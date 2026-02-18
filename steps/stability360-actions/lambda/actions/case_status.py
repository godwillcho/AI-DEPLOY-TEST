"""
Stability360 Actions — Case Status Lookup (MCP Tool 5)

Allows clients to check the status of their case using the case reference
number provided by Amazon Connect Cases (a numeric reference).

Looks up the case reference in DynamoDB. If Amazon Connect Cases is enabled,
also retrieves the live case status from Connect.

Demo mode:  Returns simulated case status from DynamoDB.
Production: Returns live status from Connect Cases + DynamoDB metadata.
"""

import logging
import os

from case_creator import get_case_by_reference, get_connect_case_status

logger = logging.getLogger('case_status')

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ['case_reference']


def _validate(body):
    missing = [f for f in REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise ValueError(f'Missing required fields: {", ".join(missing)}')


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_case_status(body):
    """Look up a case by reference number and return its status."""

    if not body:
        raise ValueError('Request body is required')

    _validate(body)

    case_reference = body.get('case_reference', '').strip()
    logger.info('Case status lookup: %s', case_reference)

    # Look up in DynamoDB
    case_record = get_case_by_reference(case_reference)

    if not case_record:
        logger.info('Case reference not found: %s', case_reference)
        return {
            'found': False,
            'case_reference': case_reference,
            'message': (
                'I was not able to find a case with that reference number. '
                'Please double-check the reference and try again, or I can '
                'connect you with a team member for help.'
            ),
        }

    case_id = case_record.get('case_id', '')
    client_name = case_record.get('client_name', 'Unknown')
    need_category = case_record.get('need_category', 'General')
    escalation_tier = case_record.get('escalation_tier', 'unknown')
    created_at = case_record.get('created_at', '')
    stored_status = case_record.get('status', 'open')
    county = case_record.get('county', '')

    # Try to get live status from Connect Cases
    live_status = None
    if case_id:
        live_status = get_connect_case_status(case_id)

    # Determine final status
    if live_status:
        status = live_status.get('status', stored_status)
        status_source = live_status.get('source', 'unknown')
    else:
        status = stored_status
        status_source = 'dynamo'

    # Build user-friendly status description
    status_descriptions = {
        'open': 'Your case is open and being reviewed by our team.',
        'in_progress': 'Your case is currently being worked on by a case manager.',
        'pending': 'Your case is pending additional information or review.',
        'resolved': 'Your case has been resolved. If you need further help, please let us know.',
        'closed': 'Your case has been closed. If you need further assistance, we can open a new case.',
    }
    status_description = status_descriptions.get(
        status.lower(),
        f'Your case status is: {status}.',
    )

    logger.info('Case status result: ref=%s, status=%s (source=%s)',
                case_reference, status, status_source)

    return {
        'found': True,
        'case_reference': case_reference,
        'status': status,
        'status_description': status_description,
        'need_category': need_category,
        'escalation_tier': escalation_tier,
        'created_at': created_at,
        'county': county,
        'message': (
            f'I found your case, {client_name}. {status_description} '
            f'Your case is for {need_category.lower()} assistance'
            f'{" in " + county + " County" if county else ""}. '
            f'Is there anything else I can help you with?'
        ),
    }
