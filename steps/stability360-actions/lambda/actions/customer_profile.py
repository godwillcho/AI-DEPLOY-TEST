"""
Stability360 Actions — Customer Profile Lookup & Creation (MCP Tool 5)

Searches Amazon Connect Customer Profiles for existing customers by email
or phone number. If no match is found, creates a new profile.

Used at the start of an intake conversation after the client consents
to data collection and provides basic contact information.

Demo mode:  Simulates profile lookup/creation (no real API calls).
Production: Uses Amazon Connect Customer Profiles API.
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger('customer_profile')

TABLE_NAME = os.environ.get('ACTIONS_TABLE_NAME', '')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# Module-level cache for domain name
_cached_domain_name = None

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ['first_name', 'last_name']


def _validate(body):
    missing = [f for f in REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise ValueError(f'Missing required fields: {", ".join(missing)}')

    # Must have at least one contact method
    if not body.get('email') and not body.get('phone_number'):
        raise ValueError('At least one contact method (email or phone_number) is required')


# ---------------------------------------------------------------------------
# Customer Profiles domain discovery
# ---------------------------------------------------------------------------


def _get_domain_name():
    """Discover the Customer Profiles domain name for this Connect instance."""
    global _cached_domain_name
    if _cached_domain_name:
        return _cached_domain_name

    if not CONNECT_INSTANCE_ID:
        logger.warning('CONNECT_INSTANCE_ID not set — cannot discover domain')
        return None

    try:
        connect_client = boto3.client('connect')
        paginator = connect_client.get_paginator('list_integration_associations')
        for page in paginator.paginate(
            InstanceId=CONNECT_INSTANCE_ID,
            IntegrationType='CUSTOMER_PROFILES_DOMAIN',
        ):
            for assoc in page.get('IntegrationAssociationSummaryList', []):
                arn = assoc.get('IntegrationArn', '')
                # ARN format: arn:aws:profile:<region>:<account>:domains/<domain-name>
                if '/domains/' in arn:
                    domain_name = arn.split('/domains/')[-1]
                else:
                    domain_name = arn.split('/')[-1]
                _cached_domain_name = domain_name
                logger.info('Customer Profiles domain found: %s', domain_name)
                return domain_name
    except ClientError:
        logger.warning('Could not discover Customer Profiles domain', exc_info=True)

    logger.info('No Customer Profiles domain found for instance %s', CONNECT_INSTANCE_ID)
    return None


# ---------------------------------------------------------------------------
# Profile search
# ---------------------------------------------------------------------------


def _search_profiles(profiles_client, domain_name, email=None, phone=None):
    """Search for existing customer profiles by email or phone."""
    matches = []

    # Search by email
    if email:
        try:
            resp = profiles_client.search_profiles(
                DomainName=domain_name,
                KeyName='_email',
                Values=[email],
            )
            matches.extend(resp.get('Items', []))
        except ClientError:
            logger.debug('Email search failed', exc_info=True)

    # Search by phone (if no email match found)
    if not matches and phone:
        try:
            resp = profiles_client.search_profiles(
                DomainName=domain_name,
                KeyName='_phone',
                Values=[phone],
            )
            matches.extend(resp.get('Items', []))
        except ClientError:
            logger.debug('Phone search failed', exc_info=True)

    return matches


# ---------------------------------------------------------------------------
# Profile creation
# ---------------------------------------------------------------------------


def _create_profile(profiles_client, domain_name, data):
    """Create a new customer profile."""
    profile_kwargs = {
        'DomainName': domain_name,
        'FirstName': data.get('first_name', ''),
        'LastName': data.get('last_name', ''),
    }

    if data.get('email'):
        profile_kwargs['EmailAddress'] = data['email']
    if data.get('phone_number'):
        profile_kwargs['PhoneNumber'] = data['phone_number']

    resp = profiles_client.create_profile(**profile_kwargs)
    profile_id = resp.get('ProfileId', '')
    logger.info('Customer profile created: %s', profile_id)
    return profile_id


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_customer_profile(body):
    """Look up or create a customer profile.

    Returns profile info including whether the customer is new or returning.
    """
    if not body:
        raise ValueError('Request body is required')

    _validate(body)

    first_name = body.get('first_name', '')
    last_name = body.get('last_name', '')
    email = body.get('email', '')
    phone_number = body.get('phone_number', '')

    record_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    # --- Demo mode ---
    if ENVIRONMENT == 'dev':
        demo_profile_id = f'demo_profile_{uuid.uuid4().hex[:12]}'
        logger.info('Demo mode — simulated profile: %s', demo_profile_id)

        result = {
            'profile_id': demo_profile_id,
            'is_returning': False,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone_number': phone_number,
            'message': f'Welcome, {first_name}! We have created your profile.',
            'sessionAttributes': {
                'profile_id': demo_profile_id,
            },
        }

        # Store in DynamoDB
        if table:
            try:
                table.put_item(Item={
                    'record_id': record_id,
                    'record_type': 'customer_profile',
                    'created_at': timestamp,
                    'environment': ENVIRONMENT,
                    'profile_id': demo_profile_id,
                    'is_returning': False,
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'phone_number': phone_number,
                })
            except Exception:
                logger.error('Failed to store profile record', exc_info=True)

        return result

    # --- Production mode ---
    domain_name = _get_domain_name()
    if not domain_name:
        logger.warning('Customer Profiles not available — returning basic info')
        return {
            'profile_id': '',
            'is_returning': False,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone_number': phone_number,
            'message': f'Welcome, {first_name}! Customer Profiles is not configured.',
            'sessionAttributes': {},
        }

    try:
        profiles_client = boto3.client('customer-profiles')

        # Search for existing profile
        matches = _search_profiles(profiles_client, domain_name, email, phone_number)

        if matches:
            # Returning customer
            profile = matches[0]
            profile_id = profile.get('ProfileId', '')
            existing_first = profile.get('FirstName', first_name)
            existing_last = profile.get('LastName', last_name)

            logger.info('Returning customer found: %s (%s %s)',
                        profile_id, existing_first, existing_last)

            result = {
                'profile_id': profile_id,
                'is_returning': True,
                'first_name': existing_first,
                'last_name': existing_last,
                'email': profile.get('EmailAddress', email),
                'phone_number': profile.get('PhoneNumber', phone_number),
                'message': (
                    f'Welcome back, {existing_first}! '
                    f'I see you have contacted us before. '
                    f'How can I help you today?'
                ),
                'sessionAttributes': {
                    'profile_id': profile_id,
                },
            }
        else:
            # New customer — create profile
            profile_id = _create_profile(profiles_client, domain_name, body)

            result = {
                'profile_id': profile_id,
                'is_returning': False,
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone_number': phone_number,
                'message': (
                    f'Welcome, {first_name}! '
                    f'I have created your profile so we can best assist you.'
                ),
                'sessionAttributes': {
                    'profile_id': profile_id,
                },
            }

        # Store in DynamoDB
        if table:
            try:
                table.put_item(Item={
                    'record_id': record_id,
                    'record_type': 'customer_profile',
                    'created_at': timestamp,
                    'environment': ENVIRONMENT,
                    'profile_id': result['profile_id'],
                    'is_returning': result['is_returning'],
                    'first_name': result['first_name'],
                    'last_name': result['last_name'],
                    'email': result.get('email', ''),
                    'phone_number': result.get('phone_number', ''),
                })
            except Exception:
                logger.error('Failed to store profile record', exc_info=True)

        return result

    except Exception:
        logger.error('Customer profile lookup/creation failed', exc_info=True)
        return {
            'profile_id': '',
            'is_returning': False,
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'phone_number': phone_number,
            'message': f'Welcome, {first_name}! I was unable to look up your profile, but I can still help you.',
            'sessionAttributes': {},
        }
