"""
Stability360 Intake Bot Lambda — Routes customers to service-specific AI agents.

Handles Lex V2 code hook invocations for the Stability360IntakeBot.
Sends a ListPicker interactive message with available services.

Routing:
  - Thrive@Work: closes the IntakeBot session so the contact flow continues
    to the CreateWisdomSession -> Stability360Bot path.
  - General Assistance: handled entirely inside this Lambda (shows "coming
    soon" message and re-shows the menu).  The bot session stays open.

The contact flow after the IntakeBot is a simple linear path — no branching.
The IntakeBot only exits (Close) when the user picks Thrive@Work.
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
            'subtitle': 'Please select a service to get started:',
            'elements': [
                {
                    'title': 'Thrive@Work',
                    'subtitle': 'AI-powered employee assistance and resources',
                },
                {
                    'title': 'General Assistance',
                    'subtitle': 'Other services and support',
                },
            ],
        },
    },
}

# Selections that route to Thrive@Work (close the session)
THRIVE_KEYWORDS = {'thrive@work', 'thrive', 'thriveatwork', 'thrive at work'}
# Selections that show "coming soon" and re-show menu
GENERAL_KEYWORDS = {'general assistance', 'general'}


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


def _close_session(message_text=None, session_attributes=None):
    """Close the IntakeBot session (user selected Thrive@Work)."""
    resp = {
        'sessionState': {
            'dialogAction': {
                'type': 'Close',
            },
            'intent': {
                'name': 'IntakeIntent',
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
    """Classify user input. Returns 'thrive', 'general', or None."""
    if not text:
        return None
    normalized = text.lower().strip()
    # Exact match
    if normalized in THRIVE_KEYWORDS:
        return 'thrive'
    if normalized in GENERAL_KEYWORDS:
        return 'general'
    # Partial match
    for kw in THRIVE_KEYWORDS:
        if kw in normalized or normalized in kw:
            return 'thrive'
    for kw in GENERAL_KEYWORDS:
        if kw in normalized or normalized in kw:
            return 'general'
    return None


def _handle_selection(user_input, session_attributes):
    """Process the user's menu selection."""
    target = _resolve_selection(user_input)

    if target == 'thrive':
        # Close the session — contact flow continues to Q Connect path
        return _close_session(
            'Connecting you to Thrive@Work...',
            session_attributes,
        )

    if target == 'general':
        # Show "coming soon" message then re-show the menu (stay in IntakeBot)
        return _elicit_slot_response(
            messages=[
                {
                    'contentType': 'PlainText',
                    'content': (
                        'Thank you for your interest! General Assistance '
                        'is coming soon. Please check back later.'
                    ),
                },
                {
                    'contentType': 'CustomPayload',
                    'content': json.dumps(MAIN_MENU),
                },
            ],
            session_attributes=session_attributes,
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
