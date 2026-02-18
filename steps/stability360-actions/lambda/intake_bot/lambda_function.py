"""
Stability360 Intake Bot Lambda — Routes customers to service-specific AI agents.

Handles Lex V2 code hook invocations for the Stability360IntakeBot.
Sends a ListPicker interactive message with available services.

Routing (both options close the session so the contact flow can branch):
  - Community Resources: closes session with intent RouteToCommunityResources
    → contact flow routes to Stability360 Actions AI agent (Aria)
  - Thrive@Work: closes session with intent RouteToThriveAtWork
    → contact flow routes to Thrive@Work AI agent
"""

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Interactive message templates
# ---------------------------------------------------------------------------

MAIN_MENU = {
    'templateType': 'ListPicker',
    'version': '1.0',
    'data': {
        'content': {
            'title': 'Welcome to Stability360!',
            'subtitle': 'How can we help you today? Please select a service:',
            'elements': [
                {
                    'title': 'Community Resources',
                    'subtitle': '211 resources, housing, utilities, food, and more',
                },
                {
                    'title': 'Thrive@Work',
                    'subtitle': 'Employee assistance and employer benefits',
                },
            ],
        },
    },
}

# Selections that route to Community Resources (Stability360 Actions agent)
COMMUNITY_KEYWORDS = {
    'community resources', 'community', 'resources', '211',
    'housing', 'utilities', 'food', 'assistance',
}
# Selections that route to Thrive@Work agent
THRIVE_KEYWORDS = {
    'thrive@work', 'thrive', 'thriveatwork', 'thrive at work',
    'employee', 'employer', 'benefits',
}


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def _elicit_slot_response(intent_name='IntakeIntent', messages=None,
                          session_attributes=None):
    """Return an ElicitSlot response to show the ListPicker menu."""
    if messages is None:
        messages = [
            {
                'contentType': 'CustomPayload',
                'content': json.dumps(MAIN_MENU),
            },
        ]

    resp = {
        'sessionState': {
            'dialogAction': {
                'type': 'ElicitSlot',
                'slotToElicit': 'IntakeResponse',
            },
            'intent': {
                'name': intent_name,
                'state': 'InProgress',
                'slots': {
                    'IntakeResponse': None,
                },
            },
        },
        'messages': messages,
    }
    if session_attributes:
        resp['sessionState']['sessionAttributes'] = session_attributes
    return resp


def _close_session(intent_name, message_text=None, session_attributes=None):
    """Close the IntakeBot session — exits to the contact flow.

    The intent_name determines which branch the contact flow takes:
      - RouteToCommunityResources → Stability360 Actions agent
      - RouteToThriveAtWork → Thrive@Work agent
    """
    resp = {
        'sessionState': {
            'dialogAction': {
                'type': 'Close',
            },
            'intent': {
                'name': intent_name,
                'state': 'Fulfilled',
            },
        },
    }
    if session_attributes:
        resp['sessionState']['sessionAttributes'] = session_attributes
    if message_text:
        resp['messages'] = [
            {
                'contentType': 'PlainText',
                'content': message_text,
            },
        ]
    return resp


# ---------------------------------------------------------------------------
# Selection handling
# ---------------------------------------------------------------------------


def _resolve_selection(text):
    """Classify user input. Returns 'community', 'thrive', or None."""
    if not text:
        return None
    normalized = text.lower().strip()
    # Exact match
    if normalized in COMMUNITY_KEYWORDS:
        return 'community'
    if normalized in THRIVE_KEYWORDS:
        return 'thrive'
    # Partial match
    for kw in COMMUNITY_KEYWORDS:
        if kw in normalized or normalized in kw:
            return 'community'
    for kw in THRIVE_KEYWORDS:
        if kw in normalized or normalized in kw:
            return 'thrive'
    return None


def _handle_selection(user_input, session_attributes):
    """Process the user's menu selection."""
    target = _resolve_selection(user_input)

    if target == 'community':
        return _close_session(
            'RouteToCommunityResources',
            'Connecting you to Community Resources...',
            session_attributes,
        )

    if target == 'thrive':
        return _close_session(
            'RouteToThriveAtWork',
            'Connecting you to Thrive@Work...',
            session_attributes,
        )

    # Unrecognized — re-show menu
    return _elicit_slot_response(session_attributes=session_attributes)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def handler(event, context):
    """Lex V2 code hook handler for the Stability360 Intake Bot."""
    logger.info('Event: %s', json.dumps(event, default=str))

    intent_name = event['sessionState']['intent']['name']
    invocation_source = event['invocationSource']
    input_transcript = event.get('inputTranscript', '').strip()
    slots = event['sessionState']['intent'].get('slots') or {}
    session_attributes = event['sessionState'].get('sessionAttributes') or {}

    # Get slot value if present
    slot_value = None
    intake_slot = slots.get('IntakeResponse')
    if intake_slot and intake_slot.get('value'):
        slot_value = intake_slot['value'].get('interpretedValue', '')

    logger.info(
        'Intent=%s, source=%s, transcript=%r, slotValue=%r',
        intent_name, invocation_source, input_transcript, slot_value,
    )

    # FallbackIntent — re-show the menu
    if intent_name == 'FallbackIntent':
        return _elicit_slot_response(session_attributes=session_attributes)

    # IntakeIntent handling
    if intent_name == 'IntakeIntent':
        user_input = slot_value or input_transcript
        if user_input:
            return _handle_selection(user_input, session_attributes)
        # No input yet — show the ListPicker menu
        return _elicit_slot_response(session_attributes=session_attributes)

    # Default — show menu
    return _elicit_slot_response(session_attributes=session_attributes)
