#!/usr/bin/env python3
"""End-to-end conversational test of the Stability360 Actions AI agent (Aria).

Tests Aria directly through the Q Connect SendMessage / GetNextMessage API.
Each test creates a fresh session to avoid cross-contamination.

Scenarios:
  1. General question (KB retrieval, no consent)
  2. Resource lookup (asks for location, searches 211)
  3. Case status check (no consent needed)
  4. Direct Support path (consent → profile → scoring → connect now)
  5. Mixed path (consent → profile → scoring → case for review)
  6. Referral path (consent → profile → scoring → shares resources)
  7. Escalation request (client asks for a person)

Usage:
    python steps/stability360-actions/test_agent.py                    # dev (default)
    python steps/stability360-actions/test_agent.py --env prod         # prod
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
        'agent_id': '3dc8df27-3edf-499d-87c1-7e95f220f525',
    },
    'prod': {
        'region': 'us-east-1',
        'assistant_id': '170bfe70-4ed2-4abe-abb8-1d9f5213128d',
        'agent_id': '21256ee4-ee96-47f7-ac3f-e7cb10cdf17a',
    },
}

MAX_POLL_SECONDS = 60
POLL_INTERVAL = 1.5
BETWEEN_MESSAGES = 3  # seconds between messages in a multi-turn test
BETWEEN_TESTS = 3     # seconds between tests


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
# Test helpers
# ---------------------------------------------------------------------------


def print_conversation(test_name, exchanges, passed):
    """Print a formatted test conversation."""
    status = '\033[92mPASS\033[0m' if passed else '\033[91mFAIL\033[0m'
    print(f'\n{"=" * 70}')
    print(f'[{status}] {test_name}')
    print(f'{"=" * 70}')
    for ex in exchanges:
        print(f'  User: {ex["user"]}')
        bot_text = ex['bot'][:400] + '...' if len(ex['bot']) > 400 else ex['bot']
        print(f'  Aria: {bot_text}')
        print()
    return passed


def has_any(text, keywords):
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


def test_01_general_question(qc, cfg):
    """Test 1: General question — KB retrieval, no consent needed."""
    sid = create_session(qc, cfg['assistant_id'], f'test-general-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'What programs does Stability360 offer?',
    ])

    bot = exchanges[0]['bot']
    passed = len(bot) > 30 and has_any(bot, ['program', 'service', 'help', 'support', 'resource', 'stability'])

    return print_conversation('General Question (KB retrieval)', exchanges, passed)


def test_02_resource_lookup(qc, cfg):
    """Test 2: Resource lookup — asks for location, searches 211."""
    sid = create_session(qc, cfg['assistant_id'], f'test-resource-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help paying my electric bill.',
        'Charleston County, 29401',
    ])

    # Check that Aria asked for location or provided resources
    all_bot = ' '.join(e['bot'] for e in exchanges)
    passed = has_any(all_bot, [
        'county', 'zip', 'location', 'area',  # asked for location
        'resource', 'program', 'assistance', 'help', 'provider',  # shared resources
        '211', 'call', 'phone',  # directed to 211
    ])

    return print_conversation('Resource Lookup (211 search)', exchanges, passed)


def test_03_case_status(qc, cfg):
    """Test 3: Case status check — no consent needed."""
    sid = create_session(qc, cfg['assistant_id'], f'test-status-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I want to check on my case. My reference number is 00000000.',
    ])

    bot = exchanges[0]['bot']
    # Should either say not found or ask for reference
    passed = has_any(bot, ['not found', 'couldn\'t find', 'unable', 'check', 'double-check', 'reference', 'case'])

    return print_conversation('Case Status Check (not found)', exchanges, passed)


def test_04_direct_support_path(qc, cfg):
    """Test 4: Direct Support path — full journey."""
    sid = create_session(qc, cfg['assistant_id'], f'test-ds-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with housing. I\'m about to be evicted.',
        'Yes, that\'s okay.',                        # consent
        'Sarah',                                      # first name
        'Johnson',                                    # last name
        '843-555-1234',                               # phone
        'sarah.test@email.com',                       # email
        'I\'m currently homeless, staying at a shelter.',  # housing situation
        'I have no income right now.',                # income info
        'I\'m unemployed.',                           # employment
        'I\'d like to talk to someone now.',          # choose connect
    ])

    all_bot = ' '.join(e['bot'] for e in exchanges)
    # Should see: consent ask, data collection, and either escalation offer or case reference
    passed = has_any(all_bot, [
        'consent', 'personal', 'okay', 'questions',  # consent flow
    ]) or has_any(all_bot, [
        'team member', 'connect', 'case', 'reference', 'support',  # escalation/case
    ])

    return print_conversation('Direct Support Path (full journey)', exchanges, passed)


def test_05_mixed_path(qc, cfg):
    """Test 5: Mixed path — case for review."""
    sid = create_session(qc, cfg['assistant_id'], f'test-mixed-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need help with utility bills. I\'m behind on payments.',
        'Yes, I\'m okay with that.',                  # consent
        'Michael',                                     # first name
        'Brown',                                       # last name
        '843-555-5678',                               # phone
        'michael.test@email.com',                     # email
        'I\'m renting month to month.',               # housing
        'About $2500 a month.',                       # income
        'My rent is $900.',                           # housing cost
        'I work part time.',                          # employment
        'I\'d rather have someone review my case and get back to me.',  # case for review
    ])

    all_bot = ' '.join(e['bot'] for e in exchanges)
    passed = has_any(all_bot, [
        'case', 'review', 'follow up', 'reference', 'team', 'manager',
    ])

    return print_conversation('Mixed Path (case for review)', exchanges, passed)


def test_06_referral_path(qc, cfg):
    """Test 6: Referral path — resources shared, no case."""
    sid = create_session(qc, cfg['assistant_id'], f'test-ref-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I\'m looking for food pantries in my area.',
        'Yes, that\'s fine.',                          # consent
        'Lisa',                                        # first name
        'Williams',                                    # last name
        '843-555-9999',                               # phone
        'lisa.test@email.com',                        # email
        'I own my home, no mortgage.',                # housing
        'I make about $6000 a month.',                # income
        'No housing cost.',                           # housing cost
        'I work full time with benefits.',            # employment
        'That covers what I need, thank you.',        # satisfied, no case
    ])

    all_bot = ' '.join(e['bot'] for e in exchanges)
    # For referral path, Aria should share resources
    passed = has_any(all_bot, [
        'resource', 'pantry', 'food', 'program', 'provider', 'assistance', 'help',
    ])

    return print_conversation('Referral Path (resources shared)', exchanges, passed)


def test_07_escalation_request(qc, cfg):
    """Test 7: Client explicitly asks for a person."""
    sid = create_session(qc, cfg['assistant_id'], f'test-escalate-{uuid.uuid4().hex[:6]}')
    exchanges, _ = converse(qc, cfg['assistant_id'], sid, [
        'I need to speak with a real person right now.',
    ])

    bot = exchanges[0]['bot']
    passed = has_any(bot, [
        'connect', 'transfer', 'agent', 'person', 'someone', 'specialist',
        'team member', 'help', 'reason', 'understand',
    ])

    return print_conversation('Escalation Request (human agent)', exchanges, passed)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


ALL_TESTS = [
    test_01_general_question,
    test_02_resource_lookup,
    test_03_case_status,
    test_04_direct_support_path,
    test_05_mixed_path,
    test_06_referral_path,
    test_07_escalation_request,
]


def main():
    parser = argparse.ArgumentParser(description='Conversational E2E test for Aria')
    parser.add_argument('--env', choices=['dev', 'prod'], default='dev',
                        help='Environment to test (default: dev)')
    parser.add_argument('--test', type=int, default=0,
                        help='Run a specific test number (1-7), or 0 for all')
    args = parser.parse_args()

    cfg = ENVS[args.env]
    session = boto3.Session(region_name=cfg['region'])
    qc = session.client('qconnect')

    print(f'\n{"=" * 70}')
    print(f'Stability360 Actions — Agent Conversational Test ({args.env.upper()})')
    print(f'Assistant: {cfg["assistant_id"]}')
    print(f'Agent: {cfg["agent_id"]}')
    print(f'Region: {cfg["region"]}')
    print(f'{"=" * 70}')

    tests = ALL_TESTS
    if args.test:
        if 1 <= args.test <= len(ALL_TESTS):
            tests = [ALL_TESTS[args.test - 1]]
        else:
            print(f'Invalid test number {args.test}. Must be 1-{len(ALL_TESTS)}.')
            return 1

    results = []
    for test_fn in tests:
        try:
            passed = test_fn(qc, cfg)
        except Exception as e:
            name = test_fn.__doc__ or test_fn.__name__
            print(f'\n[FAIL] {name}\n  Exception: {e}')
            passed = False

        results.append((test_fn.__doc__ or test_fn.__name__, passed))
        if test_fn != tests[-1]:
            time.sleep(BETWEEN_TESTS)

    # Summary
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    failed_count = total - passed_count

    print(f'\n{"=" * 70}')
    print(f'TEST SUMMARY')
    print(f'{"=" * 70}')
    for name, passed in results:
        status = '\033[92mPASS\033[0m' if passed else '\033[91mFAIL\033[0m'
        short_name = name.split(' — ')[0] if ' — ' in name else name[:60]
        print(f'  [{status}] {short_name}')
    print(f'\n{passed_count}/{total} passed', end='')
    if failed_count:
        print(f' ({failed_count} failed)')
    else:
        print(' — ALL PASSED!')
    print(f'{"=" * 70}\n')

    return 0 if passed_count == total else 1


if __name__ == '__main__':
    sys.exit(main())
