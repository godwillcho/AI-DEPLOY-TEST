"""
Stability360 Actions — Lambda Router

Single Lambda function handling 5 MCP action tools:
  1. POST /scoring/calculate      → scoring_calculator.handle_scoring
  2. POST /charitytracker/submit  → charitytracker_payload.handle_charitytracker
  3. POST /followup/schedule      → followup_scheduler.handle_followup
  4. POST /customer/profile       → customer_profile.handle_customer_profile
  5. POST /case/status            → case_status.handle_case_status

Invocation patterns handled:
  1. API Gateway          — event.body (JSON string), event.resource / event.path
  2. AgentCore MCP        — event.toolName + event.arguments
  3. Direct / test        — event.action + event.payload
"""

import json
import logging
import os

from scoring_calculator import handle_scoring
from charitytracker_payload import handle_charitytracker
from followup_scheduler import handle_followup
from customer_profile import handle_customer_profile
from case_status import handle_case_status
from sophia_resource_lookup import handle_resource_lookup

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# ---------------------------------------------------------------------------
# Logger — structured JSON
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
# Route tables
# ---------------------------------------------------------------------------

# API Gateway path → handler
PATH_ROUTES = {
    '/scoring/calculate': handle_scoring,
    '/charitytracker/submit': handle_charitytracker,
    '/followup/schedule': handle_followup,
    '/customer/profile': handle_customer_profile,
    '/case/status': handle_case_status,
    '/resources/search': handle_resource_lookup,
}

# MCP operationId → handler (tool name after stripping target prefix)
TOOL_ROUTES = {
    'scoringCalculate': handle_scoring,
    'charityTrackerSubmit': handle_charitytracker,
    'followupSchedule': handle_followup,
    'customerProfileLookup': handle_customer_profile,
    'caseStatusLookup': handle_case_status,
    'resourceLookup': handle_resource_lookup,
}

# Direct invocation action → handler
ACTION_ROUTES = {
    'scoring': handle_scoring,
    'charitytracker': handle_charitytracker,
    'followup': handle_followup,
    'customer_profile': handle_customer_profile,
    'case_status': handle_case_status,
    'resource_lookup': handle_resource_lookup,
}

# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _extract_route_and_body(event):
    """Detect invocation format and extract (route_key, body_dict)."""

    # 1. API Gateway — has httpMethod or resource
    if 'httpMethod' in event or 'resource' in event:
        path = event.get('resource') or event.get('path', '')
        body = {}
        if event.get('body'):
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        return 'path', path, body

    # 2. AgentCore MCP — has toolName
    if 'toolName' in event:
        tool_name = event['toolName']
        if '___' in tool_name:
            tool_name = tool_name.split('___', 1)[1]
        args = event.get('arguments', {})
        if isinstance(args, str):
            args = json.loads(args)
        return 'tool', tool_name, args

    # 3. Direct invocation — has action field
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
    """Main entry point — routes to the appropriate action module."""

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
