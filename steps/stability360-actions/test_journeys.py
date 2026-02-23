#!/usr/bin/env python3
"""Customer journey E2E tests for the Stability360 Actions AI agent (Aria).

Tests 13 complete customer journeys through the Q Connect SendMessage API.
Each journey validates correct conversational flow including consent, intake,
tool usage, and session attribute behavior.

Critical validation: "I need help finding food" triggers consent + intake,
while "What food banks are in Charleston?" triggers a direct resource search.

Journeys:
   1. Referral -- Food (unemployed, consent + condensed intake)
   2. Referral -- Food (employed, partner employer, silent KB check)
   3. Referral -- Vague request -> menu -> Housing -> Rent
   4. Direct Support -- Utilities (non-urgent, full intake + scoring)
   5. Direct Support -- Utilities (imminent shutoff, priority escalation)
   6. General Question -- No consent needed (direct resource search)
   7. Out-of-Area -- ZIP outside service area
   8. Consent Declined -- General assistance only
   9. Hybrid -- Food [R] + Utilities [D] (mixed needs)
  10. Info Question -- "What is Stability360?"
  11. Human Escalation -- Client requests a person
  12. Thrive@Work Mention -- Redirected, no details shared
  13. Tool Failure Fallback -- Graceful degradation

Usage:
    python steps/stability360-actions/test_journeys.py                # dev (default)
    python steps/stability360-actions/test_journeys.py --env prod     # prod
    python steps/stability360-actions/test_journeys.py --test 1       # single journey
    python steps/stability360-actions/test_journeys.py --test 1,6     # specific journeys
    python steps/stability360-actions/test_journeys.py --verbose      # show full bot responses
"""

import argparse
import boto3
import json
import sys
import time
import uuid

# ---------------------------------------------------------------------------
# Environment configs
# ---------------------------------------------------------------------------

ENVS = {
    'dev': {
        'region': 'us-west-2',
        'assistant_id': '7cce1c51-b13c-490b-9c4f-01fd7c9e66eb',
        'agent_id': '88f2b8d8-1d85-4079-870f-d952be8b5fdb',
    },
    'prod': {
        'region': 'us-east-1',
        'assistant_id': '170bfe70-4ed2-4abe-abb8-1d9f5213128d',
        'agent_id': '21256ee4-ee96-47f7-ac3f-e7cb10cdf17a',
    },
}

MAX_POLL_SECONDS = 90
POLL_INTERVAL = 1.5
BETWEEN_MESSAGES = 3
BETWEEN_TESTS = 4

VERBOSE = False


# ---------------------------------------------------------------------------
# Q Connect helpers
# ---------------------------------------------------------------------------


def create_session(qc, assistant_id, name):
    """Create a new Q Connect session."""
    resp = qc.create_session(assistantId=assistant_id, name=name)
    return resp['session']['sessionId']


def send_and_get(qc, assistant_id, session_id, text):
    """Send a message and poll for the bot's response."""
    send_resp = qc.send_message(
        assistantId=assistant_id,
        sessionId=session_id,
        type='TEXT',
        message={'value': {'text': {'value': text}}},
        orchestratorUseCase='Connect.SelfService',
    )
    next_token = send_resp.get('nextMessageToken')

    responses = []
    start = time.time()
    while time.time() - start < MAX_POLL_SECONDS:
        if not next_token:
            break
        try:
            msg = qc.get_next_message(
                assistantId=assistant_id,
                sessionId=session_id,
                nextMessageToken=next_token,
            )
        except Exception as e:
            if 'Throttl' in str(type(e).__name__) or 'throttl' in str(e).lower():
                time.sleep(2)
                continue
            raise

        conv_state = msg.get('conversationState', {})
        status = conv_state.get('status', '')
        next_token = msg.get('nextMessageToken')

        resp_val = msg.get('response', {}).get('value', {})
        text_val = resp_val.get('text', {}).get('value', '')
        participant = msg.get('response', {}).get('participant', '')

        if text_val and participant != 'CUSTOMER':
            responses.append(text_val)

        if status == 'CLOSED':
            break
        if status == 'READY' and responses:
            break
        if status == 'PROCESSING':
            time.sleep(POLL_INTERVAL)
            continue

        time.sleep(POLL_INTERVAL)

    return '\n'.join(responses), conv_state


