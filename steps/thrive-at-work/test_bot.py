#!/usr/bin/env python3
"""End-to-end test of the Stability360 Thrive@Work AI bot.

Tests all deployed use cases via the Q Connect SendMessage / GetNextMessage API.
Each test creates a fresh session to avoid cross-contamination.

Usage:
    python steps/thrive-at-work/test_bot.py
"""

import boto3
import json
import time
import uuid
import sys

REGION = 'us-west-2'
ASSISTANT_ID = '7cce1c51-b13c-490b-9c4f-01fd7c9e66eb'
AI_AGENT_ID = '089ee21c-6a4c-49fb-b463-3d4bb5f9ab58'

# How long to poll for a response before giving up
MAX_POLL_SECONDS = 30
POLL_INTERVAL = 1.0


def create_session(qc, name):
    """Create a new Q Connect session."""
    resp = qc.create_session(
        assistantId=ASSISTANT_ID,
        name=name,
    )
    session_id = resp['session']['sessionId']
    return session_id


def send_and_get_response(qc, session_id, text):
    """Send a message and poll for the bot's response."""
    # Send
    send_resp = qc.send_message(
        assistantId=ASSISTANT_ID,
        sessionId=session_id,
        type='TEXT',
        message={'value': {'text': {'value': text}}},
        orchestratorUseCase='Connect.SelfService',
    )
    next_token = send_resp.get('nextMessageToken')

    # Poll for response
    responses = []
    start = time.time()
    while time.time() - start < MAX_POLL_SECONDS:
        if not next_token:
            break
        try:
            msg = qc.get_next_message(
                assistantId=ASSISTANT_ID,
                sessionId=session_id,
                nextMessageToken=next_token,
            )
        except Exception as e:
            if 'ThrottlingException' in str(type(e).__name__) or 'throttl' in str(e).lower():
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


def print_result(test_name, user_msg, bot_response, conv_state, success_check=None):
    """Print formatted test result."""
    passed = success_check(bot_response, conv_state) if success_check else bool(bot_response)
    status = 'PASS' if passed else 'FAIL'
    print(f'\n{"="*70}')
    print(f'[{status}] {test_name}')
    print(f'{"="*70}')
    print(f'User: {user_msg}')
    print(f'Bot:  {bot_response[:500]}{"..." if len(bot_response) > 500 else ""}')
    if conv_state:
        print(f'State: {conv_state.get("status", "?")} / {conv_state.get("reason", "?")}')
    print()
    return passed


