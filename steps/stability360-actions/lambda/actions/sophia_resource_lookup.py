"""
Stability360 Actions — Community Resource Lookup (MCP Tool 6)

Queries the Sophia community resource API for resources based on
keyword, county, and optional location filters. Returns structured results
with provider name, description, address, phone, URL, and eligibility.

Falls back gracefully if the API is unavailable.
"""

import json
import math
import os
import re
import logging
import uuid
from html import escape as html_escape

import boto3
import urllib3

logger = logging.getLogger('sophia_resource_lookup')

SOPHIA_API_URL = os.environ.get(
    'SOPHIA_API_URL',
    'https://api-prod-0.sophia-app.com/api/services/search/keyword-search',
)
SOPHIA_TENANT = os.environ.get('SOPHIA_TENANT', 'sc-prod-0')
SOPHIA_ORIGIN = os.environ.get('SOPHIA_ORIGIN', 'https://www.sc211.org')
MAX_RESULTS = int(os.environ.get('SOPHIA_MAX_RESULTS', '3'))
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET_NAME', '')
API_BASE_URL = os.environ.get('API_BASE_URL', '')
PRESIGNED_URL_EXPIRY = 86400  # 24 hours

http = urllib3.PoolManager()
_s3_client = None


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client('s3')
    return _s3_client

# ---------------------------------------------------------------------------
# Tri-county ZIP code coordinates (Berkeley, Charleston, Dorchester)
# Used for proximity sorting — Haversine distance from user ZIP centroid.
# Source: US Census / zippopotam.us.  ~60 entries, ~3 KB.
# ---------------------------------------------------------------------------

ZIP_COORDS = {
    # Berkeley County
    "29059": (33.3276, -80.4024),  # Holly Hill
    "29410": (32.9302, -80.0027),  # Hanahan
    "29431": (33.2703, -79.8736),  # Bonneau
    "29434": (33.1362, -79.8826),  # Cordesville
    "29436": (33.3364, -80.1859),  # Cross
    "29445": (33.0580, -80.0101),  # Goose Creek
    "29450": (33.0439, -79.7841),  # Huger
    "29453": (33.2221, -79.6282),  # Jamestown
    "29461": (33.1971, -80.0233),  # Moncks Corner
    "29468": (33.4199, -80.0932),  # Pineville
    "29469": (33.2241, -80.0398),  # Pinopolis
    "29476": (33.1642, -79.9042),  # Russellville
    "29479": (33.3362, -79.9236),  # Saint Stephen
    "29486": (33.0185, -80.1756),  # Summerville
    "29492": (32.9668, -79.8528),  # Daniel Island / Cainhoy
    # Charleston County
    "29401": (32.7795, -79.9371),  # Charleston (downtown)
    "29403": (32.7976, -79.9493),  # Charleston
    "29404": (32.8982, -80.0686),  # Charleston AFB
    "29405": (32.8530, -79.9913),  # North Charleston
    "29406": (32.9352, -80.0325),  # North Charleston
    "29407": (32.7993, -80.0060),  # West Ashley
    "29409": (32.7961, -79.9605),  # The Citadel
    "29412": (32.7180, -79.9537),  # James Island
    "29414": (32.8215, -80.0568),  # West Ashley / Dorchester overlap
    "29415": (32.8488, -79.8577),  # North Charleston PO
    "29416": (32.8488, -79.8577),  # Charleston PO
    "29417": (32.8488, -79.8577),  # Charleston PO
    "29418": (32.8930, -80.0458),  # North Charleston
    "29419": (32.8488, -79.8577),  # North Charleston PO
    "29420": (32.9336, -80.1026),  # North Charleston
    "29422": (32.8488, -79.8577),  # Charleston PO
    "29423": (32.8488, -79.8577),  # North Charleston PO
    "29424": (32.7831, -79.9370),  # College of Charleston
    "29425": (32.7862, -79.9471),  # MUSC
    "29426": (32.7790, -80.3288),  # Adams Run
    "29429": (33.0063, -79.6561),  # Awendaw
    "29438": (32.5486, -80.3070),  # Edisto Island
    "29439": (32.6630, -79.9270),  # Folly Beach
    "29449": (32.7105, -80.2744),  # Hollywood
    "29451": (32.7943, -79.7729),  # Isle of Palms
    "29455": (32.8357, -79.8217),  # Johns Island
    "29457": (32.8488, -79.8577),  # Johns Island PO
    "29458": (33.1194, -79.5074),  # McClellanville
    "29464": (32.8473, -79.8206),  # Mount Pleasant
    "29465": (32.8488, -79.8577),  # Mount Pleasant PO
    "29466": (32.8674, -79.8049),  # Mount Pleasant
    "29470": (32.7881, -80.2223),  # Ravenel
    "29482": (32.7637, -79.8399),  # Sullivans Island
    "29485": (32.9756, -80.1831),  # Summerville
    "29487": (32.6529, -80.1829),  # Wadmalaw Island
    # Dorchester County
    "29018": (33.3475, -80.6709),  # Bowman
    "29432": (33.2628, -80.8059),  # Branchville
    "29437": (33.1247, -80.4034),  # Dorchester
    "29447": (33.0863, -80.6228),  # Grover
    "29448": (33.2205, -80.4501),  # Harleyville
    "29456": (32.9930, -80.1257),  # Ladson
    "29471": (33.1872, -80.6672),  # Reevesville
    "29472": (33.1080, -80.3086),  # Ridgeville
    "29477": (33.1845, -80.5732),  # Saint George
    "29483": (33.0280, -80.1739),  # Summerville
    "29484": (33.0023, -80.2267),  # Summerville
}

