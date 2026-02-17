"""
Stability360 — Thrive@Work Employee ID Lookup (MCP Tool 1)

Receives an employee_id, queries DynamoDB, returns:
  - matched: True/False
  - employer_name, partnership_status, eligible_programs (if matched)
  - message: human-readable status for the AI agent

Invocation patterns handled:
  1. API Gateway            — event.body contains JSON string
  2. Bedrock Agent          — event.parameters is a list of {name, value}
  3. AgentCore Gateway MCP  — event.toolName + event.arguments dict
  4. AgentCore / Direct     — event.employee_id directly in event

Security:
  - Input sanitization on employee_id (alphanumeric + hyphens only, max 50 chars)
  - No internal error details leaked to caller
  - Structured JSON logging with correlation IDs
  - PII-safe logging (employee_id logged, no sensitive fields)
"""

import json
import boto3
import os
import re
import logging
from decimal import Decimal

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
TABLE_NAME = os.environ.get('EMPLOYEES_TABLE_NAME', '')

# Validation constants
MAX_EMPLOYEE_ID_LENGTH = 50
EMPLOYEE_ID_PATTERN = re.compile(r'^[A-Za-z0-9\-]+$')

# ---------------------------------------------------------------------------
# Logger setup — structured JSON output
# ---------------------------------------------------------------------------

logger = logging.getLogger('employee_lookup')
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))


class StructuredFormatter(logging.Formatter):
    """Emit log records as JSON lines for CloudWatch Logs Insights."""

    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'environment': ENVIRONMENT,
        }
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


# Replace default handlers
for h in logger.handlers[:]:
    logger.removeHandler(h)
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.addHandler(handler)

# ---------------------------------------------------------------------------
# DynamoDB client (initialized once per container)
# ---------------------------------------------------------------------------

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decimal_default(obj):
    """Convert DynamoDB Decimal types to Python int/float for JSON."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def _response(status_code, body):
    """Build API Gateway-compatible response with security headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'X-Content-Type-Options': 'nosniff',
            'Cache-Control': 'no-store',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        },
        'body': json.dumps(body, default=_decimal_default),
    }


def _extract_employee_id(event):
    """Extract employee_id from any supported invocation format."""

    # 1. API Gateway — body is a JSON string
    if 'body' in event and event['body']:
        body = json.loads(event['body'])
        return body.get('employee_id')

    # 2. Bedrock Agent action group — parameters is a list of dicts
    if 'parameters' in event and isinstance(event['parameters'], list):
        params = {p['name']: p['value'] for p in event['parameters']}
        return params.get('employee_id')

    # 3. AgentCore Gateway MCP — toolName + arguments dict
    if 'toolName' in event and 'arguments' in event:
        args = event['arguments']
        if isinstance(args, str):
            args = json.loads(args)
        return args.get('employee_id')

    # 4. AgentCore / Direct invocation — flat JSON
    return event.get('employee_id')


def _validate_employee_id(employee_id):
    """
    Validate employee_id input.
    Returns (sanitized_id, error_message).
    error_message is None if valid.
    """
    if not employee_id:
        return None, 'employee_id is required'

    employee_id = str(employee_id).strip()

    if len(employee_id) > MAX_EMPLOYEE_ID_LENGTH:
        return None, f'employee_id exceeds maximum length of {MAX_EMPLOYEE_ID_LENGTH}'

    if not EMPLOYEE_ID_PATTERN.match(employee_id):
        return None, 'employee_id contains invalid characters (alphanumeric and hyphens only)'

    return employee_id, None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(event, context):
    """Lambda entry point."""

    # Correlation ID for tracing
    request_id = (
        event.get('requestContext', {}).get('requestId')
        or getattr(context, 'aws_request_id', 'unknown')
    )

    logger.info(
        'Request received',
        extra={
            'extra': {
                'requestId': request_id,
                'invocationType': _detect_invocation_type(event),
            }
        },
    )

    try:
        # --- Extract input ---
        raw_employee_id = _extract_employee_id(event)

        # --- Validate input ---
        employee_id, validation_error = _validate_employee_id(raw_employee_id)
        if validation_error:
            logger.warning(
                f'Validation failed: {validation_error}',
                extra={'extra': {'requestId': request_id, 'raw_input': repr(raw_employee_id)[:100]}},
            )
            return _response(400, {
                'matched': False,
                'error': validation_error,
            })

        logger.info(
            'Looking up employee',
            extra={'extra': {'requestId': request_id, 'employee_id': employee_id}},
        )

        # --- DynamoDB lookup (GetItem by PK) ---
        result = table.get_item(
            Key={'employee_id': employee_id},
            ConsistentRead=True,
        )

        # --- No match ---
        if 'Item' not in result:
            logger.info(
                'Employee not found',
                extra={'extra': {'requestId': request_id, 'employee_id': employee_id}},
            )
            return _response(200, {
                'matched': False,
                'employee_id': employee_id,
                'message': 'Employee ID not recognized',
            })

        item = result['Item']
        partnership_status = item.get('partnership_status', 'UNKNOWN')

        # --- Match but INACTIVE partnership ---
        if partnership_status != 'ACTIVE':
            logger.info(
                'Employer partnership inactive',
                extra={
                    'extra': {
                        'requestId': request_id,
                        'employee_id': employee_id,
                        'partnership_status': partnership_status,
                    }
                },
            )
            return _response(200, {
                'matched': True,
                'employee_id': employee_id,
                'employer_name': item.get('employer_name', ''),
                'partnership_status': partnership_status,
                'eligible_programs': [],
                'message': 'Employer partnership is no longer active',
            })

        # --- Match and ACTIVE ---
        employer_name = item.get('employer_name', '')
        eligible_programs = item.get('eligible_programs', [])

        logger.info(
            'Employee validated successfully',
            extra={
                'extra': {
                    'requestId': request_id,
                    'employee_id': employee_id,
                    'employer_name': employer_name,
                    'program_count': len(eligible_programs),
                }
            },
        )

        return _response(200, {
            'matched': True,
            'employee_id': employee_id,
            'employer_name': employer_name,
            'partnership_status': 'ACTIVE',
            'eligible_programs': eligible_programs,
            'date_enrolled': item.get('date_enrolled', ''),
            'message': 'Employee verified — employer partnership active',
        })

    except json.JSONDecodeError as e:
        logger.warning(
            'Malformed JSON in request body',
            extra={'extra': {'requestId': request_id, 'error': str(e)}},
        )
        return _response(400, {
            'matched': False,
            'error': 'Invalid JSON in request body',
        })

    except Exception:
        # Log full stack trace internally but return generic message to caller
        logger.error(
            'Unhandled exception during employee lookup',
            extra={'extra': {'requestId': request_id}},
            exc_info=True,
        )
        return _response(500, {
            'matched': False,
            'error': 'Internal server error',
        })


def _detect_invocation_type(event):
    """Detect invocation source for logging."""
    if 'body' in event and event.get('httpMethod'):
        return 'api_gateway'
    if 'parameters' in event and isinstance(event.get('parameters'), list):
        return 'bedrock_agent'
    if 'toolName' in event and 'arguments' in event:
        return 'agentcore_mcp'
    if 'employee_id' in event:
        return 'direct_or_mcp'
    return 'unknown'