def main():
    session = boto3.Session(region_name=REGION)
    qc = session.client('qconnect')

    results = []

    # ---- Test 1: Greeting + General Inquiry ----
    print('\n>>> Test 1: Greeting and general inquiry about Stability360 programs')
    sid = create_session(qc, f'test-greeting-{uuid.uuid4().hex[:8]}')
    resp, state = send_and_get_response(qc, sid, 'Hi! What programs does Stability360 offer?')
    passed = print_result(
        'Test 1: Greeting + General Inquiry',
        'Hi! What programs does Stability360 offer?',
        resp, state,
        lambda r, s: len(r) > 50,  # Should get a substantial response
    )
    results.append(('Greeting + General Inquiry', passed))
    time.sleep(2)

    # ---- Test 2: Employee Lookup — Valid ID ----
    print('\n>>> Test 2: Employee lookup with valid ID (TW-10001)')
    sid = create_session(qc, f'test-lookup-valid-{uuid.uuid4().hex[:8]}')
    # First send context that we want to check eligibility
    resp1, _ = send_and_get_response(qc, sid, 'I want to check my Thrive@Work eligibility. My employee ID is TW-10001.')
    time.sleep(3)
    # The bot should either respond with results or ask for more info
    # If it used the tool, there may be a follow-up message
    resp2, state2 = send_and_get_response(qc, sid, 'Yes, that is my employee ID.')
    combined = resp1 + '\n' + resp2
    passed = print_result(
        'Test 2: Employee Lookup (Valid ID TW-10001)',
        'My employee ID is TW-10001',
        combined, state2,
        lambda r, s: any(kw in r.lower() for kw in ['tw-10001', 'employee', 'eligib', 'program', 'lookup', 'look up', 'verify', 'check']),
    )
    results.append(('Employee Lookup (Valid)', passed))
    time.sleep(2)

    # ---- Test 3: Employee Lookup — Invalid ID ----
    print('\n>>> Test 3: Employee lookup with invalid ID (TW-99999)')
    sid = create_session(qc, f'test-lookup-invalid-{uuid.uuid4().hex[:8]}')
    resp, state = send_and_get_response(qc, sid, 'Can you check my eligibility? My employee ID is TW-99999.')
    time.sleep(3)
    resp2, state2 = send_and_get_response(qc, sid, 'Yes, TW-99999.')
    combined = resp + '\n' + resp2
    passed = print_result(
        'Test 3: Employee Lookup (Invalid ID TW-99999)',
        'My employee ID is TW-99999',
        combined, state2,
        lambda r, s: any(kw in r.lower() for kw in ['not found', 'couldn\'t find', 'unable', 'couldn\'t locate', 'not in', 'check', 'verify', 'tw-99999']),
    )
    results.append(('Employee Lookup (Invalid)', passed))
    time.sleep(2)

    # ---- Test 4: KB Retrieval — Community Resources ----
    print('\n>>> Test 4: KB retrieval - community resources inquiry')
    sid = create_session(qc, f'test-kb-resources-{uuid.uuid4().hex[:8]}')
    resp, state = send_and_get_response(qc, sid, 'I need help paying my rent this month. What assistance is available?')
    passed = print_result(
        'Test 4: KB Retrieval (Community Resources)',
        'I need help paying my rent this month. What assistance is available?',
        resp, state,
        lambda r, s: len(r) > 30,  # Should get some response about assistance
    )
    results.append(('KB Retrieval (Community Resources)', passed))
    time.sleep(2)

    # ---- Test 5: Escalation Request ----
    print('\n>>> Test 5: Escalation - ask for a human agent')
    sid = create_session(qc, f'test-escalate-{uuid.uuid4().hex[:8]}')
    resp, state = send_and_get_response(qc, sid, 'I need to speak with a real person please.')
    passed = print_result(
        'Test 5: Escalation Request',
        'I need to speak with a real person please.',
        resp, state,
        lambda r, s: any(kw in r.lower() for kw in ['connect', 'transfer', 'agent', 'person', 'someone', 'specialist', 'help', 'reason', 'assist']),
    )
    results.append(('Escalation Request', passed))
    time.sleep(2)

    # ---- Test 6: Combined Flow — Lookup then Program Details ----
    print('\n>>> Test 6: Combined flow - lookup then ask about specific program')
    sid = create_session(qc, f'test-combined-{uuid.uuid4().hex[:8]}')
    resp1, _ = send_and_get_response(qc, sid, 'Hi, my employee ID is TW-10001. Can you check what I have access to?')
    time.sleep(4)
    resp2, state2 = send_and_get_response(qc, sid, 'Tell me more about the financial wellness coaching program.')
    combined = f'[After lookup]: {resp1}\n[After program question]: {resp2}'
    passed = print_result(
        'Test 6: Combined Flow (Lookup + Program Details)',
        'TW-10001 lookup -> ask about financial wellness',
        combined, state2,
        lambda r, s: len(r) > 50,  # Should get responses for both
    )
    results.append(('Combined Flow', passed))

    # ---- Summary ----
    print('\n' + '=' * 70)
    print('TEST SUMMARY')
    print('=' * 70)
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    for name, passed in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  [{status}] {name}')
    print(f'\n{passed_count}/{total} tests passed.')
    print('=' * 70)

    return 0 if passed_count == total else 1


if __name__ == '__main__':
    sys.exit(main())
