"""
Stability360 Actions — Sophia 211 Resource Lookup (MCP Tool 6)

Queries the Sophia 211 API (sc211.org) for community resources based on
keyword, county, and optional location filters. Returns structured results
with provider name, description, address, phone, URL, and eligibility.

Falls back gracefully if the API is unavailable.
"""

import json
import math
import os
import re
import logging

import urllib3

logger = logging.getLogger('sophia_resource_lookup')

SOPHIA_API_URL = os.environ.get(
    'SOPHIA_API_URL',
    'https://api-prod-0.sophia-app.com/api/services/search/keyword-search',
)
SOPHIA_TENANT = os.environ.get('SOPHIA_TENANT', 'sc-prod-0')
SOPHIA_ORIGIN = os.environ.get('SOPHIA_ORIGIN', 'https://www.sc211.org')
MAX_RESULTS = int(os.environ.get('SOPHIA_MAX_RESULTS', '10'))

http = urllib3.PoolManager()

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
    parse_limit = max_results * 3 if user_coords else max_results
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
            'url': service.get('url') or item.get('url') or '',
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

    return parsed[:max_results]


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
    zip_code = body.get('zip_code', '')
    state = body.get('state', 'South Carolina')
    max_results = min(int(body.get('max_results', MAX_RESULTS)), 20)

    # Look up user coordinates from ZIP for proximity sorting
    user_coords = ZIP_COORDS.get(zip_code)
    if user_coords:
        logger.info('Resource lookup: keyword=%s, county=%s, zip=%s → coords=(%s, %s)',
                     keyword, county, zip_code, user_coords[0], user_coords[1])
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
                    'Please try dialing 211 directly for assistance.'
                ),
                'source': 'sophia_211_error',
            }

        resp_text = resp.data.decode('utf-8', errors='replace')
        resp_json = json.loads(resp_text)

        raw_results = resp_json.get('payload', [])
        total_count = len(raw_results)
        parsed = _parse_results(raw_results, max_results, user_coords=user_coords)

        if not parsed:
            logger.info('No results found for: %s in %s', keyword, county or 'state')
            return {
                'found': False,
                'results': [],
                'total_count': 0,
                'message': (
                    f'No resources found for "{keyword}" '
                    f'{"in " + county + " County" if county else "in your area"}. '
                    'You can try dialing 211 for additional help.'
                ),
                'source': 'sophia_211',
            }

        sorted_label = ' (sorted by proximity)' if user_coords else ''
        logger.info('Found %d results (showing %d%s) for: %s in %s',
                     total_count, len(parsed), sorted_label, keyword, county or 'state')

        return {
            'found': True,
            'results': parsed,
            'total_count': total_count,
            'showing': len(parsed),
            'sorted_by': 'proximity' if user_coords else 'relevance',
            'message': (
                f'Found {total_count} resources for "{keyword}" '
                f'{"in " + county + " County" if county else "in your area"}. '
                f'Here are the top {len(parsed)} nearest results.'
                if user_coords else
                f'Found {total_count} resources for "{keyword}" '
                f'{"in " + county + " County" if county else "in your area"}. '
                f'Here are the top {len(parsed)} results.'
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
                'Please try dialing 211 directly for assistance.'
            ),
            'source': 'sophia_211_error',
        }
