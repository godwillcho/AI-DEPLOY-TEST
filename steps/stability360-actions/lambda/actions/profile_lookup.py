"""
Stability360 Actions -- Profile Lookup (Read-Only)

Searches Amazon Connect Customer Profiles by phone, email, or full name.
Returns stored fields for returning callers so the AI agent can skip
re-asking known information.

Read-only -- never creates or updates profiles. Profile creation
stays in task_manager.py at disposition time.
"""

import logging
import os

import boto3

from config import normalize_phone

logger = logging.getLogger('profile_lookup')

CUSTOMER_PROFILES_DOMAIN = os.environ.get('CUSTOMER_PROFILES_DOMAIN', '')
CONNECT_REGION = os.environ.get('CONNECT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))


def _search_profiles(client, domain, key_name, value):
    """Search profiles by a key. Returns profile dict or None."""
    try:
        resp = client.search_profiles(
            DomainName=domain,
            KeyName=key_name,
            Values=[value],
            MaxResults=10,
        )
        items = resp.get('Items', [])
        if len(items) == 1:
            logger.info('Found profile by %s: %s', key_name, items[0]['ProfileId'])
            return items[0]
        if len(items) > 1:
            # Pick most recently updated
            best = sorted(items, key=lambda x: x.get('LastUpdatedAt', ''), reverse=True)[0]
            logger.info('Found %d profiles by %s — using most recent: %s',
                        len(items), key_name, best['ProfileId'])
            return best
    except Exception:
        logger.debug('Profile search by %s failed', key_name, exc_info=True)
    return None


# Custom attributes stored on the profile (intake data)
CUSTOM_ATTR_KEYS = [
    'zipCode', 'county', 'age', 'childrenUnder18', 'contactMethod',
    'employmentStatus', 'employer',
    'housingSituation', 'monthlyIncome',
    'militaryAffiliation', 'publicAssistance',
    'lastNeedCategory',
]


def _extract_fields(profile):
    """Extract usable fields from a Customer Profile record.

    Pulls standard fields (name, phone, email) and custom attributes
    (ZIP, age, employment, housing, last need category, etc.).
    """
    fields = {}
    # Standard fields
    for cp_key, field_name in [
        ('FirstName', 'firstName'),
        ('LastName', 'lastName'),
        ('PhoneNumber', 'phoneNumber'),
        ('EmailAddress', 'emailAddress'),
    ]:
        val = profile.get(cp_key, '').strip()
        if val:
            fields[field_name] = val

    # Custom attributes (intake data from previous calls)
    custom = profile.get('Attributes', {})
    for key in CUSTOM_ATTR_KEYS:
        val = custom.get(key, '').strip()
        if val:
            fields[key] = val

    return fields


def lookup_profile(body):
    """Search Customer Profiles by phone, email, or name.

    Returns profile fields if found, empty dict if not.
    """
    domain = CUSTOMER_PROFILES_DOMAIN
    if not domain:
        logger.info('CUSTOMER_PROFILES_DOMAIN not set — skipping lookup.')
        return {
            'profileFound': False,
            'fields': {},
            'message': 'No existing profile. Collect all required fields.',
        }

    # Extract identifiers from request
    contact_info = body.get('contactInfo', '').strip()
    phone = body.get('phoneNumber', '').strip()
    email = body.get('emailAddress', '').strip()

    # Detect phone vs email from contactInfo
    if contact_info:
        if '@' in contact_info:
            email = email or contact_info
        else:
            phone = phone or contact_info

    first_name = body.get('firstName', '').strip()
    last_name = body.get('lastName', '').strip()

    if phone:
        phone = normalize_phone(phone)

    if not phone and not email and not (first_name and last_name):
        return {
            'profileFound': False,
            'fields': {},
            'message': 'No identifier provided. Collect all required fields.',
        }

    try:
        client = boto3.client('customer-profiles', region_name=CONNECT_REGION)

        # Search: phone → email → name
        profile = None
        if phone:
            profile = _search_profiles(client, domain, '_phone', phone)
        if not profile and email:
            profile = _search_profiles(client, domain, '_email', email)
        if not profile and first_name and last_name:
            full_name = f'{first_name} {last_name}'
            profile = _search_profiles(client, domain, '_fullName', full_name)

        if profile:
            fields = _extract_fields(profile)
            last_need = fields.get('lastNeedCategory', '')
            logger.info('Profile lookup: found %s with %d fields (lastNeed=%s)',
                        profile['ProfileId'], len(fields), last_need or 'none')

            message = (
                'Returning caller found. Use these fields — only ask for what is missing. '
                'Do NOT re-ask for fields already provided by the profile.'
            )
            if last_need:
                message += (
                    f' Their last request was for: {last_need}. '
                    'Ask if they need help with the same thing or something different. '
                    'If same: skip classifyNeed and getRequiredFields, go to ZIP validation then resourceLookup. '
                    'If different: classify the new need and ask only for fields not already on the profile.'
                )

            return {
                'profileFound': True,
                'profileId': profile['ProfileId'],
                'fields': fields,
                'lastNeedCategory': last_need,
                'message': message,
            }

        return {
            'profileFound': False,
            'fields': {},
            'message': 'No existing profile. Collect all required fields.',
        }

    except Exception:
        logger.warning('Profile lookup failed', exc_info=True)
        return {
            'profileFound': False,
            'fields': {},
            'message': 'Profile lookup unavailable. Collect all required fields.',
        }
