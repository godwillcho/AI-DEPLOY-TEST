"""
Stability360 Actions — Amazon Connect Cases Integration

Shared module for creating and updating cases in Amazon Connect Cases.
Used by charitytracker_payload.py and followup_scheduler.py to automatically
create cases for direct_support and mixed paths.

Demo mode:  Returns simulated case IDs (no real Connect Cases API calls).
Production: Creates real cases via the Connect Cases API.
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger('case_creator')

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')
TABLE_NAME = os.environ.get('ACTIONS_TABLE_NAME', '')

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# Module-level cache for domain and template IDs
_cached_domain_id = None
_cached_template_id = None


# ---------------------------------------------------------------------------
# Domain and template discovery
# ---------------------------------------------------------------------------


def _get_cases_domain_id():
    """Look up the Cases domain ID for the Connect instance.

    Caches the result at module level. Returns None if Cases is not
    enabled on this Connect instance.
    """
    global _cached_domain_id
    if _cached_domain_id:
        return _cached_domain_id

    if not CONNECT_INSTANCE_ID:
        logger.warning('CONNECT_INSTANCE_ID not set — cannot look up Cases domain')
        return None

    try:
        connect_client = boto3.client('connect')
        paginator = connect_client.get_paginator('list_integration_associations')
        for page in paginator.paginate(
            InstanceId=CONNECT_INSTANCE_ID,
            IntegrationType='CASES_DOMAIN',
        ):
            for assoc in page.get('IntegrationAssociationSummaryList', []):
                arn = assoc.get('IntegrationArn', '')
                # ARN format: arn:aws:cases:<region>:<account>:domain/<domain-id>
                if '/domain/' in arn:
                    domain_id = arn.split('/domain/')[-1]
                elif '/' in arn:
                    domain_id = arn.split('/')[-1]
                else:
                    domain_id = arn
                _cached_domain_id = domain_id
                logger.info('Cases domain found: %s', domain_id)
                return domain_id
    except ClientError:
        logger.warning('Could not look up Cases domain', exc_info=True)

    logger.info('No Cases domain found for instance %s', CONNECT_INSTANCE_ID)
    return None


def _get_template_id(cases_client, domain_id):
    """Find a case template to use.

    Looks for a template named 'Stability360 Intake', falls back to
    the first available template. Caches the result.
    """
    global _cached_template_id
    if _cached_template_id:
        return _cached_template_id

    try:
        resp = cases_client.list_templates(domainId=domain_id)
        templates = resp.get('templates', [])
        for t in templates:
            if 'stability360' in t.get('name', '').lower():
                _cached_template_id = t['templateId']
                logger.info('Using template: %s (%s)', t['name'], _cached_template_id)
                return _cached_template_id
        # Fall back to first template
        if templates:
            _cached_template_id = templates[0]['templateId']
            logger.info('Using default template: %s (%s)',
                        templates[0].get('name', 'unnamed'), _cached_template_id)
            return _cached_template_id
    except ClientError:
        logger.warning('Could not list case templates', exc_info=True)

    return None


# ---------------------------------------------------------------------------
# Field discovery
# ---------------------------------------------------------------------------


def _get_system_field_ids(cases_client, domain_id):
    """Get field IDs for the standard system fields (title, status, etc.)."""
    field_map = {}
    try:
        resp = cases_client.list_fields(domainId=domain_id)
        for field in resp.get('fields', []):
            name = field.get('name', '').lower()
            field_map[name] = field['fieldId']
    except ClientError:
        logger.warning('Could not list case fields', exc_info=True)
    return field_map


# ---------------------------------------------------------------------------
# Case reference generation
# ---------------------------------------------------------------------------


def _generate_demo_reference():
    """Generate a simulated case reference number for demo/dev mode.

    Mimics the native Connect Cases format: an 8-digit numeric string.
    """
    import random
    return str(random.randint(10000000, 99999999))


def _fetch_native_reference(cases_client, domain_id, case_id):
    """Fetch the auto-generated reference_number from Connect Cases.

    Connect Cases generates a numeric reference_number for each case,
    but it is not returned by CreateCase — we must call GetCase to
    retrieve it.

    Returns the reference_number string or None on failure.
    """
    try:
        resp = cases_client.get_case(
            domainId=domain_id,
            caseId=case_id,
            fields=[{'id': 'reference_number'}],
        )
        for field in resp.get('fields', []):
            val = field.get('value', {})
            ref = val.get('stringValue', '')
            if ref:
                logger.info('Native case reference: %s for case %s', ref, case_id)
                return ref
    except Exception:
        logger.warning('Could not fetch native reference_number for case %s',
                       case_id, exc_info=True)
    return None


def _store_case_reference(case_reference, case_id, data, profile_id=None):
    """Store case reference mapping in DynamoDB for status lookups."""
    if not table:
        logger.warning('DynamoDB table not configured — skipping case reference storage')
        return

    try:
        table.put_item(Item={
            'record_id': case_reference,
            'record_type': 'case_reference',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'environment': ENVIRONMENT,
            'case_id': case_id,
            'client_name': data.get('client_name', 'Unknown'),
            'need_category': data.get('need_category', 'General'),
            'escalation_tier': data.get('escalation_tier', 'unknown'),
            'contact_info': data.get('contact_info', ''),
            'contact_method': data.get('contact_method', ''),
            'county': data.get('county', ''),
            'profile_id': profile_id or '',
            'status': 'open',
        })
        logger.info('Case reference stored: %s → %s', case_reference, case_id)
    except Exception:
        logger.error('Failed to store case reference', exc_info=True)


# ---------------------------------------------------------------------------
# Case creation
# ---------------------------------------------------------------------------


def create_intake_case(data, profile_id=None):
    """Create a Connect Case for an intake submission.

    Args:
        data: dict with keys like client_name, need_category, county,
              contact_info, escalation_tier, intake_answers, etc.
        profile_id: Optional customer profile ID to associate with the case.

    Returns:
        (case_id, case_reference) tuple. case_id or case_reference may be
        None on failure.
    """
    if ENVIRONMENT == 'dev':
        demo_id = f'demo_case_{uuid.uuid4().hex[:12]}'
        case_reference = _generate_demo_reference()
        logger.info('Demo mode — simulated case: %s, ref: %s (profile: %s)',
                     demo_id, case_reference, profile_id or 'none')
        _store_case_reference(case_reference, demo_id, data, profile_id)
        return demo_id, case_reference

    domain_id = _get_cases_domain_id()
    if not domain_id:
        logger.info('Cases not available — skipping case creation')
        case_reference = _generate_demo_reference()
        _store_case_reference(case_reference, '', data, profile_id)
        return None, case_reference

    try:
        cases_client = boto3.client('connectcases')
        template_id = _get_template_id(cases_client, domain_id)
        if not template_id:
            logger.warning('No case template found — skipping case creation')
            case_reference = _generate_demo_reference()
            _store_case_reference(case_reference, '', data, profile_id)
            return None, case_reference

        # Build case title
        client_name = data.get('client_name', 'Unknown')
        need_category = data.get('need_category', 'General')
        escalation_tier = data.get('escalation_tier', 'unknown')
        title = (
            f'Stability360 — {escalation_tier.replace("_", " ").title()} | '
            f'{need_category.title()} | {client_name}'
        )

        # Build case fields — use title field at minimum
        field_map = _get_system_field_ids(cases_client, domain_id)
        fields = []

        title_field_id = field_map.get('title')
        if title_field_id:
            fields.append({
                'id': title_field_id,
                'value': {'stringValue': title[:500]},
            })

        # Create the case
        create_kwargs = {
            'domainId': domain_id,
            'templateId': template_id,
            'fields': fields,
        }

        # Associate with customer profile if available
        if profile_id:
            create_kwargs['clientToken'] = str(uuid.uuid4())
            # Add customer_id field if it exists in the template
            customer_field_id = field_map.get('customer_id')
            if customer_field_id:
                fields.append({
                    'id': customer_field_id,
                    'value': {'stringValue': profile_id},
                })
            logger.info('Associating case with profile: %s', profile_id)

        resp = cases_client.create_case(**create_kwargs)
        case_id = resp.get('caseId', '')
        logger.info('Connect Case created: %s', case_id)

        # Fetch the native reference_number generated by Connect Cases
        case_reference = None
        if case_id:
            case_reference = _fetch_native_reference(cases_client, domain_id, case_id)
        if not case_reference:
            # Fallback: generate a numeric reference if fetch fails
            case_reference = _generate_demo_reference()
            logger.warning('Using fallback reference %s for case %s', case_reference, case_id)

        logger.info('Case reference: %s for case %s', case_reference, case_id)

        # Add detailed intake data as a comment
        if case_id:
            comment_body = _build_case_comment(data)
            comment_body = f'Case Reference: {case_reference}\n\n{comment_body}'
            add_case_comment(case_id, comment_body)

        _store_case_reference(case_reference, case_id, data, profile_id)
        return case_id, case_reference

    except Exception:
        logger.error('Failed to create Connect Case', exc_info=True)
        case_reference = _generate_demo_reference()
        _store_case_reference(case_reference, '', data, profile_id)
        return None, case_reference


def _build_case_comment(data):
    """Build a detailed comment body from intake data."""
    lines = [
        f'Client: {data.get("client_name", "Unknown")}',
        f'Need Category: {data.get("need_category", "N/A")}',
        f'Subcategories: {", ".join(data.get("subcategories", [])) or "N/A"}',
        f'County: {data.get("county", "N/A")}',
        f'ZIP Code: {data.get("zip_code", "N/A")}',
        f'Contact Method: {data.get("contact_method", "N/A")}',
        f'Contact Info: {data.get("contact_info", "N/A")}',
        f'Escalation Tier: {data.get("escalation_tier", "N/A")}',
    ]

    # Add intake answers
    intake_answers = data.get('intake_answers', {})
    if intake_answers:
        lines.append('')
        lines.append('--- Intake Answers ---')
        for key, value in intake_answers.items():
            label = key.replace('_', ' ').title()
            lines.append(f'{label}: {value}')

    # Add extended intake
    extended_intake = data.get('extended_intake', {})
    if extended_intake:
        lines.append('')
        lines.append('--- Extended Intake ---')
        for key, value in extended_intake.items():
            label = key.replace('_', ' ').title()
            lines.append(f'{label}: {value}')

    # Add conversation summary
    summary = data.get('conversation_summary', '')
    if summary:
        lines.append('')
        lines.append('--- Conversation Summary ---')
        lines.append(summary)

    # Add scoring data if present
    scoring = data.get('scoring_results', {})
    if scoring:
        lines.append('')
        lines.append('--- Scoring Results ---')
        lines.append(f'Housing Score: {scoring.get("housing_score", "N/A")}')
        lines.append(f'Employment Score: {scoring.get("employment_score", "N/A")}')
        lines.append(f'Financial Score: {scoring.get("financial_resilience_score", "N/A")}')
        lines.append(f'Composite Score: {scoring.get("composite_score", "N/A")}')
        lines.append(f'Priority Flag: {scoring.get("priority_flag", "N/A")}')
        lines.append(f'Recommended Path: {scoring.get("recommended_path", "N/A")}')

    # Add scoring input data if present
    scoring_inputs = data.get('scoring_inputs', {})
    # Also check inside extended_intake for scoring_inputs
    if not scoring_inputs:
        ext = data.get('extended_intake', {})
        if isinstance(ext, dict):
            scoring_inputs = ext.get('scoring_inputs', {})
    if scoring_inputs and isinstance(scoring_inputs, dict):
        lines.append('')
        lines.append('--- Scoring Input Data ---')
        input_labels = {
            'housing_situation': 'Housing Situation',
            'monthly_income': 'Monthly Income',
            'monthly_housing_cost': 'Monthly Housing Cost',
            'employment_status': 'Employment Status',
            'housing_challenges': 'Housing Challenges',
            'has_benefits': 'Has Benefits',
            'monthly_expenses': 'Monthly Expenses',
            'savings_rate': 'Savings Rate',
            'fico_range': 'FICO Range',
        }
        for key, label in input_labels.items():
            if key in scoring_inputs:
                val = scoring_inputs[key]
                if isinstance(val, list):
                    val = ', '.join(str(v) for v in val)
                lines.append(f'{label}: {val}')

    # Also check inside extended_intake for scoring_results
    if not scoring:
        ext = data.get('extended_intake', {})
        if isinstance(ext, dict):
            scoring = ext.get('scoring_results', {})
        if scoring and isinstance(scoring, dict):
            lines.append('')
            lines.append('--- Scoring Results ---')
            lines.append(f'Housing Score: {scoring.get("housing_score", "N/A")}')
            lines.append(f'Employment Score: {scoring.get("employment_score", "N/A")}')
            lines.append(f'Financial Score: {scoring.get("financial_resilience_score", "N/A")}')
            lines.append(f'Composite Score: {scoring.get("composite_score", "N/A")}')
            lines.append(f'Priority Flag: {scoring.get("priority_flag", "N/A")}')
            lines.append(f'Recommended Path: {scoring.get("recommended_path", "N/A")}')

    # Add profile info if present
    profile_id = data.get('profile_id', '')
    if profile_id:
        lines.append('')
        lines.append(f'Customer Profile: {profile_id}')

    lines.append('')
    lines.append(f'Submitted: {datetime.now(timezone.utc).isoformat()}')
    lines.append(f'Environment: {ENVIRONMENT}')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Case comments (related items)
# ---------------------------------------------------------------------------


def get_case_by_reference(case_reference):
    """Look up a case by its user-friendly reference number.

    Returns a dict with case details or None if not found.
    """
    if not table:
        logger.warning('DynamoDB table not configured')
        return None

    try:
        resp = table.get_item(Key={'record_id': case_reference})
        item = resp.get('Item')
        if not item or item.get('record_type') != 'case_reference':
            logger.info('Case reference not found: %s', case_reference)
            return None
        logger.info('Case reference found: %s → %s', case_reference, item.get('case_id', ''))
        return item
    except Exception:
        logger.error('Failed to look up case reference', exc_info=True)
        return None


def get_connect_case_status(case_id):
    """Get the status of a Connect Case by its case ID.

    Returns a dict with case fields or None if unavailable.
    """
    if ENVIRONMENT == 'dev':
        logger.info('Demo mode — returning simulated case status for %s', case_id)
        return {'status': 'open', 'source': 'demo'}

    if not case_id or case_id.startswith('demo_case_'):
        return None

    domain_id = _get_cases_domain_id()
    if not domain_id:
        return None

    try:
        cases_client = boto3.client('connectcases')
        resp = cases_client.get_case(
            domainId=domain_id,
            caseId=case_id,
            fields=[],
        )
        case_fields = resp.get('fields', [])
        logger.info('Connect Case status retrieved for %s', case_id)

        # Extract status from fields
        status_value = 'open'
        title_value = ''
        for field in case_fields:
            field_val = field.get('value', {})
            field_name = field.get('name', '').lower() if 'name' in field else ''
            if field_name == 'status' or 'status' in str(field.get('id', '')).lower():
                status_value = field_val.get('stringValue', status_value)
            if field_name == 'title' or 'title' in str(field.get('id', '')).lower():
                title_value = field_val.get('stringValue', '')

        return {
            'status': status_value,
            'title': title_value,
            'source': 'connect_cases',
        }
    except Exception:
        logger.error('Failed to get Connect Case status', exc_info=True)
        return None


def add_case_comment(case_id, comment_text):
    """Add a comment to an existing Connect Case.

    Args:
        case_id: The Connect Case ID.
        comment_text: Plain text comment to add.

    Returns:
        True on success, False on failure.
    """
    if ENVIRONMENT == 'dev':
        logger.info('Demo mode — simulated comment on case %s', case_id)
        return True

    if not case_id or case_id.startswith('demo_case_'):
        logger.info('Skipping comment — case_id is demo or empty')
        return False

    domain_id = _get_cases_domain_id()
    if not domain_id:
        return False

    try:
        cases_client = boto3.client('connectcases')
        cases_client.create_related_item(
            domainId=domain_id,
            caseId=case_id,
            type='Comment',
            content={
                'comment': {
                    'body': comment_text[:1500],
                    'contentType': 'Text/Plain',
                }
            },
        )
        logger.info('Comment added to case %s', case_id)
        return True
    except Exception:
        logger.error('Failed to add comment to case %s', case_id, exc_info=True)
        return False