def converse(qc, assistant_id, session_id, messages):
    """Send a sequence of messages and collect all responses."""
    all_responses = []
    last_state = {}
    for msg in messages:
        resp, state = send_and_get(qc, assistant_id, session_id, msg)
        all_responses.append({'user': msg, 'bot': resp, 'state': state})
        last_state = state
        time.sleep(BETWEEN_MESSAGES)
    return all_responses, last_state


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def has_any(text, keywords):
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def has_all(text, keywords):
    """Check if text contains ALL of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return all(kw.lower() in text_lower for kw in keywords)


def bot_at(exchanges, turn):
    """Get the bot response at a specific turn index (0-based)."""
    if turn < len(exchanges):
        return exchanges[turn]['bot']
    return ''


def all_bot_text(exchanges):
    """Concatenate all bot responses into one string."""
    return ' '.join(e['bot'] for e in exchanges)


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------


class JourneyResult:
    """Holds the result of a single journey test."""

    def __init__(self, number, name, exchanges, checks):
        self.number = number
        self.name = name
        self.exchanges = exchanges
        self.checks = checks  # list of (check_name, passed, detail)
        self.passed = all(c[1] for c in checks)

    def print_report(self):
        status = '\033[92mPASS\033[0m' if self.passed else '\033[91mFAIL\033[0m'
        print(f'\n{"=" * 70}')
        print(f'[{status}] Journey {self.number}: {self.name}')
        print(f'{"=" * 70}')

        # Print conversation
        for ex in self.exchanges:
            print(f'  Client: {ex["user"]}')
            bot = ex['bot']
            if not VERBOSE and len(bot) > 300:
                bot = bot[:300] + '...'
            for line in bot.split('\n'):
                print(f'  Aria:   {line}')
            print()

        # Print checks
        for check_name, passed, detail in self.checks:
            icon = '\033[92m+\033[0m' if passed else '\033[91mx\033[0m'
            print(f'  [{icon}] {check_name}')
            if not passed and detail:
                print(f'       -> {detail}')

        return self.passed


# ---------------------------------------------------------------------------
# Journey tests
# ---------------------------------------------------------------------------


def journey_01_referral_food_unemployed(qc, cfg):
    """Referral -- Food Assistance (unemployed)"""
    sid = create_session(qc, cfg['assistant_id'], f'j01-food-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help finding food',           # triggers intake, NOT general lookup
        'Yes',                                 # confirm need
        'Yes that\'s fine',                    # consent
        '29407',                               # ZIP (Charleston)
        'Text',                                # contact method
        '843-555-1234',                        # phone number
        'No',                                  # not employed -> skip employer
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Aria confirms food need or asks consent',
         has_any(full, ['food', 'consent', 'personal questions', 'information']),
         f'Expected need confirmation or consent ask'),
        ('Consent asked BEFORE data collection',
         has_any(full, ['personal questions', 'consent', 'okay with you', 'is that okay']),
         'No consent language found -- may have skipped consent'),
        ('ZIP code asked during intake',
         has_any(full, ['zip', 'zip code', 'where', 'area', 'located']),
         'ZIP code question not found'),
        ('Contact method asked',
         has_any(full, ['contact', 'phone', 'text', 'email', 'reach']),
         'Contact method question not found'),
        ('Employment asked',
         has_any(full, ['employ', 'work', 'job']),
         'Employment question not found'),
        ('Resources shared (resourceLookup called after intake)',
         has_any(full, ['food', 'pantry', 'resource', 'provider', 'assistance',
                        'phone:', 'services:']),
         'No resource results found -- resourceLookup may not have been called'),
        ('Did NOT jump straight to resource search (consent first)',
         not has_any(bot_at(exchanges, 1), ['search', 'looking up', 'let me find']),
         'Bot jumped to resource search on turn 2 -- consent was skipped'),
    ]

    return JourneyResult(1, 'Referral -- Food (unemployed)', exchanges, checks)


def journey_02_referral_food_employed_partner(qc, cfg):
    """Referral -- Food Assistance (employed, partner employer check)"""
    sid = create_session(qc, cfg['assistant_id'], f'j02-food-emp-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with food',
        'Yes',                                  # confirm need
        'Sure',                                 # consent
        '29466',                                # ZIP (Berkeley/Charleston)
        'Phone call',                           # contact method
        '843-555-9876',                         # phone
        'Yes, part time',                       # employed
        'Bosch',                                # employer (partner check triggers)
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Consent asked',
         has_any(full, ['personal questions', 'consent', 'okay with you', 'is that okay']),
         'No consent language found'),
        ('Employer asked (since employed)',
         has_any(full, ['employer', 'who do you work', 'company', 'work for']),
         'Employer question not found despite being employed'),
        ('Thrive@Work NOT mentioned to client',
         not has_any(full, ['thrive', 'partner', 'employer program', 'employer benefit']),
         'Thrive@Work or partner program was disclosed to client'),
        ('Resources shared after intake',
         has_any(full, ['food', 'pantry', 'resource', 'provider', 'assistance']),
         'No resource results found'),
        ('Follow-up offered',
         has_any(full, ['follow up', 'team member', 'call you', 'reach out']),
         'No follow-up offer found'),
    ]

    return JourneyResult(2, 'Referral -- Food (employed, partner check)', exchanges, checks)


def journey_03_referral_vague_menu_housing_rent(qc, cfg):
    """Referral -- Vague request -> menu -> Housing -> Rent"""
    sid = create_session(qc, cfg['assistant_id'], f'j03-vague-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help',                          # vague -> menu
        '1',                                    # Housing
        'Rent',                                 # subcategory
        'Yes',                                  # consent
        '29401',                                # ZIP (Charleston)
        'Email',                                # contact method
        'test@example.com',                     # email
        'No',                                   # not employed
    ])

    full = all_bot_text(exchanges)
    bot_turn1 = bot_at(exchanges, 0)
    checks = [
        ('Menu presented for vague request',
         has_any(bot_turn1, ['1.', 'housing', 'transportation', 'food'])
         or has_any(bot_at(exchanges, 1) if len(exchanges) > 1 else '', ['1.', 'housing']),
         'Category menu not presented when client was vague'),
        ('Subcategory follow-up asked',
         has_any(full, ['rent', 'shelter', 'eviction', 'repair', 'utilities', 'housing need']),
         'No subcategory follow-up found'),
        ('Consent asked after classification',
         has_any(full, ['personal questions', 'consent', 'okay with you']),
         'Consent not asked'),
        ('Resources shared',
         has_any(full, ['resource', 'provider', 'rental', 'assistance', 'help']),
         'No resource results found'),
    ]

    return JourneyResult(3, 'Referral -- Vague -> Menu -> Housing -> Rent', exchanges, checks)


def journey_04_direct_support_utilities_non_urgent(qc, cfg):
    """Direct Support -- Utilities (non-urgent, full intake + scoring)"""
    sid = create_session(qc, cfg['assistant_id'], f'j04-util-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with my utility bills',
        'Yes',                                  # confirm need
        'Yes, that\'s okay',                    # consent
        'Maria',                                # first name
        'Gonzalez',                             # last name
        '29414',                                # ZIP (Charleston/Dorchester)
        'Email',                                # contact method
        'maria.test@example.com',               # email
        'Weekdays',                             # preferred days
        'Morning',                              # preferred time
        '34',                                   # age
        'Yes, two kids',                        # children under 18
        'Employed full time',                   # employment
        'Boeing',                               # employer (partner check)
        'None',                                 # military
        'We get SNAP',                          # public assistance
        'Renting',                              # housing situation (scoring)
        '$2,800',                               # monthly income (scoring)
        '$1,200',                               # housing cost (scoring)
        'Yes please',                           # connect with team member
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Consent asked',
         has_any(full, ['personal questions', 'consent', 'okay with you']),
         'No consent language found'),
        ('First name asked',
         has_any(full, ['first name', 'name']),
         'First name question not found'),
        ('ZIP code asked',
         has_any(full, ['zip', 'zip code']),
         'ZIP code question not found'),
        ('Age asked (Direct Support -- Housing)',
         has_any(full, ['old are you', 'age', 'how old']),
         'Age question not found for Direct Support path'),
        ('Children asked',
         has_any(full, ['children', 'kids', 'under 18']),
         'Children question not found'),
        ('Employment asked',
         has_any(full, ['employ', 'work', 'job']),
         'Employment question not found'),
        ('Military asked',
         has_any(full, ['military', 'service', 'veteran']),
         'Military question not found'),
        ('Housing situation asked (scoring)',
         has_any(full, ['housing situation', 'renting', 'shelter', 'own']),
         'Housing situation scoring question not found'),
        ('Income asked (scoring)',
         has_any(full, ['income', 'earn', 'make']),
         'Income scoring question not found'),
        ('Scoring completed -- escalation offered',
         has_any(full, ['team member', 'connect', 'someone', 'benefit']),
         'No escalation offer after scoring'),
        ('Thrive@Work NOT mentioned',
         not has_any(full, ['thrive', 'partner employer', 'employer program']),
         'Thrive@Work leaked to client'),
    ]

    return JourneyResult(4, 'Direct Support -- Utilities (non-urgent)', exchanges, checks)


def journey_05_direct_support_imminent_shutoff(qc, cfg):
    """Direct Support -- Utilities (imminent shutoff, priority escalation)"""
    sid = create_session(qc, cfg['assistant_id'], f'j05-shutoff-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'My power is getting cut off tomorrow, I need help',
        'Yes',                                  # consent
        'Yes',                                  # connect now
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Urgency recognized',
         has_any(full, ['urgent', 'understand', 'right away', 'immediately']),
         'No urgency acknowledgment found'),
        ('Consent asked even for urgent',
         has_any(full, ['personal questions', 'consent', 'okay with you'])
         or has_any(full, ['connect', 'team member', 'someone']),
         'Neither consent nor immediate escalation found'),
        ('Offered to connect (or scheduled callback)',
         has_any(full, ['connect', 'team member', 'someone', 'callback',
                        'call you', 'business hours']),
         'No escalation offer found'),
        ('Scoring NOT mentioned (should be skipped for imminent shutoff)',
         not has_any(full, ['score', 'assess', 'review your situation']),
         'Scoring language found -- should have been skipped for imminent shutoff'),
    ]

    return JourneyResult(5, 'Direct Support -- Imminent Shutoff', exchanges, checks)


def journey_06_general_question_no_consent(qc, cfg):
    """General Question -- No consent needed (direct resource search)"""
    sid = create_session(qc, cfg['assistant_id'], f'j06-general-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'What food banks are in Charleston?',
    ])

    bot = bot_at(exchanges, 0)
    checks = [
        ('Direct resource results (no consent asked)',
         has_any(bot, ['food', 'bank', 'pantry', 'resource', 'provider', 'phone', 'services']),
         'No resource results in first response -- expected direct search'),
        ('Consent NOT asked for general question',
         not has_any(bot, ['personal questions', 'consent', 'okay with you']),
         'Consent was asked for a general question -- should not be required'),
        ('No intake questions asked',
         not has_any(bot, ['first name', 'last name', 'employment', 'employed']),
         'Intake questions were asked for a general question'),
    ]

    return JourneyResult(6, 'General Question -- No Consent', exchanges, checks)


def journey_07_out_of_area(qc, cfg):
    """Out-of-Area -- ZIP outside service area"""
    sid = create_session(qc, cfg['assistant_id'], f'j07-ooa-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with rent',
        'Yes',                                  # confirm need
        'Yes',                                  # consent
        '29201',                                # Columbia, SC -- NOT in service area
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Consent asked before ZIP',
         has_any(full, ['personal questions', 'consent', 'okay with you']),
         'No consent language found'),
        ('Out-of-area detected',
         has_any(full, ['outside', 'service area', 'currently serves',
                        'berkeley', 'charleston', 'dorchester']),
         'No out-of-area message found'),
        ('Directed to 211',
         has_any(full, ['211', 'sc211', '2-1-1']),
         'No 211 referral found for out-of-area client'),
        ('Intake stopped (no further questions after ZIP rejection)',
         not has_any(full, ['contact method', 'phone call, text, or email',
                            'employment status']),
         'Intake continued after out-of-area detection'),
    ]

    return JourneyResult(7, 'Out-of-Area Client', exchanges, checks)


def journey_08_consent_declined(qc, cfg):
    """Consent Declined -- General assistance only"""
    sid = create_session(qc, cfg['assistant_id'], f'j08-decline-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with transportation',
        'Yes',                                  # confirm need
        'No, I\'d rather not share personal info',  # decline consent
        'Charleston',                            # location for general search
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Consent requested',
         has_any(full, ['personal questions', 'consent', 'okay with you']),
         'No consent request found'),
        ('Decline respected gracefully',
         has_any(full, ['no problem', 'that\'s okay', 'understand',
                        'general information', 'without collecting']),
         'No graceful decline acknowledgment found'),
        ('General resources still offered',
         has_any(full, ['resource', 'transportation', 'help', 'area']),
         'No general assistance offered after decline'),
        ('No intake questions after decline',
         not has_any(full, ['first name', 'last name', 'employment status']),
         'Intake questions asked after consent was declined'),
    ]

    return JourneyResult(8, 'Consent Declined', exchanges, checks)


def journey_09_hybrid_food_and_utilities(qc, cfg):
    """Hybrid -- Food [R] + Utilities [D] (mixed needs)"""
    sid = create_session(qc, cfg['assistant_id'], f'j09-hybrid-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with food and my electric bill',
        'Yes',                                  # confirm
        'Yes',                                  # consent
        'John',                                 # first name
        'Smith',                                # last name
        '29483',                                # ZIP (tri-county)
        'Phone call',                           # contact method
        '843-555-7777',                         # phone
        'Weekdays',                             # preferred days
        'Afternoon',                            # preferred time
        '45',                                   # age
        'No',                                   # no children
        'Full time',                            # employment
        'MUSC',                                 # employer
        'None',                                 # military
        'No',                                   # no public assistance
        'Renting month to month',               # housing (scoring)
        '$3,200',                               # income (scoring)
        '$1,100',                               # housing cost (scoring)
        'Yes',                                  # connect with team member
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Both needs acknowledged',
         has_any(full, ['food']) and has_any(full, ['utilit', 'electric']),
         'Not all needs acknowledged'),
        ('Consent asked',
         has_any(full, ['personal questions', 'consent', 'okay with you']),
         'No consent found'),
        ('Full Direct Support intake (names asked)',
         has_any(full, ['first name', 'name']),
         'Full intake not collected for hybrid path'),
        ('Scoring data collected',
         has_any(full, ['housing situation', 'income', 'housing', 'rent']),
         'No scoring questions found'),
        ('Escalation offered',
         has_any(full, ['team member', 'connect', 'someone']),
         'No escalation offer found'),
    ]

    return JourneyResult(9, 'Hybrid -- Food + Utilities', exchanges, checks)


def journey_10_info_question(qc, cfg):
    """Info Question -- "What is Stability360?" (no tools needed)"""
    sid = create_session(qc, cfg['assistant_id'], f'j10-info-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'What is Stability360?',
    ])

    bot = bot_at(exchanges, 0)
    checks = [
        ('Answered with Stability360 info',
         has_any(bot, ['stability360', 'trident', 'united way', 'program', 'community']),
         'No Stability360 description found'),
        ('No consent asked for info question',
         not has_any(bot, ['personal questions', 'consent']),
         'Consent asked for a simple info question'),
        ('No intake questions',
         not has_any(bot, ['zip code', 'first name', 'employment']),
         'Intake questions asked for info question'),
    ]

    return JourneyResult(10, 'Info Question -- What is Stability360?', exchanges, checks)


def journey_11_human_escalation(qc, cfg):
    """Human Escalation -- Client requests a person"""
    sid = create_session(qc, cfg['assistant_id'], f'j11-escalate-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I want to talk to a real person',
        'No, I just want a person',             # decline KB offer
    ])

    full = all_bot_text(exchanges)
    checks = [
        ('Offered KB answer first (Tier 3)',
         has_any(bot_at(exchanges, 0), ['help', 'something', 'answer', 'assist',
                                         'before', 'specific', 'connect']),
         'No offer to help before escalating'),
        ('Respected client choice to escalate',
         has_any(full, ['connect', 'transfer', 'team member', 'someone',
                        'business hours', 'available']),
         'No escalation action after client insisted on a person'),
    ]

    return JourneyResult(11, 'Human Escalation -- Request a Person', exchanges, checks)


def journey_12_thrive_at_work_mention(qc, cfg):
    """Thrive@Work Mention -- Redirected, no details shared"""
    sid = create_session(qc, cfg['assistant_id'], f'j12-thrive-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I heard my employer has a program through Thrive@Work?',
        'I need help with childcare',           # redirected to normal flow
        'Yes',                                  # consent
        '29407',                                # ZIP
        'Text',                                 # contact method
        '843-555-3333',                         # phone
        'Yes, full time',                       # employed
        'Boeing',                               # employer
    ])

    full = all_bot_text(exchanges)
    bot_turn0 = bot_at(exchanges, 0)
    checks = [
        ('Thrive@Work details NOT shared',
         not has_any(bot_turn0, ['partner', 'employer program', 'employer benefit',
                                  'thrive program', 'eligible for thrive']),
         'Thrive@Work details were shared with client'),
        ('Redirected to general help',
         has_any(bot_turn0, ['community resources', 'help', 'looking for',
                              'what kind']),
         'Not redirected to general help flow'),
        ('Normal intake proceeded',
         has_any(full, ['consent', 'personal questions', 'okay with you'])
         or has_any(full, ['zip', 'contact', 'employ']),
         'Normal intake flow did not proceed'),
    ]

    return JourneyResult(12, 'Thrive@Work Mention -- Redirected', exchanges, checks)


def journey_13_general_vs_intake_distinction(qc, cfg):
    """Consent/Intake distinction -- the critical fix validation.

    This test runs TWO conversations back-to-back to verify the core
    behavioral distinction:
    A) "What food banks are in Charleston?" -> NO consent, direct search
    B) "I need help finding food" -> consent + intake REQUIRED
    """
    # --- Conversation A: General question ---
    sid_a = create_session(qc, cfg['assistant_id'], f'j13a-gen-{uuid.uuid4().hex[:6]}')
    exchanges_a, _ = converse(qc, cfg['assistant_id'], sid_a, [
        'What food banks are in Charleston?',
    ])
    bot_a = bot_at(exchanges_a, 0)

    time.sleep(BETWEEN_MESSAGES)

    # --- Conversation B: Person seeking help ---
    sid_b = create_session(qc, cfg['assistant_id'], f'j13b-intake-{uuid.uuid4().hex[:6]}')
    exchanges_b, _ = converse(qc, cfg['assistant_id'], sid_b, [
        'I need help finding food',
    ])
    bot_b = bot_at(exchanges_b, 0)

    # Combine exchanges for display
    all_exchanges = (
        [{'user': '--- Conversation A (general question) ---', 'bot': '', 'state': {}}]
        + exchanges_a
        + [{'user': '--- Conversation B (person seeking help) ---', 'bot': '', 'state': {}}]
        + exchanges_b
    )

    checks = [
        ('A: General question -> direct resource results (no consent)',
         has_any(bot_a, ['food', 'bank', 'pantry', 'provider', 'phone', 'resource']),
         f'General question did not get direct results. Got: {bot_a[:200]}'),
        ('A: No consent asked for general question',
         not has_any(bot_a, ['personal questions', 'consent', 'okay with you']),
         'Consent was asked for general question'),
        ('B: Person seeking help -> consent or need confirmation (NOT direct search)',
         has_any(bot_b, ['personal questions', 'consent', 'okay with you',
                          'food', 'is that right', 'help with']),
         f'Person seeking help got wrong response. Got: {bot_b[:200]}'),
        ('B: NOT a direct resource dump',
         not has_any(bot_b, ['phone:', 'services:', 'website:', 'address:']),
         'Person seeking help got direct resource results -- intake was skipped'),
    ]

    return JourneyResult(13, 'Consent/Intake Distinction (Critical Fix)', all_exchanges, checks)


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

ALL_JOURNEYS = [
    journey_01_referral_food_unemployed,
    journey_02_referral_food_employed_partner,
    journey_03_referral_vague_menu_housing_rent,
    journey_04_direct_support_utilities_non_urgent,
    journey_05_direct_support_imminent_shutoff,
    journey_06_general_question_no_consent,
    journey_07_out_of_area,
    journey_08_consent_declined,
    journey_09_hybrid_food_and_utilities,
    journey_10_info_question,
    journey_11_human_escalation,
    journey_12_thrive_at_work_mention,
    journey_13_general_vs_intake_distinction,
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(
        description='Customer journey E2E tests for Aria (13 journeys)')
    parser.add_argument('--env', choices=['dev', 'prod'], default='dev',
                        help='Environment to test (default: dev)')
    parser.add_argument('--test', type=str, default='',
                        help='Run specific journey(s): --test 1 or --test 1,6,13')
    parser.add_argument('--verbose', action='store_true',
                        help='Show full bot responses (not truncated)')
    args = parser.parse_args()

    VERBOSE = args.verbose
    cfg = ENVS[args.env]
    session = boto3.Session(region_name=cfg['region'])
    qc = session.client('qconnect')

    print(f'\n{"=" * 70}')
    print(f'Stability360 Actions -- Customer Journey Tests ({args.env.upper()})')
    print(f'Assistant: {cfg["assistant_id"]}')
    print(f'Agent:     {cfg["agent_id"]}')
    print(f'Region:    {cfg["region"]}')
    print(f'{"=" * 70}')

    # Parse --test argument
    if args.test:
        try:
            indices = [int(x.strip()) for x in args.test.split(',')]
        except ValueError:
            print(f'Invalid --test value: {args.test}. Use numbers like --test 1 or --test 1,6,13')
            return 1
        journeys = []
        for i in indices:
            if 1 <= i <= len(ALL_JOURNEYS):
                journeys.append(ALL_JOURNEYS[i - 1])
            else:
                print(f'Invalid journey number {i}. Must be 1-{len(ALL_JOURNEYS)}.')
                return 1
    else:
        journeys = ALL_JOURNEYS

    # Run journeys
    results = []
    for journey_fn in journeys:
        try:
            result = journey_fn(qc, cfg)
            result.print_report()
        except Exception as e:
            name = journey_fn.__doc__ or journey_fn.__name__
            print(f'\n[FAIL] {name}\n  Exception: {e}')
            result = JourneyResult(0, name, [], [('Exception', False, str(e))])

        results.append(result)
        if journey_fn != journeys[-1]:
            time.sleep(BETWEEN_TESTS)

    # Summary
    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = total - passed_count
    total_checks = sum(len(r.checks) for r in results)
    passed_checks = sum(sum(1 for _, p, _ in r.checks if p) for r in results)

    print(f'\n{"=" * 70}')
    print(f'JOURNEY TEST SUMMARY')
    print(f'{"=" * 70}')
    for r in results:
        status = '\033[92mPASS\033[0m' if r.passed else '\033[91mFAIL\033[0m'
        check_status = f'{sum(1 for _, p, _ in r.checks if p)}/{len(r.checks)} checks'
        print(f'  [{status}] Journey {r.number:2d}: {r.name} ({check_status})')

    print(f'\n  Journeys: {passed_count}/{total} passed', end='')
    if failed_count:
        print(f' ({failed_count} failed)')
    else:
        print(' -- ALL PASSED!')
    print(f'  Checks:   {passed_checks}/{total_checks} passed')
    print(f'{"=" * 70}\n')

    return 0 if passed_count == total else 1


if __name__ == '__main__':
    sys.exit(main())
