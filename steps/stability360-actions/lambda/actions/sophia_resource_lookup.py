"""
Stability360 Actions — Sophia 211 Resource Lookup (MCP Tool 6)

Queries the Sophia 211 API (sc211.org) for community resources based on
keyword, county, and optional location filters. Returns structured results
with provider name, description, address, phone, URL, and eligibility.

Falls back gracefully if the API is unavailable.
"""

import json
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


def _strip_html(text):
    """Remove HTML tags and decode entities."""
    if not text:
        return ''
    clean = re.sub(r'<[^>]+>', '', str(text))
    clean = clean.replace('&nbsp;', ' ').replace('&amp;', '&')
    return clean.strip()


def _parse_results(raw_results, max_results=None):
    """Parse Sophia API results into a clean, structured format."""
    max_results = max_results or MAX_RESULTS
    parsed = []

    for item in raw_results[:max_results]:
        service = item.get('service', {}) or {}
        location = item.get('location', {}) or {}
        organization = service.get('organization', {}) or {}
        address = location.get('address', {}) or {}
        phones = item.get('phones', []) or []

        # Build address string
        addr_parts = [
            address.get('address1', ''),
            address.get('city', ''),
            address.get('stateProvince', ''),
            address.get('postalCode', ''),
        ]
        addr_str = ', '.join(p for p in addr_parts if p).strip(', ')

        # Extract phone numbers
        phone_list = []
        for p in phones:
            if isinstance(p, dict):
                number = p.get('number', '')
                name = p.get('name', '')
                if number:
                    phone_list.append(f'{number} ({name})' if name else number)
            elif isinstance(p, str) and p:
                phone_list.append(p)

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

        # Only include non-empty fields
        result = {k: v for k, v in result.items() if v}
        if result.get('service_name'):
            parsed.append(result)

    return parsed


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

    logger.info('Resource lookup: keyword=%s, county=%s, city=%s, zip=%s',
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
        parsed = _parse_results(raw_results, max_results)

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

        logger.info('Found %d results (showing %d) for: %s in %s',
                     total_count, len(parsed), keyword, county or 'state')

        return {
            'found': True,
            'results': parsed,
            'total_count': total_count,
            'showing': len(parsed),
            'message': (
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