# County centroids — fallback when no ZIP is available for proximity sorting.
# Approximate geographic center of each county.
COUNTY_CENTROIDS = {
    'Berkeley':   (33.1960, -79.9510),
    'Charleston': (32.7765, -79.9311),
    'Dorchester': (33.0768, -80.4065),
}


def _haversine_miles(lat1, lng1, lat2, lng2):
    """Straight-line distance in miles between two lat/lng points."""
    R = 3959  # Earth radius in miles
    lat1, lng1, lat2, lng2 = (math.radians(v) for v in (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ['keyword']


def _validate(body):
    missing = [f for f in REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise ValueError(f'Missing required fields: {", ".join(missing)}')


# ---------------------------------------------------------------------------
# Sophia API request builder
# ---------------------------------------------------------------------------


def _build_search_payload(keyword, county='', city='', zip_code='', state='South Carolina'):
    """Build the Sophia keyword-search request payload."""
    location_values = ['United States', state or 'South Carolina']

    if county:
        location_values.append(county)
    else:
        location_values.append('')

    location_values.append(city or '')
    location_values.append(zip_code or '')

    return {
        'payload': {
            'type': 'keyword-search',
            'phrase': keyword,
            'searchLocationFilter': {
                'fieldToSearch': 'service.serviceAreas.searchLocation.keyword',
                'values': location_values,
            },
            'order': 'relevance',
            'filtersApplied': [],
            'filterButtons': [],
        }
    }


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _to_e164(raw_number):
    """Convert a raw phone number to E.164 format with dashes (+1-XXX-XXX-XXXX for US)."""
    digits = re.sub(r'\D', '', str(raw_number))
    if len(digits) == 10:
        return f'+1-{digits[:3]}-{digits[3:6]}-{digits[6:]}'
    if len(digits) == 11 and digits.startswith('1'):
        return f'+{digits[0]}-{digits[1:4]}-{digits[4:7]}-{digits[7:]}'
    if digits.startswith('+'):
        return digits
    return f'+{digits}' if digits else ''


def _ensure_https(url):
    """Ensure URL has https:// prefix so links are clickable."""
    if not url:
        return ''
    url = url.strip()
    if url.startswith('http://') or url.startswith('https://'):
        return url
    if url.startswith('www.') or '.' in url:
        return f'https://{url}'
    return url


def _strip_html(text):
    """Remove HTML tags and decode entities."""
    if not text:
        return ''
    clean = re.sub(r'<[^>]+>', '', str(text))
    clean = clean.replace('&nbsp;', ' ').replace('&amp;', '&')
    return clean.strip()


def _parse_results(raw_results, max_results=None, user_coords=None):
    """Parse Sophia API results into a clean, structured format.

    When *user_coords* is provided as (lat, lng), results are sorted by
    proximity (nearest first) and each result includes ``distance_miles``.
    Otherwise, the API's relevance ordering is preserved.
    """
    max_results = max_results or MAX_RESULTS

    # Parse more than max_results when sorting by proximity so we pick
    # the closest ones from a wider pool.
    parse_limit = max_results * 5 if user_coords else max_results
    parsed = []

    for item in raw_results[:parse_limit]:
        service = item.get('service', {}) or {}
        location = item.get('location') or {}
        organization = service.get('organization', {}) or {}

        # Address lives in location.addresses[] (array), not location.address
        addresses = location.get('addresses', []) or []
        address = addresses[0] if addresses else {}

        # Phones: prefer top-level item.phones, fall back to service.phones
        phones = item.get('phones', []) or service.get('phones', []) or []

        # Build address string
        addr_parts = [
            address.get('address1', ''),
            address.get('city', ''),
            address.get('stateProvince', ''),
            address.get('zipCode', '') or address.get('postalCode', ''),
        ]
        addr_str = ', '.join(p for p in addr_parts if p).strip(', ')

        # Extract phone numbers in E.164 format
        phone_list = []
        for p in phones:
            if isinstance(p, dict):
                raw = p.get('number', '') or p.get('plainNumber', '')
                label = p.get('phoneLabel', '') or p.get('name', '')
                e164 = _to_e164(raw)
                if e164:
                    phone_list.append(f'{e164} ({label})' if label else e164)
            elif isinstance(p, str) and p:
                e164 = _to_e164(p)
                if e164:
                    phone_list.append(e164)

        # Clean description
        description = _strip_html(service.get('description', ''))
        if len(description) > 500:
            description = description[:497] + '...'

        result = {
            'service_name': service.get('name', 'Unknown Service'),
            'organization': organization.get('name', ''),
            'description': description,
            'address': addr_str,
            'phones': phone_list,
            'url': _ensure_https(service.get('url') or item.get('url') or ''),
            'eligibility': _strip_html(service.get('eligibility', '')),
            'fees': _strip_html(service.get('fees', '')),
        }

        # Calculate distance from user when coordinates are available
        if user_coords:
            res_lat = location.get('latitude')
            res_lng = location.get('longitude')
            if res_lat and res_lng:
                miles = _haversine_miles(
                    user_coords[0], user_coords[1],
                    float(res_lat), float(res_lng),
                )
                result['distance_miles'] = round(miles, 1)

        # Only include non-empty fields
        result = {k: v for k, v in result.items() if v}
        if result.get('service_name'):
            parsed.append(result)

    # Sort by distance when available (nearest first)
    if user_coords:
        parsed.sort(key=lambda r: r.get('distance_miles', float('inf')))
        # Filter out results we KNOW are beyond 50 miles; keep unknown-distance results
        nearby = [r for r in parsed
                  if 'distance_miles' not in r or r['distance_miles'] <= 50]
        if nearby:
            parsed = nearby

    return parsed[:max_results]


# ---------------------------------------------------------------------------
# HTML results page + presigned URL
# ---------------------------------------------------------------------------


def _build_results_html(keyword, parsed_results, zip_code=''):
    """Build a mobile-friendly HTML page showing all results."""
    location_label = f' near {zip_code}' if zip_code else ''
    cards_html = []
    for i, r in enumerate(parsed_results, 1):
        name = html_escape(r.get('service_name', 'Unknown'))
        parts = [f'<h3>{i}. {name}</h3>']
        if r.get('address'):
            dist = f' &mdash; {r["distance_miles"]} mi' if r.get('distance_miles') else ''
            parts.append(f'<p class="addr">{html_escape(r["address"])}{dist}</p>')
        if r.get('phones'):
            phone = r['phones'][0]
            # Extract just the number for tel: link
            num = phone.split(' ')[0] if ' ' in phone else phone
            parts.append(f'<p class="phone"><a href="tel:{num}">{html_escape(phone)}</a></p>')
        if r.get('url'):
            url = r['url']
            parts.append(f'<p class="web"><a href="{html_escape(url)}" target="_blank">{html_escape(url)}</a></p>')
        if r.get('description'):
            parts.append(f'<p class="desc">{html_escape(r["description"])}</p>')
        if r.get('eligibility'):
            parts.append(f'<p class="elig"><strong>Eligibility:</strong> {html_escape(r["eligibility"][:200])}</p>')
        cards_html.append(f'<div class="card">{"".join(parts)}</div>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Resources for {html_escape(keyword)}{location_label} — Stability360</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,system-ui,sans-serif; background:#f5f5f5; color:#333; padding:16px; }}
  .header {{ background:#1a5276; color:#fff; padding:20px; border-radius:8px; margin-bottom:16px; text-align:center; }}
  .header h1 {{ font-size:20px; margin-bottom:4px; }}
  .header p {{ font-size:14px; opacity:0.85; }}
  .card {{ background:#fff; border-radius:8px; padding:16px; margin-bottom:12px; box-shadow:0 1px 3px rgba(0,0,0,0.1); }}
  .card h3 {{ font-size:16px; color:#1a5276; margin-bottom:8px; }}
  .card p {{ font-size:14px; margin-bottom:4px; line-height:1.4; }}
  .card .addr {{ color:#555; }}
  .card .phone a {{ color:#1a5276; text-decoration:none; font-weight:600; }}
  .card .web a {{ color:#2980b9; word-break:break-all; }}
  .card .desc {{ color:#666; font-size:13px; }}
  .card .elig {{ color:#777; font-size:13px; }}
  .footer {{ text-align:center; font-size:12px; color:#888; margin-top:20px; padding:12px; }}
  .footer a {{ color:#2980b9; }}
</style>
</head>
<body>
<div class="header">
  <h1>Community Resources</h1>
  <p>Results for &ldquo;{html_escape(keyword)}&rdquo;{location_label}</p>
</div>
{"".join(cards_html)}
<div class="footer">
  Stability360 by Trident United Way<br>
  This link expires in 24 hours.
</div>
</body>
</html>"""


def _upload_results_page(keyword, parsed_results, zip_code=''):
    """Upload HTML results page to S3 and return a short redirect URL."""
    if not RESULTS_BUCKET:
        logger.warning('RESULTS_BUCKET_NAME not set — skipping results page upload')
        return None

    html_content = _build_results_html(keyword, parsed_results, zip_code)
    page_id = uuid.uuid4().hex[:12]
    s3_key = f'results/{page_id}.html'

    try:
        s3 = _get_s3_client()
        s3.put_object(
            Bucket=RESULTS_BUCKET,
            Key=s3_key,
            Body=html_content.encode('utf-8'),
            ContentType='text/html',
        )
        # Return short redirect URL instead of long presigned URL
        # Read at call time (index.py sets this from API Gateway event context)
        api_base = os.environ.get('API_BASE_URL', '')
        if api_base:
            short_url = f'{api_base}/r/{page_id}'
        else:
            # Fallback to presigned URL if API_BASE_URL not set
            short_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': RESULTS_BUCKET, 'Key': s3_key},
                ExpiresIn=PRESIGNED_URL_EXPIRY,
            )
        logger.info('Results page uploaded: s3://%s/%s → %s', RESULTS_BUCKET, s3_key, short_url)
        return short_url
    except Exception:
        logger.error('Failed to upload results page', exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_resource_lookup(body):
    """Query Sophia 211 API for community resources."""

    if not body:
        raise ValueError('Request body is required')

    _validate(body)

    keyword = body.get('keyword', '')
    county = body.get('county', '')
    city = body.get('city', '')
    zip_code = body.get('zip_code', '') or body.get('zipCode', '')
    state = body.get('state', 'South Carolina')
    max_results = min(int(body.get('max_results', MAX_RESULTS)), 20)

    # Look up user coordinates for proximity sorting
    # Priority: ZIP centroid → county centroid → none
    user_coords = ZIP_COORDS.get(zip_code)
    coords_source = 'zip'
    if not user_coords and county:
        user_coords = COUNTY_CENTROIDS.get(county)
        coords_source = 'county'
    if user_coords:
        logger.info('Resource lookup: keyword=%s, county=%s, zip=%s → coords=(%s, %s) source=%s',
                     keyword, county, zip_code, user_coords[0], user_coords[1], coords_source)
    else:
        logger.info('Resource lookup: keyword=%s, county=%s, city=%s, zip=%s (no coords)',
                     keyword, county, city, zip_code)

    search_payload = _build_search_payload(keyword, county, city, zip_code, state)
    body_bytes = json.dumps(search_payload).encode('utf-8')

    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Tenant': SOPHIA_TENANT,
        'Origin': SOPHIA_ORIGIN,
    }

    try:
        resp = http.request(
            'POST',
            SOPHIA_API_URL,
            body=body_bytes,
            headers=headers,
            timeout=urllib3.Timeout(connect=5.0, read=25.0),
            retries=False,
        )

        if resp.status != 200:
            logger.warning('Sophia API returned status %d', resp.status)
            return {
                'found': False,
                'results': [],
                'total_count': 0,
                'message': (
                    'The community resource directory is temporarily unavailable. '
                    'A team member may be able to help — offer to connect the client.'
                ),
                'source': 'sophia_211_error',
            }

        resp_text = resp.data.decode('utf-8', errors='replace')
        resp_json = json.loads(resp_text)

        raw_results = resp_json.get('payload', [])
        parsed = _parse_results(raw_results, max_results, user_coords=user_coords)

        if not parsed:
            logger.info('No results found for: %s in %s', keyword, county or 'state')
            return {
                'found': False,
                'results': [],
                'message': (
                    f'No resources found for "{keyword}" '
                    f'{"in " + county + " County" if county else "in your area"}. '
                    'Offer to connect the client with a team member for assistance.'
                ),
                'source': 'sophia_211',
            }

        sorted_label = ' (sorted by proximity)' if user_coords else ''
        logger.info('Found results (showing %d%s) for: %s in %s',
                     len(parsed), sorted_label, keyword, county or 'state')

        # Parse a wider set for the full HTML page (up to 20)
        all_parsed = _parse_results(raw_results, 20, user_coords=user_coords)

        # Upload HTML results page and get presigned URL
        browse_url = _upload_results_page(keyword, all_parsed, zip_code)

        # Pre-formatted markdown for the agent to output directly
        formatted_lines = []
        for i, r in enumerate(parsed, 1):
            name = r.get('service_name', 'Unknown')
            formatted_lines.append(f'**{i}. {name}**')
            if r.get('address'):
                dist = f' -- {r["distance_miles"]} mi' if r.get('distance_miles') else ''
                formatted_lines.append(f'Address: {r["address"]}{dist}')
            if r.get('phones'):
                formatted_lines.append(f'Phone: {r["phones"][0]}')
            if r.get('url'):
                formatted_lines.append(f'Web: {r["url"]}')
            if r.get('description'):
                desc = r['description'][:120]
                formatted_lines.append(f'({desc})')
            formatted_lines.append('')

        if browse_url:
            formatted_lines.append('---')
            formatted_lines.append(f'**📋 View all results here:** {browse_url}')
            formatted_lines.append('(Link expires in 24 hours)')
            formatted_lines.append('')

        return {
            'found': True,
            'results': parsed,
            'formatted_results': '\n'.join(formatted_lines),
            'sorted_by': 'proximity' if user_coords else 'relevance',
            'browse_url': browse_url or '',
            'message': (
                f'Here are some nearby resources for "{keyword}". '
                'Present formatted_results to the caller. '
                'Do NOT mention how many total results exist. '
                'The "View all results" link at the bottom expires in 24 hours.'
            ),
            'source': 'sophia_211',
        }

    except Exception:
        logger.error('Sophia API request failed', exc_info=True)
        return {
            'found': False,
            'results': [],
            'total_count': 0,
            'message': (
                'The community resource directory is temporarily unavailable. '
                'A team member may be able to help — offer to connect the client.'
            ),
            'source': 'sophia_211_error',
        }
