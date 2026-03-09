"""
Stability360 Actions -- Lambda Router

Routes incoming requests to the appropriate action module.
Handles 3 invocation patterns: API Gateway, AgentCore MCP, and direct.
After each successful call, auto-saves contact attributes and runs
post-disposition automation (task, profile, case).

Modules:
  config.py               - Shared constants, env vars, logger
  partner_employers.py    - Thrive@Work partner employer list
  contact_attributes.py   - Contact attribute persistence + eligibility
  auto_scoring.py         - Auto-score wrapper for resource lookup
  intake_helper.py        - 6 intake actions (classify, validate, fields, partner, next steps, disposition)
  queue_checker.py        - Agent availability check
  scoring_calculator.py   - Scoring math
  sophia_resource_lookup.py - Sophia API search + S3 results
  task_manager.py         - Customer profile + task + case creation
"""

import json
import os

import boto3

from config import RESULTS_BUCKET, get_logger
from contact_attributes import save_contact_attributes
from auto_scoring import handle_resource_with_autoscore
from intake_helper import handle_intake_helper
from scoring_calculator import handle_scoring
from task_manager import handle_disposition_automation

logger = get_logger('actions_router')

# ---------------------------------------------------------------------------
# Route tables
# ---------------------------------------------------------------------------

PATH_ROUTES = {
    '/scoring/calculate': handle_scoring,
    '/resources/search': handle_resource_with_autoscore,
    '/intake/helper': handle_intake_helper,
}

TOOL_ROUTES = {
    'scoringCalculate': handle_scoring,
    'resourceLookup': handle_resource_with_autoscore,
    'intakeHelper': handle_intake_helper,
}

ACTION_ROUTES = {
    'scoring': handle_scoring,
    'resource_lookup': handle_resource_with_autoscore,
    'intake_helper': handle_intake_helper,
}

# ---------------------------------------------------------------------------
# Request parsing
# ---------------------------------------------------------------------------


def _extract_route_and_body(event):
    """Detect invocation format and extract (route_type, route_key, body_dict)."""

    # 1. API Gateway
    if 'httpMethod' in event or 'resource' in event:
        path = event.get('resource') or event.get('path', '')
        method = event.get('httpMethod', 'POST')

        if method == 'GET' and path.startswith('/r/'):
            return 'redirect', path, event

        body = {}
        if event.get('body'):
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        return 'path', path, body

    # 2. AgentCore MCP
    if 'toolName' in event:
        tool_name = event['toolName']
        if '___' in tool_name:
            tool_name = tool_name.split('___', 1)[1]
        args = event.get('arguments', {})
        if isinstance(args, str):
            args = json.loads(args)
        return 'tool', tool_name, args

    # 3. Direct invocation
    if 'action' in event:
        return 'action', event['action'], event.get('payload', event)

    return 'unknown', None, event


def _resolve_handler(route_type, route_key):
    """Resolve the handler function from route tables."""
    tables = {'path': PATH_ROUTES, 'tool': TOOL_ROUTES, 'action': ACTION_ROUTES}
    return tables.get(route_type, {}).get(route_key)


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
# Results redirect (GET /r/{pageId})
# ---------------------------------------------------------------------------


def _handle_results_redirect(event):
    """Handle GET /r/{pageId} -- redirect to presigned S3 URL for results page."""
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
        extra={'extra': {
            'requestId': request_id,
            'eventKeys': list(event.keys()),
            'eventSnapshot': {k: (v if k != 'body' else '<body>')
                              for k, v in event.items() if k != 'body'},
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

    # Redirect requests
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
        logger.warning('Unknown route: %s', route_key)
        return _response(404, {'error': f'Unknown route: {route_key}'})

    try:
        result = handler_fn(body)

        # Auto-save contact attributes
        save_contact_attributes(body, result, request_id)

        # Post-disposition automation (task, profile, case)
        if not result.get('redirected'):
            automation_attrs = handle_disposition_automation(body, result)
            if automation_attrs:
                result.update(automation_attrs)

        # Propagate session attributes
        session_attrs = result.pop('sessionAttributes', None)
        response = _response(200, result)
        if session_attrs:
            response_body = json.loads(response['body'])
            response_body['sessionAttributes'] = session_attrs
            response['body'] = json.dumps(response_body, default=str)
            logger.info(
                'Session attributes included in response',
                extra={'extra': {'requestId': request_id, 'attrs': list(session_attrs.keys())}},
            )
        return response

    except ValueError as e:
        logger.warning('Validation error: %s', e)
        return _response(400, {'error': str(e)})

    except Exception:
        logger.error('Unhandled exception', exc_info=True)
        return _response(500, {'error': 'Internal server error'})
