"""
Stability360 Actions — CharityTracker Payload Builder + SES Email (MCP Tool 3)

Assembles structured intake data into an HTML email payload and sends it
via Amazon SES to the configured CharityTracker inbox.

Demo mode:  Sends to a test email address (SES sandbox — verified recipients only).
Production: Sends to the real CharityTracker inbox (requires SES production access).

Every submission is stored in DynamoDB for audit.
"""

import html
import json
import os
import uuid
import logging
from datetime import datetime, timezone

import boto3

from case_creator import create_intake_case

logger = logging.getLogger('charitytracker_payload')

TABLE_NAME = os.environ.get('ACTIONS_TABLE_NAME', '')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
SES_SENDER_EMAIL = os.environ.get('SES_SENDER_EMAIL', 'godwill.achu.cho@gmail.com')
CHARITYTRACKER_RECIPIENT = os.environ.get(
    'CHARITYTRACKER_RECIPIENT_EMAIL',
    'godwill.achu.cho@gmail.com',
)

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None
ses_client = boto3.client('ses')

# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ['client_name', 'need_category', 'zip_code', 'county']


def _validate(body):
    """Validate required fields are present."""
    missing = [f for f in REQUIRED_FIELDS if not body.get(f)]
    if missing:
        raise ValueError(f'Missing required fields: {", ".join(missing)}')


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------


def _build_html_email(body):
    """Build structured HTML email from session data."""
    client_name = html.escape(str(body.get('client_name', 'Unknown')))
    need_category = html.escape(str(body.get('need_category', 'General')))
    subcategories = body.get('subcategories', [])
    zip_code = html.escape(str(body.get('zip_code', '')))
    county = html.escape(str(body.get('county', '')))
    contact_method = html.escape(str(body.get('contact_method', 'Not provided')))
    contact_info = html.escape(str(body.get('contact_info', 'Not provided')))
    escalation_tier = html.escape(str(body.get('escalation_tier', 'unknown')))
    conversation_summary = html.escape(str(body.get('conversation_summary', '')))
    intake_answers = body.get('intake_answers', {})
    extended_intake = body.get('extended_intake', {})
    timestamp = html.escape(str(body.get('timestamp', datetime.now(timezone.utc).isoformat())))

    subcats_html = ', '.join(html.escape(str(s)) for s in subcategories) if subcategories else 'N/A'

    # Build intake answers table rows
    intake_rows = ''
    for key, value in intake_answers.items():
        label = html.escape(key.replace('_', ' ').title())
        safe_value = html.escape(str(value))
        intake_rows += f'<tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">{label}</td>'
        intake_rows += f'<td style="padding:6px;border:1px solid #ddd">{safe_value}</td></tr>'

    extended_rows = ''
    for key, value in extended_intake.items():
        label = html.escape(key.replace('_', ' ').title())
        safe_value = html.escape(str(value))
        extended_rows += f'<tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">{label}</td>'
        extended_rows += f'<td style="padding:6px;border:1px solid #ddd">{safe_value}</td></tr>'

    email_html = f"""
    <html>
    <body style="font-family:Arial,sans-serif;line-height:1.6;color:#333">
      <h2 style="color:#1a5276">Stability360 — {escalation_tier.replace('_', ' ').title()} Submission</h2>
      <p style="color:#666">Submitted: {timestamp}</p>

      <h3 style="color:#2c3e50">Client Information</h3>
      <table style="border-collapse:collapse;width:100%;max-width:600px">
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">Name</td>
            <td style="padding:6px;border:1px solid #ddd">{client_name}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">Need Category</td>
            <td style="padding:6px;border:1px solid #ddd">{need_category}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">Subcategories</td>
            <td style="padding:6px;border:1px solid #ddd">{subcats_html}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">ZIP Code</td>
            <td style="padding:6px;border:1px solid #ddd">{zip_code}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">County</td>
            <td style="padding:6px;border:1px solid #ddd">{county}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">Contact Method</td>
            <td style="padding:6px;border:1px solid #ddd">{contact_method}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">Contact Info</td>
            <td style="padding:6px;border:1px solid #ddd">{contact_info}</td></tr>
        <tr><td style="padding:6px;border:1px solid #ddd;font-weight:bold">Escalation Tier</td>
            <td style="padding:6px;border:1px solid #ddd">{escalation_tier}</td></tr>
      </table>

      {'<h3 style="color:#2c3e50">Intake Answers</h3><table style="border-collapse:collapse;width:100%;max-width:600px">' + intake_rows + '</table>' if intake_rows else ''}

      {'<h3 style="color:#2c3e50">Extended Intake</h3><table style="border-collapse:collapse;width:100%;max-width:600px">' + extended_rows + '</table>' if extended_rows else ''}

      {'<h3 style="color:#2c3e50">Conversation Summary</h3><p style="background:#f8f9fa;padding:12px;border-radius:4px">' + conversation_summary + '</p>' if conversation_summary else ''}

      <hr style="border:none;border-top:1px solid #ddd;margin:20px 0">
      <p style="color:#999;font-size:12px">
        This submission was generated by the Stability360 AI intake system.
        Environment: {ENVIRONMENT}
      </p>
    </body>
    </html>
    """
    return email_html


