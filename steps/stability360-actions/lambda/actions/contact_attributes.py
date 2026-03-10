"""
Stability360 Actions -- Contact Attribute Persistence

Saves recognized session attributes as Amazon Connect contact attributes
after every successful tool call. Also derives eligibility flags from
caller demographics.
"""

import boto3
from botocore.exceptions import ClientError

from config import (
    ATTR_MAP, CONNECT_INSTANCE_ID, CONNECT_REGION, UUID_RE, get_logger,
    normalize_phone,
)

logger = get_logger('contact_attributes')

# Scoring result keys -> Connect attribute names
SCORE_FIELDS = {
    'housing_score': 'housingScore',
    'housing_label': 'housingLabel',
    'employment_score': 'employmentScore',
    'employment_label': 'employmentLabel',
    'financial_resilience_score': 'financialResilienceScore',
    'financial_label': 'financialLabel',
    'composite_score': 'compositeScore',
    'composite_label': 'compositeLabel',
    'priority_flag': 'priorityFlag',
    'priority_meaning': 'priorityMeaning',
    'recommended_path': 'recommendedPath',
    'path_meaning': 'pathMeaning',
}


def get_contact_ids(body):
    """Extract and validate instance_id and contact_id from the request body.

    Returns (instance_id, contact_id) or (None, None) if invalid.
    """
    raw_instance = body.get('instance_id') or CONNECT_INSTANCE_ID
    raw_contact = body.get('contact_id') or ''
    instance_id = raw_instance.strip() if raw_instance else ''
    contact_id = raw_contact.strip() if raw_contact else ''

    if not instance_id or not UUID_RE.match(instance_id):
        return None, None
    if not contact_id or not UUID_RE.match(contact_id):
        return None, None
    return instance_id, contact_id


def save_contact_attributes(body, result, request_id):
    """Persist recognized session attributes as Connect contact attributes.

    Called automatically after every successful tool handler. Silently skips
    if instance_id or contact_id is missing/invalid.
    """
    instance_id, contact_id = get_contact_ids(body)

    logger.info(
        'Contact attribute check -- instance_id=%s, contact_id=%s, env_fallback=%s',
        body.get('instance_id', '<not in body>'),
        body.get('contact_id', '<not in body>'),
        CONNECT_INSTANCE_ID or '<not set>',
    )

    if not instance_id:
        logger.warning('Skipping contact attributes -- invalid instance_id')
        return
    if not contact_id:
        logger.warning('Skipping contact attributes -- invalid contact_id')
        return

    # Collect from request body
    attributes = {}
    phone_attr_names = {'contactInfo', 'phoneNumber'}
    contact_method = str(body.get('contactMethod', '')).strip().lower()
    for body_key, attr_name in ATTR_MAP.items():
        value = body.get(body_key)
        if value is not None and str(value).strip():
            val = str(value).strip()
            # Normalize phone numbers to E.164
            if attr_name == 'phoneNumber':
                val = normalize_phone(val)
            elif attr_name == 'contactInfo' and contact_method in ('phone', 'both'):
                val = normalize_phone(val)
            attributes[attr_name] = val

    # Collect scoring results from handler output
    for result_key, attr_name in SCORE_FIELDS.items():
        value = result.get(result_key)
        if value is not None:
            attributes[attr_name] = str(value).strip()

    # Collect disposition from handler result
    for key in ('disposition', 'dispositionLabel'):
        value = result.get(key)
        if value is not None:
            attr_name = 'callDisposition' if key == 'disposition' else 'callDispositionLabel'
            attributes[attr_name] = str(value).strip()

    if not attributes:
        logger.info('No attributes to save for request %s', request_id)
        return

    logger.info(
        'Saving %d contact attributes for contact %s: %s',
        len(attributes), contact_id, list(attributes.keys()),
    )

    try:
        connect_client = boto3.client('connect', region_name=CONNECT_REGION)
        connect_client.update_contact_attributes(
            InstanceId=instance_id,
            InitialContactId=contact_id,
            Attributes=attributes,
        )
        logger.info(
            'Saved %d contact attributes',
            len(attributes),
            extra={'extra': {
                'requestId': request_id,
                'contactId': contact_id,
                'attributes': list(attributes.keys()),
            }},
        )
    except ClientError as exc:
        logger.warning(
            'Failed to save contact attributes: %s',
            exc,
            extra={'extra': {'requestId': request_id, 'contactId': contact_id}},
        )


def save_extra_attributes(body, attributes):
    """Save a dict of extra attributes to the contact (e.g., eligibility flags).

    Silently skips if instance_id/contact_id invalid or attributes empty.
    """
    if not attributes:
        return
    instance_id, contact_id = get_contact_ids(body)
    if not instance_id or not contact_id:
        return
    try:
        connect_client = boto3.client('connect', region_name=CONNECT_REGION)
        connect_client.update_contact_attributes(
            InstanceId=instance_id,
            InitialContactId=contact_id,
            Attributes=attributes,
        )
        logger.info('Saved %d extra attributes: %s', len(attributes), list(attributes.keys()))
    except Exception:
        logger.warning('Failed to save extra attributes', exc_info=True)


def derive_eligibility_flags(body):
    """Derive eligibility flags from demographics.

    Returns dict of flags to save as contact attributes.
    """
    flags = {}

    # Age 65+ -> BCDCOG
    age = body.get('age', '')
    try:
        if age and int(str(age).strip()) >= 65:
            flags['eligibleBCDCOG'] = 'true'
    except (ValueError, TypeError):
        pass

    # Children under 18 -> Siemer
    children = str(body.get('hasChildrenUnder18', '')).strip().lower()
    if children in ('true', 'yes', 'y'):
        flags['eligibleSiemer'] = 'true'

    # Military -> Mission United
    military = str(body.get('militaryAffiliation', '')).strip().lower()
    if military and military not in ('none', 'no', 'n', 'n/a', ''):
        flags['eligibleMissionUnited'] = 'true'

    # Job seeking / unemployed -> Barriers to Employment
    employment = str(body.get('employmentStatus', '')).strip().lower()
    if any(kw in employment for kw in ('unemployed', 'seeking', 'looking', 'no job', 'not working')):
        flags['eligibleBarriersToEmployment'] = 'true'

    return flags
