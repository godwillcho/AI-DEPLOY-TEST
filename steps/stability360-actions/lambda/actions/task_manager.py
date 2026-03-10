"""
Stability360 Actions — Task, Customer Profile, and Case Manager

Handles post-disposition automation when a caller chooses 'callback' or 'live_transfer':
  1. Find or create a Customer Profile (by phone, email, or name)
  2. Create an Amazon Connect Task (callback only) routed to BasicQueue
  3. Create a Case linked to the contact and customer profile (both dispositions)

All operations are silent — the caller never knows about profile/case creation.
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from config import normalize_phone

logger = logging.getLogger('task_manager')

# ---------------------------------------------------------------------------
# Configuration (from Lambda env vars, set by deploy.py)
# ---------------------------------------------------------------------------

TASK_CONTACT_FLOW_ID = os.environ.get('TASK_CONTACT_FLOW_ID', '')
TASK_TEMPLATE_ID = os.environ.get('TASK_TEMPLATE_ID', '')
BASIC_QUEUE_ARN = os.environ.get('BASIC_QUEUE_ARN', '')
CUSTOMER_PROFILES_DOMAIN = os.environ.get('CUSTOMER_PROFILES_DOMAIN', '')
CONNECT_CASES_DOMAIN_ID = os.environ.get('CONNECT_CASES_DOMAIN_ID', '')
CASE_TEMPLATE_ID = os.environ.get('CASE_TEMPLATE_ID', '')
CONNECT_REGION = os.environ.get('CONNECT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Customer Profile
# ---------------------------------------------------------------------------


def find_or_create_customer_profile(body):
    """Search for an existing customer profile by phone/email/name, or create one.

    Multi-step search to handle duplicates:
      1. Search by phone — if exactly 1 → use it
      2. If 0 or multiple → search by email — if exactly 1 → use it
      3. If still ambiguous → search by full name
      4. If multiple at any step → pick the most recent
      5. If no results → create new profile

    Returns profile_id or None.
    """
    domain = CUSTOMER_PROFILES_DOMAIN
    if not domain:
        logger.info('CUSTOMER_PROFILES_DOMAIN not set — skipping profile.')
        return None

    first_name = body.get('firstName', '').strip()
    last_name = body.get('lastName', '').strip()
    contact_method = body.get('contactMethod', '').strip().lower()
    contact_info = body.get('contactInfo', '').strip()
    phone = (contact_info if contact_method == 'phone' else '') or body.get('phoneNumber', '').strip()
    email = (contact_info if contact_method == 'email' else '') or body.get('emailAddress', '').strip()

    # Normalize phone to E.164 format for consistent search/storage
    if phone:
        phone = normalize_phone(phone)

    try:
        profiles_client = boto3.client('customer-profiles', region_name=CONNECT_REGION)

        # Step 1: Search by phone
        if phone:
            profile_id = _search_profiles(profiles_client, domain, '_phone', phone)
            if profile_id:
                return profile_id

        # Step 2: Search by email
        if email:
            profile_id = _search_profiles(profiles_client, domain, '_email', email)
            if profile_id:
                return profile_id

        # Step 3: Search by full name
        full_name = f'{first_name} {last_name}'.strip()
        if full_name:
            profile_id = _search_profiles(profiles_client, domain, '_fullName', full_name)
            if profile_id:
                return profile_id

        # Step 4: Create new profile
        create_kwargs = {'DomainName': domain}
        if first_name:
            create_kwargs['FirstName'] = first_name
        if last_name:
            create_kwargs['LastName'] = last_name
        if phone:
            create_kwargs['PhoneNumber'] = phone
        if email:
            create_kwargs['EmailAddress'] = email

        resp = profiles_client.create_profile(**create_kwargs)
        profile_id = resp['ProfileId']
        logger.info('Created customer profile: %s', profile_id)
        return profile_id

    except Exception:
        logger.warning('Customer profile operation failed', exc_info=True)
        return None


def _search_profiles(profiles_client, domain, key_name, value):
    """Search profiles by a key. Returns profile_id if found, None otherwise."""
    try:
        resp = profiles_client.search_profiles(
            DomainName=domain,
            KeyName=key_name,
            Values=[value],
            MaxResults=10,
        )
        items = resp.get('Items', [])
        if len(items) == 1:
            profile_id = items[0]['ProfileId']
            logger.info('Found unique profile by %s: %s', key_name, profile_id)
            return profile_id
        if len(items) > 1:
            # Pick the most recently updated
            sorted_items = sorted(
                items,
                key=lambda x: x.get('LastUpdatedAt', ''),
                reverse=True,
            )
            profile_id = sorted_items[0]['ProfileId']
            logger.info(
                'Found %d profiles by %s — using most recent: %s',
                len(items), key_name, profile_id,
            )
            return profile_id
    except Exception:
        logger.debug('Profile search by %s failed', key_name, exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Task Creation
# ---------------------------------------------------------------------------


def create_callback_task(body, instance_id, contact_id, profile_id=None):
    """Create an Amazon Connect task for a callback request.

    Returns task_contact_id or None.
    """
    if not TASK_CONTACT_FLOW_ID:
        logger.warning('TASK_CONTACT_FLOW_ID not set — cannot create task.')
        return None

    first_name = body.get('firstName', '').strip() or 'Unknown'
    last_name = body.get('lastName', '').strip() or 'Caller'
    need_category = (
        body.get('keyword', '') or body.get('needCategory', '') or 'General'
    )

    task_name = f'Callback: {first_name} {last_name} — {need_category}'[:512]

    description_parts = [
        f'Callback requested by {first_name} {last_name}',
        f'Need: {need_category}',
    ]
    for label, key in [
        ('ZIP', 'zipCode'), ('Contact', 'contactInfo'),
        ('Employment', 'employmentStatus'), ('Employer', 'employer'),
        ('Scoring', 'scoringSummary'),
        ('Preferred days', 'preferredDays'), ('Preferred times', 'preferredTimes'),
    ]:
        val = body.get(key, '').strip()
        if val:
            description_parts.append(f'{label}: {val}')
    task_description = '\n'.join(description_parts)[:4096]

    # Build references (task template fields)
    references = {}
    for key in [
        'firstName', 'lastName', 'needCategory', 'zipCode',
        'contactMethod', 'contactInfo', 'employmentStatus', 'employer',
        'partnerEmployee', 'scoringSummary', 'preferredDays', 'preferredTimes',
    ]:
        val = body.get(key, '')
        if key == 'needCategory':
            val = need_category
        if val:
            references[key] = {'Value': str(val)[:4096], 'Type': 'STRING'}

    try:
        connect_client = boto3.client('connect', region_name=CONNECT_REGION)

        task_kwargs = {
            'InstanceId': instance_id,
            'Name': task_name,
            'Description': task_description,
            'PreviousContactId': contact_id,
        }
        if references:
            task_kwargs['References'] = references
        # Pass profile ID as contact attribute so the task flow can resolve it
        if profile_id:
            task_kwargs['Attributes'] = {'customerProfileId': profile_id}
        if TASK_TEMPLATE_ID:
            # Template already has ContactFlowId — don't pass both
            task_kwargs['TaskTemplateId'] = TASK_TEMPLATE_ID
        else:
            # No template — use the flow directly
            task_kwargs['ContactFlowId'] = TASK_CONTACT_FLOW_ID

        resp = connect_client.start_task_contact(**task_kwargs)
        task_contact_id = resp['ContactId']
        logger.info('Task created: %s (linked to contact %s)', task_contact_id, contact_id)
        return task_contact_id

    except Exception:
        logger.warning('Failed to create callback task', exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Case Creation
# ---------------------------------------------------------------------------


def create_case(body, instance_id, contact_id, profile_id=None):
    """Create a Connect Case linked to the contact and customer profile.

    Returns case_id or None. Silent — caller never knows.
    """
    domain_id = CONNECT_CASES_DOMAIN_ID
    if not domain_id:
        logger.info('CONNECT_CASES_DOMAIN_ID not set — skipping case creation.')
        return None

    first_name = body.get('firstName', '').strip() or 'Unknown'
    last_name = body.get('lastName', '').strip() or 'Caller'
    need_category = (
        body.get('keyword', '') or body.get('needCategory', '') or 'General'
    )

    try:
        cases_client = boto3.client('connectcases', region_name=CONNECT_REGION)

        # Use the Stability360 case template (set by deploy.py)
        template_id = CASE_TEMPLATE_ID
        if not template_id:
            logger.warning('CASE_TEMPLATE_ID not set — cannot create case.')
            return None

        # System field IDs are fixed strings in Connect Cases
        title = f'{need_category} — {first_name} {last_name}'
        fields = [
            {'id': 'title', 'value': {'stringValue': title[:500]}},
        ]
        if profile_id:
            # customer_id expects a full profile ARN
            domain = CUSTOMER_PROFILES_DOMAIN
            sts = boto3.client('sts', region_name=CONNECT_REGION)
            account = sts.get_caller_identity()['Account']
            profile_arn = (
                f'arn:aws:profile:{CONNECT_REGION}:{account}'
                f':domains/{domain}/profiles/{profile_id}'
            )
            fields.append({
                'id': 'customer_id',
                'value': {'stringValue': profile_arn},
            })

        case_kwargs = {
            'domainId': domain_id,
            'templateId': template_id,
            'fields': fields,
        }

        resp = cases_client.create_case(**case_kwargs)
        case_id = resp.get('caseId', '')
        case_arn = resp.get('caseArn', '')
        logger.info('Case created: %s', case_id)

        # Link the contact to the case
        if case_id and contact_id:
            try:
                contact_arn = _build_contact_arn(instance_id, contact_id)
                cases_client.create_related_item(
                    domainId=domain_id,
                    caseId=case_id,
                    type='Contact',
                    content={'contact': {'contactArn': contact_arn}},
                )
                logger.info('Contact %s linked to case %s', contact_id, case_id)
            except Exception:
                logger.warning('Could not link contact to case', exc_info=True)

        return case_id

    except Exception:
        logger.warning('Failed to create case', exc_info=True)
        return None




def _build_contact_arn(instance_id, contact_id):
    """Build a Connect contact ARN."""
    region = CONNECT_REGION
    # Get account from instance ARN context, or use STS
    try:
        sts = boto3.client('sts', region_name=region)
        account = sts.get_caller_identity()['Account']
    except Exception:
        account = '*'
    return f'arn:aws:connect:{region}:{account}:instance/{instance_id}/contact/{contact_id}'


# ---------------------------------------------------------------------------
# Main orchestrator — called from index.py
# ---------------------------------------------------------------------------


def handle_disposition_automation(body, result):
    """Run post-disposition automation: profile, task, case.

    Called from the Lambda handler when recordDisposition returns
    disposition='callback' or 'live_transfer'.

    Returns dict of additional contact attributes to save.
    """
    disposition = result.get('disposition', '')
    if disposition not in ('callback', 'live_transfer', 'emergency'):
        return {}

    raw_instance = body.get('instance_id') or CONNECT_INSTANCE_ID
    raw_contact = body.get('contact_id') or ''
    instance_id = raw_instance.strip() if raw_instance else ''
    contact_id = raw_contact.strip() if raw_contact else ''

    if not instance_id or not UUID_RE.match(instance_id):
        logger.warning('Cannot run disposition automation — invalid instance_id: %r', instance_id)
        return {}
    if not contact_id or not UUID_RE.match(contact_id):
        logger.warning('Cannot run disposition automation — invalid contact_id: %r', contact_id)
        return {}

    extra_attrs = {}

    # 1. Customer profile (both callback and live_transfer)
    logger.info('Disposition automation: finding/creating customer profile...')
    profile_id = find_or_create_customer_profile(body)
    if profile_id:
        extra_attrs['customerProfileId'] = profile_id
        extra_attrs['profileCreated'] = 'true'
    else:
        extra_attrs['profileCreated'] = 'false'

    # 2. Task (callback only)
    if disposition == 'callback':
        logger.info('Disposition automation: creating callback task...')
        task_contact_id = create_callback_task(body, instance_id, contact_id, profile_id)
        if task_contact_id:
            extra_attrs['taskCreated'] = 'true'
            extra_attrs['taskContactId'] = task_contact_id
        else:
            extra_attrs['taskCreated'] = 'false'

    # 3. Case (both callback and live_transfer) — linked to contact + profile
    logger.info('Disposition automation: creating case...')
    case_id = create_case(body, instance_id, contact_id, profile_id)
    if case_id:
        extra_attrs['caseId'] = case_id
        extra_attrs['caseCreated'] = 'true'
    else:
        extra_attrs['caseCreated'] = 'false'

    # Save extra attributes to the original contact
    if extra_attrs:
        try:
            connect_client = boto3.client('connect', region_name=CONNECT_REGION)
            connect_client.update_contact_attributes(
                InstanceId=instance_id,
                InitialContactId=contact_id,
                Attributes=extra_attrs,
            )
            logger.info('Saved %d disposition automation attributes: %s',
                        len(extra_attrs), list(extra_attrs.keys()))
        except Exception:
            logger.warning('Failed to save disposition automation attributes', exc_info=True)

    return extra_attrs