# ---------------------------------------------------------------------------
# SES sender
# ---------------------------------------------------------------------------


def _send_email(subject, html_body, recipient=None):
    """Send HTML email via SES. Returns message ID or None on failure."""
    recipient = recipient or CHARITYTRACKER_RECIPIENT

    try:
        resp = ses_client.send_email(
            Source=SES_SENDER_EMAIL,
            Destination={'ToAddresses': [recipient]},
            Message={
                'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                'Body': {'Html': {'Data': html_body, 'Charset': 'UTF-8'}},
            },
        )
        message_id = resp.get('MessageId', '')
        logger.info('Email sent: %s → %s (MessageId: %s)', SES_SENDER_EMAIL, recipient, message_id)
        return message_id
    except Exception:
        logger.error('SES send failed', exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_charitytracker(body):
    """Build CharityTracker payload, send via SES, store in DynamoDB."""

    if not body:
        raise ValueError('Request body is required')

    _validate(body)

    record_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    body['timestamp'] = body.get('timestamp', timestamp)

    client_name = body.get('client_name', 'Unknown')
    need_category = body.get('need_category', 'General')
    county = body.get('county', 'Unknown')
    escalation_tier = body.get('escalation_tier', 'unknown')

    subject = (
        f'Stability360 — {escalation_tier.replace("_", " ").title()} | '
        f'{need_category.title()} | {county} County'
    )

    html_body = _build_html_email(body)

    # Send email (skip if SES sender is not configured or not verified)
    message_id = None
    if SES_SENDER_EMAIL and CHARITYTRACKER_RECIPIENT:
        message_id = _send_email(subject, html_body)
    else:
        logger.info('SES email skipped — sender/recipient not configured')
    sent = message_id is not None

    payload_summary = (
        f'{escalation_tier.replace("_", " ").title()} submission '
        f'for {need_category}/{", ".join(body.get("subcategories", []))} '
        f'in {county} County'
    )

    # Store in DynamoDB
    if table:
        try:
            table.put_item(Item={
                'record_id': record_id,
                'record_type': 'submission',
                'created_at': timestamp,
                'environment': ENVIRONMENT,
                'client_name': client_name,
                'need_category': need_category,
                'county': county,
                'escalation_tier': escalation_tier,
                'email_sent': sent,
                'ses_message_id': message_id or '',
                'payload_summary': payload_summary,
                'submission_data': json.loads(json.dumps(body, default=str)),
            })
            logger.info('Submission stored: %s', record_id)
        except Exception:
            logger.error('Failed to store submission', exc_info=True)

    # Create Connect Case for all submissions
    case_id = None
    case_reference = ''
    profile_id = body.get('profile_id', '')
    try:
        case_id, case_reference = create_intake_case(body, profile_id=profile_id or None)
        if case_id:
            logger.info('Connect Case created for %s: %s (ref: %s, profile: %s)',
                        escalation_tier, case_id, case_reference, profile_id or 'none')
    except Exception:
        logger.error('Failed to create Connect Case', exc_info=True)

    return {
        'record_id': record_id,
        'sent': sent,
        'message_id': message_id or '',
        'payload_summary': payload_summary,
        'case_id': case_id or '',
        'case_reference': case_reference or '',
    }
