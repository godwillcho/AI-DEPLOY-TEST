"""
Stability360 Intake Bot Lambda — Routes customers to service-specific AI agents.

Handles Lex V2 code hook invocations for the Stability360IntakeBot.
Sends a ListPicker interactive message with available services.

Routing uses the ``selectedRoute`` session attribute (NOT intent switching,
because Lex V2 does not propagate intent-name changes in Close responses
back to Amazon Connect):
  - Community Resources → selectedRoute = "CommunityResources"
  - Thrive@Work        → selectedRoute = "ThriveAtWork"

The contact flow should use a *Check contact attributes* block after the
intake bot to branch on the ``selectedRoute`` Lex session attribute.
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


def _close_session(route_key, message_text=None, session_attributes=None):
    """Close the IntakeBot session — exits to the contact flow.

    Sets the ``selectedRoute`` session attribute so the contact flow can
    branch using a *Check contact attributes* block:
      - Attribute type : Lex session attribute
      - Attribute       : selectedRoute
      - Conditions       : ``CommunityResources`` or ``ThriveAtWork``

    The intent stays ``IntakeIntent`` (Fulfilled) because Lex V2 does NOT
    propagate intent-name changes made in a Close response back to
    Amazon Connect — Connect always sees the original matched intent.
    """
    attrs = dict(session_attributes or {})
    attrs['selectedRoute'] = route_key

    resp = {
        'sessionState': {
            'dialogAction': {
                'type': 'Close',
            },
            'intent': {
                'name': 'IntakeIntent',
                'state': 'Fulfilled',
            },
            'sessionAttributes': attrs,
        },
    }
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
            'CommunityResources',
            'Connecting you to Community Resources...',
            session_attributes,
        )

    if target == 'thrive':
        return _close_session(
            'ThriveAtWork',
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
        response = _elicit_slot_response(session_attributes=session_attributes)
        logger.info('Response: %s', json.dumps(response, default=str))
        return response

    # IntakeIntent handling
    if intent_name == 'IntakeIntent':
        user_input = slot_value or input_transcript
        if user_input:
            response = _handle_selection(user_input, session_attributes)
            logger.info('Response: %s', json.dumps(response, default=str))
            return response
        # No input yet — show the ListPicker menu
        response = _elicit_slot_response(session_attributes=session_attributes)
        logger.info('Response: %s', json.dumps(response, default=str))
        return response

    # Default — show menu
    response = _elicit_slot_response(session_attributes=session_attributes)
    logger.info('Response: %s', json.dumps(response, default=str))
    return response
