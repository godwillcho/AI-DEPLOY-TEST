"""
Stability360 — Case Updater Lambda

Invoked from the Amazon Connect contact flow after the Q Connect session ends.
Reads all contact attributes (including caseId), maps them to case field UUIDs
via CASE_FIELD_MAP, and calls connectcases:UpdateCase.

If no caseId is present in contact attributes, returns success (no-op).
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger('case_updater')
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

CONNECT_CASES_DOMAIN_ID = os.environ.get('CONNECT_CASES_DOMAIN_ID', '')
CONNECT_REGION = os.environ.get('CONNECT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))

_raw_field_map = os.environ.get('CASE_FIELD_MAP', '{}')
try:
    CASE_FIELD_MAP = json.loads(_raw_field_map)
except (json.JSONDecodeError, TypeError):
    CASE_FIELD_MAP = {}


def handler(event, context):
    """Main entry point — invoked by Amazon Connect contact flow."""

    logger.info('Event received: %s', json.dumps(event, default=str))

    # Extract contact attributes from Connect contact flow event
    contact_data = event.get('Details', {}).get('ContactData', {})
    attributes = contact_data.get('Attributes', {})

    if not attributes:
        logger.info('No contact attributes found — nothing to update.')
        return {'statusCode': 200, 'result': 'no_attributes'}

    case_id = attributes.get('caseId', '').strip()
    if not case_id:
        logger.info('No caseId in contact attributes — skipping case update.')
        return {'statusCode': 200, 'result': 'no_case'}

    if not CONNECT_CASES_DOMAIN_ID:
        logger.warning('CONNECT_CASES_DOMAIN_ID not set — cannot update case.')
        return {'statusCode': 200, 'result': 'no_domain'}

    if not CASE_FIELD_MAP:
        logger.warning('CASE_FIELD_MAP is empty — no fields to update.')
        return {'statusCode': 200, 'result': 'no_field_map'}

    # Build case update fields from contact attributes
    fields = []
    updated_keys = []
    for attr_key, field_id in CASE_FIELD_MAP.items():
        value = attributes.get(attr_key, '').strip()
        if value:
            fields.append({
                'id': field_id,
                'value': {'stringValue': value[:500]},
            })
            updated_keys.append(attr_key)

    if not fields:
        logger.info('No matching contact attributes for case fields — skipping.')
        return {'statusCode': 200, 'result': 'no_matching_fields'}

    # Update the case
    try:
        cases_client = boto3.client('connectcases', region_name=CONNECT_REGION)
        cases_client.update_case(
            domainId=CONNECT_CASES_DOMAIN_ID,
            caseId=case_id,
            fields=fields,
        )
        logger.info(
            'Case %s updated with %d fields: %s',
            case_id, len(fields), updated_keys,
        )
        return {
            'statusCode': 200,
            'result': 'updated',
            'caseId': case_id,
            'fieldsUpdated': len(fields),
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        logger.error('Failed to update case %s: %s — %s', case_id, error_code, e)
        return {
            'statusCode': 500,
            'result': 'error',
            'error': str(e),
        }

    except Exception as e:
        logger.error('Unexpected error updating case %s: %s', case_id, e, exc_info=True)
        return {
            'statusCode': 500,
            'result': 'error',
            'error': str(e),
        }
