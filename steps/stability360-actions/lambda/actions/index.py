"""
Stability360 Actions -- Lambda Router

Single Lambda function handling 2 MCP action tools:
  1. POST /scoring/calculate   -> scoring_calculator.handle_scoring
  2. POST /resources/search    -> sophia_resource_lookup.handle_resource_lookup

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

from scoring_calculator import handle_scoring
from sophia_resource_lookup import handle_resource_lookup

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
    'county': 'county', 'contactMethod': 'contactMethod',
    'phoneNumber': 'phoneNumber', 'emailAddress': 'emailAddress',
    'preferredDays': 'preferredDays', 'preferredTimes': 'preferredTimes',
    # Need
    'needCategory': 'needCategory', 'keyword': 'needCategory',
    'needSubcategory': 'needSubcategory', 'path': 'path',
    # Demographics
    'age': 'age', 'hasChildrenUnder18': 'hasChildrenUnder18',
    'employmentStatus': 'employmentStatus', 'employment_status': 'employmentStatus',
    'employer': 'employer',
    'militaryAffiliation': 'militaryAffiliation',
    'publicAssistance': 'publicAssistance',
    # Scoring inputs
    'housing_situation': 'housingSituation', 'housingSituation': 'housingSituation',
    'monthly_income': 'monthlyIncome', 'monthlyIncome': 'monthlyIncome',
    'monthly_housing_cost': 'monthlyHousingCost', 'monthlyHousingCost': 'monthlyHousingCost',
    'monthly_expenses': 'monthlyExpenses', 'monthlyExpenses': 'monthlyExpenses',
    'savings_rate': 'savingsRate', 'savingsRate': 'savingsRate',
    'fico_range': 'ficoRange', 'ficoRange': 'ficoRange',
    'has_benefits': 'hasBenefits', 'hasBenefits': 'hasBenefits',
    # Partner
    'partnerEmployee': 'partnerEmployee', 'partnerEmployer': 'partnerEmployer',
    # Routing
    'escalationRoute': 'escalationRoute',
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

    # Collect scoring results from handler output
    score_fields = {
        'housing_score': 'housingScore',
        'employment_score': 'employmentScore',
        'financial_resilience_score': 'financialResilienceScore',
        'composite_score': 'compositeScore',
        'priority_flag': 'priorityFlag',
        'recommended_path': 'recommendedPath',
    }
    for result_key, attr_name in score_fields.items():
        value = result.get(result_key)
        if value is not None:
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
# Route tables
# ---------------------------------------------------------------------------

# API Gateway path -> handler
PATH_ROUTES = {
    '/scoring/calculate': handle_scoring,
    '/resources/search': handle_resource_lookup,
}

# MCP operationId -> handler (tool name after stripping target prefix)
TOOL_ROUTES = {
    'scoringCalculate': handle_scoring,
    'resourceLookup': handle_resource_lookup,
}

# Direct invocation action -> handler
ACTION_ROUTES = {
    'scoring': handle_scoring,
    'resource_lookup': handle_resource_lookup,
}

# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _extract_route_and_body(event):
    """Detect invocation format and extract (route_key, body_dict)."""

    # 1. API Gateway -- has httpMethod or resource
    if 'httpMethod' in event or 'resource' in event:
        path = event.get('resource') or event.get('path', '')
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


def handler(event, context):
    """Main entry point -- routes to the appropriate action module."""

    request_id = (
        event.get('requestContext', {}).get('requestId')
        or getattr(context, 'aws_request_id', 'unknown')
    )

    logger.info(
        'Request received',
        extra={'extra': {'requestId': request_id}},
    )

    route_type, route_key, body = _extract_route_and_body(event)

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
