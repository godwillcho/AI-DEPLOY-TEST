"""
Stability360 Actions -- Lambda Router

Single Lambda function handling 2 MCP action tools:
  1. POST /resources/search    -> sophia_resource_lookup.handle_resource_lookup
     (auto-scoring runs when housing/income/employment fields are present)
  2. POST /intake/helper       -> intake_helper.handle_intake_helper
     (validateZip, getRequiredFields, checkPartner)

Contact attribute persistence is handled automatically: when any tool call
includes instance_id + contact_id, recognized session attributes in the
request body are saved as Amazon Connect contact attributes after the
primary handler completes.

Invocation patterns handled:
  1. API Gateway          -- event.body (JSON string), event.resource / event.path
  2. AgentCore MCP        -- event.toolName + event.arguments
  3. Direct / test        -- event.action + event.payload
"""

import json
import logging
import os
import re

import boto3
from botocore.exceptions import ClientError

from intake_helper import handle_intake_helper, PARTNER_EMPLOYERS, EMPLOYER_CORRECTIONS
from scoring_calculator import handle_scoring
from sophia_resource_lookup import handle_resource_lookup
from task_manager import handle_disposition_automation

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# ---------------------------------------------------------------------------
# Logger -- structured JSON
# ---------------------------------------------------------------------------

logger = logging.getLogger('actions_router')
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'environment': ENVIRONMENT,
        }
        if hasattr(record, 'extra'):
            entry.update(record.extra)
        if record.exc_info and record.exc_info[0]:
            entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


for h in logger.handlers[:]:
    logger.removeHandler(h)
_handler = logging.StreamHandler()
_handler.setFormatter(StructuredFormatter())
logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Contact attribute persistence (router-level middleware)
# ---------------------------------------------------------------------------

CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')
CONNECT_REGION = os.environ.get('CONNECT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

# Session attribute keys recognized for contact attribute persistence.
# Maps request body keys to Connect contact attribute names.
ATTR_MAP = {
    # Core intake
    'firstName': 'firstName', 'lastName': 'lastName',
    'zipCode': 'zipCode', 'zip_code': 'zipCode',
    'contactMethod': 'contactMethod',
    'contactInfo': 'contactInfo',
    'phoneNumber': 'phoneNumber', 'emailAddress': 'emailAddress',
    'preferredDays': 'preferredDays', 'preferredTimes': 'preferredTimes',
    # Need
    'keyword': 'needCategory',
    # Demographics
    'age': 'age', 'hasChildrenUnder18': 'hasChildrenUnder18', 'childrenUnder18': 'hasChildrenUnder18',
    'employmentStatus': 'employmentStatus',
    'employer': 'employer',
    'militaryAffiliation': 'militaryAffiliation',
    'publicAssistance': 'publicAssistance',
    # Scoring inputs (camelCase from spec)
    'housingSituation': 'housingSituation',
    'monthlyIncome': 'monthlyIncome',
    'monthlyHousingCost': 'monthlyHousingCost',
    # Partner
    'partnerEmployee': 'partnerEmployee', 'partnerEmployer': 'partnerEmployer',
    # Routing
    'escalationRoute': 'escalationRoute',
    'priorityFlag': 'priorityFlag',
    # Disposition
    'disposition': 'callDisposition',
    # Task/profile/case results
    'taskCreated': 'taskCreated',
    'taskContactId': 'taskContactId',
    'customerProfileId': 'customerProfileId',
    'caseId': 'caseId',
}


def _save_contact_attributes(body, result, request_id):
    """Persist recognized session attributes as Connect contact attributes.

    Called automatically after every successful tool handler.  Requires
    either instance_id in body or CONNECT_INSTANCE_ID env var, plus
    contact_id in body.  Silently skips if either is missing.
    """
    raw_instance = body.get('instance_id') or CONNECT_INSTANCE_ID
    raw_contact = body.get('contact_id') or ''
    instance_id = raw_instance.strip() if raw_instance else ''
    contact_id = raw_contact.strip() if raw_contact else ''

    logger.info(
        'Contact attribute check — instance_id=%s, contact_id=%s, env_fallback=%s',
        body.get('instance_id', '<not in body>'),
        body.get('contact_id', '<not in body>'),
        CONNECT_INSTANCE_ID or '<not set>',
    )

    if not instance_id or not UUID_RE.match(instance_id):
        logger.warning(
            'Skipping contact attributes — invalid instance_id: %r',
            instance_id,
        )
        return
    if not contact_id or not UUID_RE.match(contact_id):
        logger.warning(
            'Skipping contact attributes — invalid contact_id: %r',
            contact_id,
        )
        return

    # Collect attributes from request body
    attributes = {}
    for body_key, attr_name in ATTR_MAP.items():
        value = body.get(body_key)
        if value is not None and str(value).strip():
            attributes[attr_name] = str(value).strip()

    # Collect scoring results from handler output (scores + descriptions)
    score_fields = {
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
    for result_key, attr_name in score_fields.items():
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


# ---------------------------------------------------------------------------
# Auto-scoring wrapper for resource lookup
# ---------------------------------------------------------------------------

# Only trigger auto-scoring when D-route fields are present.
# employmentStatus alone (R-route) should NOT trigger scoring.
SCORING_TRIGGER_FIELDS = {
    'housing_situation', 'monthly_income', 'monthly_housing_cost',
    'housingSituation', 'monthlyIncome', 'monthlyHousingCost',
}

# ---- Free-text to enum mappers for scoring ----

HOUSING_MAP = {
    'homeless': 'homeless', 'no housing': 'homeless', 'on the street': 'homeless',
    'shelter': 'shelter', 'emergency shelter': 'shelter',
    'couch surfing': 'couch_surfing', 'staying with friends': 'couch_surfing',
    'staying with family': 'couch_surfing', 'couch': 'couch_surfing',
    'temporary': 'temporary', 'temp': 'temporary', 'temp housing': 'temporary',
    'transitional': 'transitional', 'transitional housing': 'transitional',
    'renting unstable': 'renting_unstable', 'behind on rent': 'renting_unstable',
    'month to month': 'renting_month_to_month', 'month-to-month': 'renting_month_to_month',
    'renting': 'renting_stable', 'rent': 'renting_stable', 'renter': 'renting_stable',
    'renting stable': 'renting_stable', 'lease': 'renting_stable',
    'own with mortgage': 'owner_with_mortgage', 'mortgage': 'owner_with_mortgage',
    'homeowner with mortgage': 'owner_with_mortgage',
    'own': 'owner', 'homeowner': 'owner', 'owner': 'owner',
    'own no mortgage': 'owner_no_mortgage', 'paid off': 'owner_no_mortgage',
}

EMPLOYMENT_MAP = {
    'unable to work': 'unable_to_work', 'disabled': 'unable_to_work',
    'disability': 'unable_to_work', 'cannot work': 'unable_to_work',
    'unemployed': 'unemployed', 'not working': 'unemployed', 'no job': 'unemployed',
    'looking for work': 'unemployed', 'job seeking': 'unemployed',
    'gig': 'gig_work', 'gig work': 'gig_work', 'freelance': 'gig_work',
    'seasonal': 'seasonal', 'seasonal work': 'seasonal',
    'part time': 'part_time', 'part-time': 'part_time',
    'full time below standard': 'full_time_below_standard',
    'self employed': 'self_employed', 'self-employed': 'self_employed',
    'own business': 'self_employed',
    'student': 'student', 'in school': 'student',
    'retired': 'retired', 'retirement': 'retired',
    'full time': 'full_time', 'full-time': 'full_time', 'employed': 'full_time',
    'working': 'full_time',
    'full time above standard': 'full_time_above_standard',
}


def _map_to_enum(value, enum_map, default):
    """Map a free-text value to the closest enum using case-insensitive lookup."""
    if not value:
        return default
    val = str(value).strip().lower().replace('_', ' ')
    # Exact match first
    if val in enum_map:
        return enum_map[val]
    # Check if value is already a valid enum (snake_case)
    valid_enums = set(enum_map.values())
    if val.replace(' ', '_') in valid_enums:
        return val.replace(' ', '_')
    # Partial match — find the longest key that's contained in the value
    best = None
    best_len = 0
    for key, enum_val in enum_map.items():
        if key in val and len(key) > best_len:
            best = enum_val
            best_len = len(key)
    return best or default


def _normalize_scoring_fields(body):
    """Translate camelCase field names and map free-text to scoring enums."""
    scoring_body = dict(body)

    # Map camelCase → snake_case for scoring calculator
    if 'housingSituation' in body and 'housing_situation' not in body:
        raw = body['housingSituation']
        scoring_body['housing_situation'] = _map_to_enum(raw, HOUSING_MAP, 'renting_stable')
    elif 'housing_situation' in body:
        raw = body['housing_situation']
        scoring_body['housing_situation'] = _map_to_enum(raw, HOUSING_MAP, 'renting_stable')

    if 'employmentStatus' in body and 'employment_status' not in body:
        raw = body['employmentStatus']
        scoring_body['employment_status'] = _map_to_enum(raw, EMPLOYMENT_MAP, 'full_time')
    elif 'employment_status' in body:
        raw = body['employment_status']
        scoring_body['employment_status'] = _map_to_enum(raw, EMPLOYMENT_MAP, 'full_time')

    if 'monthlyIncome' in body and 'monthly_income' not in body:
        scoring_body['monthly_income'] = body['monthlyIncome']
    if 'monthlyHousingCost' in body and 'monthly_housing_cost' not in body:
        scoring_body['monthly_housing_cost'] = body['monthlyHousingCost']

    return scoring_body


def _derive_eligibility_flags(body):
    """Derive eligibility flags from demographics and save as contact attributes."""
    flags = {}

    # Age 65+ → BCDCOG
    age = body.get('age', '')
    try:
        if age and int(str(age).strip()) >= 65:
            flags['eligibleBCDCOG'] = 'true'
    except (ValueError, TypeError):
        pass

    # Children under 18 → Siemer
    children = str(body.get('hasChildrenUnder18', '')).strip().lower()
    if children in ('true', 'yes', 'y'):
        flags['eligibleSiemer'] = 'true'

    # Military → Mission United
    military = str(body.get('militaryAffiliation', '')).strip().lower()
    if military and military not in ('none', 'no', 'n', 'n/a', ''):
        flags['eligibleMissionUnited'] = 'true'

    # Job seeking / unemployed → Barriers to Employment
    employment = str(body.get('employmentStatus', '')).strip().lower()
    if any(kw in employment for kw in ('unemployed', 'seeking', 'looking', 'no job', 'not working')):
        flags['eligibleBarriersToEmployment'] = 'true'

    return flags


def _handle_resource_with_autoscore(body):
    """Run scoring automatically if scoring fields are present, then resource lookup.

    When the AI passes scoring fields (housingSituation, employmentStatus, etc.)
    alongside resource lookup data, this runs scoring first to save scoring
    contact attributes, then proceeds with resource lookup.  This eliminates
    the need for a separate scoringCalculate tool call.
    """
    has_scoring = any(body.get(f) is not None for f in SCORING_TRIGGER_FIELDS)

    # Derive and save eligibility flags from demographics
    eligibility_flags = _derive_eligibility_flags(body)
    if eligibility_flags:
        raw_instance = body.get('instance_id') or CONNECT_INSTANCE_ID
        raw_contact = body.get('contact_id') or ''
        instance_id = raw_instance.strip() if raw_instance else ''
        contact_id = raw_contact.strip() if raw_contact else ''
        if instance_id and UUID_RE.match(instance_id) and contact_id and UUID_RE.match(contact_id):
            try:
                connect_client = boto3.client('connect', region_name=CONNECT_REGION)
                connect_client.update_contact_attributes(
                    InstanceId=instance_id,
                    InitialContactId=contact_id,
                    Attributes=eligibility_flags,
                )
                logger.info('Saved %d eligibility flags: %s', len(eligibility_flags), list(eligibility_flags.keys()))
            except Exception:
                logger.warning('Failed to save eligibility flags', exc_info=True)

    if has_scoring:
        logger.info('Auto-scoring: scoring fields detected in resourceLookup call')
        scoring_body = _normalize_scoring_fields(body)
        try:
            scoring_result = handle_scoring(scoring_body)
            # Save scoring attributes immediately
            raw_instance = body.get('instance_id') or CONNECT_INSTANCE_ID
            raw_contact = body.get('contact_id') or ''
            instance_id = raw_instance.strip() if raw_instance else ''
            contact_id = raw_contact.strip() if raw_contact else ''
            if instance_id and UUID_RE.match(instance_id) and contact_id and UUID_RE.match(contact_id):
                score_attrs = {}
                score_fields = {
                    'housing_score': 'housingScore', 'housing_label': 'housingLabel',
                    'employment_score': 'employmentScore', 'employment_label': 'employmentLabel',
                    'financial_resilience_score': 'financialResilienceScore', 'financial_label': 'financialLabel',
                    'composite_score': 'compositeScore', 'composite_label': 'compositeLabel',
                    'priority_flag': 'priorityFlag', 'priority_meaning': 'priorityMeaning',
                    'recommended_path': 'recommendedPath', 'path_meaning': 'pathMeaning',
                }
                for k, v in score_fields.items():
                    val = scoring_result.get(k)
                    if val is not None:
                        score_attrs[v] = str(val).strip()
                # Build human-readable scoring summary
                summary_parts = []
                if scoring_result.get('housing_score'):
                    summary_parts.append(f"Housing: {scoring_result['housing_score']}/5 ({scoring_result.get('housing_label', '')})")
                if scoring_result.get('employment_score'):
                    summary_parts.append(f"Employment: {scoring_result['employment_score']}/5 ({scoring_result.get('employment_label', '')})")
                if scoring_result.get('financial_resilience_score'):
                    summary_parts.append(f"Financial: {scoring_result['financial_resilience_score']}/5 ({scoring_result.get('financial_label', '')})")
                if scoring_result.get('composite_score'):
                    summary_parts.append(f"Composite: {scoring_result['composite_score']}/5 ({scoring_result.get('composite_label', '')})")
                if scoring_result.get('priority_flag'):
                    summary_parts.append(f"Priority: {scoring_result['priority_meaning'] or scoring_result['priority_flag']}")
                if scoring_result.get('recommended_path'):
                    summary_parts.append(f"Path: {scoring_result['path_meaning'] or scoring_result['recommended_path']}")
                if summary_parts:
                    score_attrs['scoringSummary'] = ' | '.join(summary_parts)
                if score_attrs:
                    connect_client = boto3.client('connect', region_name=CONNECT_REGION)
                    connect_client.update_contact_attributes(
                        InstanceId=instance_id,
                        InitialContactId=contact_id,
                        Attributes=score_attrs,
                    )
                    logger.info('Auto-scoring: saved %d scoring attributes', len(score_attrs))
        except Exception:
            logger.warning('Auto-scoring failed, continuing with resource lookup', exc_info=True)

    # Auto-partner-check: if employer is present, check the partner list
    employer = body.get('employer', '').strip()
    if employer:
        employer_lower = employer.lower()
        partner_attrs = {}
        if employer_lower in EMPLOYER_CORRECTIONS:
            # Misspelling — correct it, mark as partner
            corrected = EMPLOYER_CORRECTIONS[employer_lower]
            partner_attrs = {'partnerEmployee': 'true', 'partnerEmployer': corrected, 'employer': corrected}
        elif employer_lower in PARTNER_EMPLOYERS:
            partner_attrs = {'partnerEmployee': 'true', 'partnerEmployer': PARTNER_EMPLOYERS[employer_lower]}
        else:
            # Partial match
            for key, name in PARTNER_EMPLOYERS.items():
                if key in employer_lower or employer_lower in key:
                    partner_attrs = {'partnerEmployee': 'true', 'partnerEmployer': name}
                    break
        if partner_attrs:
            raw_instance = body.get('instance_id') or CONNECT_INSTANCE_ID
            raw_contact = body.get('contact_id') or ''
            instance_id = raw_instance.strip() if raw_instance else ''
            contact_id = raw_contact.strip() if raw_contact else ''
            if instance_id and UUID_RE.match(instance_id) and contact_id and UUID_RE.match(contact_id):
                try:
                    connect_client = boto3.client('connect', region_name=CONNECT_REGION)
                    connect_client.update_contact_attributes(
                        InstanceId=instance_id,
                        InitialContactId=contact_id,
                        Attributes=partner_attrs,
                    )
                    logger.info('Auto-partner: saved %s', partner_attrs)
                except Exception:
                    logger.warning('Auto-partner: failed to save', exc_info=True)

    return handle_resource_lookup(body)


# ---------------------------------------------------------------------------
# Route tables
# ---------------------------------------------------------------------------

# API Gateway path -> handler
PATH_ROUTES = {
    '/scoring/calculate': handle_scoring,
    '/resources/search': _handle_resource_with_autoscore,
    '/intake/helper': handle_intake_helper,
}

# MCP operationId -> handler (tool name after stripping target prefix)
TOOL_ROUTES = {
    'scoringCalculate': handle_scoring,
    'resourceLookup': _handle_resource_with_autoscore,
    'intakeHelper': handle_intake_helper,
}

# Direct invocation action -> handler
ACTION_ROUTES = {
    'scoring': handle_scoring,
    'resource_lookup': _handle_resource_with_autoscore,
    'intake_helper': handle_intake_helper,
}

# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _extract_route_and_body(event):
    """Detect invocation format and extract (route_key, body_dict)."""

    # 1. API Gateway -- has httpMethod or resource
    if 'httpMethod' in event or 'resource' in event:
        path = event.get('resource') or event.get('path', '')
        method = event.get('httpMethod', 'POST')

        # Handle GET /r/{pageId} redirect (no body)
        if method == 'GET' and path.startswith('/r/'):
            return 'redirect', path, event

        body = {}
        if event.get('body'):
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        return 'path', path, body

    # 2. AgentCore MCP -- has toolName
    if 'toolName' in event:
        tool_name = event['toolName']
        if '___' in tool_name:
            tool_name = tool_name.split('___', 1)[1]
        args = event.get('arguments', {})
        if isinstance(args, str):
            args = json.loads(args)
        return 'tool', tool_name, args

    # 3. Direct invocation -- has action field
    if 'action' in event:
        return 'action', event['action'], event.get('payload', event)

    return 'unknown', None, event


def _resolve_handler(route_type, route_key):
    """Resolve the handler function from route tables."""
    if route_type == 'path':
        return PATH_ROUTES.get(route_key)
    if route_type == 'tool':
        return TOOL_ROUTES.get(route_key)
    if route_type == 'action':
        return ACTION_ROUTES.get(route_key)
    return None


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


def _response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Cache-Control': 'no-store',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'X-Content-Type-Options': 'nosniff',
        },
        'body': json.dumps(body, default=str),
    }


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------


RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET_NAME', '')


def _handle_results_redirect(event):
    """Handle GET /r/{pageId} — redirect to presigned S3 URL for results page."""
    path = event.get('path', '')
    page_id = path.split('/r/')[-1].strip('/') if '/r/' in path else ''

    if not page_id or not page_id.isalnum():
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'text/html'},
            'body': '<html><body><h1>Invalid Link</h1></body></html>',
        }

    s3_key = f'results/{page_id}.html'
    try:
        s3 = boto3.client('s3')
        s3.head_object(Bucket=RESULTS_BUCKET, Key=s3_key)
        presigned = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': RESULTS_BUCKET, 'Key': s3_key},
            ExpiresIn=86400,
        )
        return {
            'statusCode': 302,
            'headers': {'Location': presigned, 'Cache-Control': 'no-store'},
            'body': '',
        }
    except Exception:
        return {
            'statusCode': 404,
            'headers': {'Content-Type': 'text/html'},
            'body': (
                '<html><body style="font-family:sans-serif;text-align:center;padding:40px">'
                '<h1>Link Expired</h1>'
                '<p>This results page has expired. Please contact Stability360 for updated resources.</p>'
                '</body></html>'
            ),
        }


def handler(event, context):
    """Main entry point -- routes to the appropriate action module."""

    request_id = (
        event.get('requestContext', {}).get('requestId')
        or getattr(context, 'aws_request_id', 'unknown')
    )

    # Log full event keys and top-level structure for debugging
    logger.info(
        'Request received',
        extra={'extra': {
            'requestId': request_id,
            'eventKeys': list(event.keys()),
            'eventSnapshot': {k: (v if k not in ('body',) else '<body>')
                              for k, v in event.items()
                              if k not in ('body',)}
        }},
    )

    # Derive API_BASE_URL from event context on first API Gateway call
    if not os.environ.get('API_BASE_URL') and 'requestContext' in event:
        rc = event['requestContext']
        domain = rc.get('domainName', '')
        stage = rc.get('stage', '')
        if domain and stage:
            os.environ['API_BASE_URL'] = f'https://{domain}/{stage}'
            logger.info('Set API_BASE_URL=%s', os.environ['API_BASE_URL'])

    route_type, route_key, body = _extract_route_and_body(event)

    # Handle redirect requests directly (no JSON body parsing)
    if route_type == 'redirect':
        logger.info('Results redirect: %s', route_key)
        return _handle_results_redirect(event)

    logger.info(
        'Routing request',
        extra={'extra': {
            'requestId': request_id,
            'routeType': route_type,
            'routeKey': route_key,
            'bodyKeys': list(body.keys()) if isinstance(body, dict) else 'N/A',
        }},
    )

    handler_fn = _resolve_handler(route_type, route_key)

    if not handler_fn:
        logger.warning(
            'Unknown route',
            extra={'extra': {'requestId': request_id, 'routeKey': route_key}},
        )
        return _response(404, {'error': f'Unknown route: {route_key}'})

    try:
        result = handler_fn(body)

        # Auto-save contact attributes after every successful tool call
        _save_contact_attributes(body, result, request_id)

        # Post-disposition automation: task, customer profile, case
        # Skip if redirected (caller hasn't confirmed yet — automation runs
        # on the follow-up recordDisposition call after caller confirms)
        if not result.get('redirected'):
            automation_attrs = handle_disposition_automation(body, result)
            if automation_attrs:
                for k, v in automation_attrs.items():
                    result[k] = v

        # Propagate session attributes if present in the tool response
        session_attrs = result.pop('sessionAttributes', None)
        response = _response(200, result)
        if session_attrs:
            # Include session attributes at the top level for Connect/agent runtime
            response_body = json.loads(response['body'])
            response_body['sessionAttributes'] = session_attrs
            response['body'] = json.dumps(response_body, default=str)
            logger.info(
                'Session attributes included in response',
                extra={'extra': {'requestId': request_id, 'attrs': list(session_attrs.keys())}},
            )
        return response

    except ValueError as e:
        logger.warning(
            'Validation error',
            extra={'extra': {'requestId': request_id, 'error': str(e)}},
        )
        return _response(400, {'error': str(e)})

    except Exception:
        logger.error(
            'Unhandled exception',
            extra={'extra': {'requestId': request_id}},
            exc_info=True,
        )
        return _response(500, {'error': 'Internal server error'})
