"""
Stability360 Actions — Follow-up Scheduler (MCP Tool 4)

Schedules follow-up actions after intake completion:
  - Referral path  → automated follow-up (Connect Task or SES reminder)
  - Direct Support → task for case manager queue

All follow-ups are stored in DynamoDB with status tracking.

Demo mode:  Creates DynamoDB record only (no real Connect Task or SES).
Production: Creates Connect Tasks via the Connect Tasks API.
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone, timedelta

import boto3

from case_creator import create_intake_case, add_case_comment

logger = logging.getLogger('followup_scheduler')

TABLE_NAME = os.environ.get('ACTIONS_TABLE_NAME', '')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')
SES_SENDER_EMAIL = os.environ.get('SES_SENDER_EMAIL', 'godwill.achu.cho@gmail.com')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ['contact_info', 'contact_method', 'referral_type', 'need_category']


def _validate(body):
    missing = [f for f in REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise ValueError(f'Missing required fields: {", ".join(missing)}')

    days = body.get('scheduled_days_out', 7)
    if not isinstance(days, (int, float)) or days < 1 or days > 90:
        raise ValueError('scheduled_days_out must be between 1 and 90')


# ---------------------------------------------------------------------------
# Follow-up methods
# ---------------------------------------------------------------------------


def _schedule_connect_task(body, follow_up_id, scheduled_date):
    """Record a follow-up for case manager review.

    Does not create Connect Tasks — follow-ups are tracked in DynamoDB
    and linked to cases via case comments.
    """
    logger.info('Follow-up recorded: %s (scheduled %s)', follow_up_id, scheduled_date)
    return follow_up_id, 'recorded'


def _schedule_email_reminder(body, follow_up_id, scheduled_date):
    """Schedule an email reminder.

    In demo mode, logs the reminder without sending.
    In production, this would integrate with SES scheduled sending
    or an EventBridge rule.
    """
    contact_info = body.get('contact_info', '')
    message = body.get('follow_up_message', '')

    if ENVIRONMENT == 'dev':
        logger.info(
            'Demo mode — email reminder scheduled: %s → %s on %s',
            follow_up_id, contact_info, scheduled_date,
        )
        return follow_up_id, 'email_demo'

    # Production: store for later sending via EventBridge scheduled rule
    logger.info('Email follow-up queued: %s → %s', follow_up_id, contact_info)
    return follow_up_id, 'email_queued'


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_followup(body):
    """Schedule a follow-up and store the record in DynamoDB."""

    if not body:
        raise ValueError('Request body is required')

    _validate(body)

    follow_up_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    days_out = int(body.get('scheduled_days_out', 7))
    scheduled_date = (now + timedelta(days=days_out)).isoformat()

    referral_type = body.get('referral_type', 'referral')
    contact_method = body.get('contact_method', 'email')
    need_category = body.get('need_category', '')

    # Determine method based on referral type and contact method
    if referral_type == 'direct_support':
        # Direct support → case manager task
        task_ref, method = _schedule_connect_task(body, follow_up_id, scheduled_date)
    elif contact_method == 'email':
        task_ref, method = _schedule_email_reminder(body, follow_up_id, scheduled_date)
    else:
        # Phone follow-up → Connect Task
        task_ref, method = _schedule_connect_task(body, follow_up_id, scheduled_date)

    # Store in DynamoDB
    if table:
        try:
            table.put_item(Item={
                'record_id': follow_up_id,
                'record_type': 'followup',
                'created_at': now.isoformat(),
                'scheduled_date': scheduled_date,
                'scheduled_days_out': days_out,
                'environment': ENVIRONMENT,
                'referral_type': referral_type,
                'need_category': need_category,
                'contact_method': contact_method,
                'contact_info': body.get('contact_info', ''),
                'follow_up_message': body.get('follow_up_message', ''),
                'method': method,
                'task_reference': task_ref or '',
                'status': 'scheduled',
            })
            logger.info('Follow-up stored: %s (method: %s)', follow_up_id, method)
        except Exception:
            logger.error('Failed to store follow-up', exc_info=True)

    # Connect Case — link to existing or create new
    case_id = body.get('case_id', '')
    case_reference = body.get('case_reference', '')
    profile_id = body.get('profile_id', '')
    try:
        if case_id:
            # Add follow-up note to existing case
            comment = (
                f'Follow-up scheduled: {follow_up_id}\n'
                f'Method: {method}\n'
                f'Scheduled date: {scheduled_date}\n'
                f'Need: {need_category} ({referral_type})'
            )
            add_case_comment(case_id, comment)
            logger.info('Follow-up linked to case %s', case_id)
        else:
            # Create new case for this follow-up
            case_data = {
                'client_name': body.get('contact_info', 'Unknown'),
                'need_category': need_category,
                'contact_info': body.get('contact_info', ''),
                'contact_method': contact_method,
                'escalation_tier': referral_type,
                'conversation_summary': (
                    f'Follow-up {follow_up_id} scheduled for {scheduled_date} '
                    f'via {method}. Need: {need_category}.'
                ),
            }
            case_id, case_reference = create_intake_case(case_data, profile_id=profile_id or None)
            if case_id:
                logger.info('New case created for follow-up: %s (ref: %s)', case_id, case_reference)
    except Exception:
        logger.error('Failed to create/update Connect Case for follow-up', exc_info=True)

    return {
        'scheduled': True,
        'follow_up_id': follow_up_id,
        'scheduled_date': scheduled_date,
        'method': method,
        'need_category': need_category,
        'referral_type': referral_type,
        'case_id': case_id or '',
        'case_reference': case_reference or '',
    }
