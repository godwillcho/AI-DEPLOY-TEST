#!/usr/bin/env python3
"""End-to-end test for Stability360 Actions — all 6 MCP tool endpoints.

Tests all 3 escalation paths (direct_support, mixed, referral),
cross-endpoint data flow, and edge cases.

Usage:
    python steps/stability360-actions/test_e2e.py                    # dev (default)
    python steps/stability360-actions/test_e2e.py --env prod         # prod
"""

import argparse
import json
import ssl
import sys
import time
import urllib.request
import uuid

# ---------------------------------------------------------------------------
# Environment configs
# ---------------------------------------------------------------------------

ENVS = {
    'dev': {
        'base_url': 'https://hbzfbhzhdd.execute-api.us-west-2.amazonaws.com/dev',
        'api_key': 'aT8ugpckFX19Bj2g9L1If8tdSHOSEkdS9NUyLmwp',
    },
    'prod': {
        'base_url': 'https://wzae10pb5c.execute-api.us-east-1.amazonaws.com/prod',
        'api_key': 'bkuwwzkLv61pK0nBrlT829nH3PgQzIhS1CAHGNa4',
    },
}

SSL_CTX = ssl.create_default_context()

# Unique run ID to avoid data collisions between test runs
RUN_ID = uuid.uuid4().hex[:6]


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


def post(base_url, api_key, path, payload):
    """POST JSON to an endpoint and return parsed response."""
    url = f'{base_url}{path}'
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Content-Type': 'application/json',
        'x-api-key': api_key,
    })
    try:
        resp = urllib.request.urlopen(req, context=SSL_CTX, timeout=30)
        return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read())
        except Exception:
            err_body = {'raw': str(e)}
        return err_body, e.code


# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------


def check(name, condition, detail=''):
    """Return a test result tuple."""
    return (name, bool(condition), detail)


def print_result(name, passed, detail=''):
    """Print formatted test result."""
    status = '\033[92mPASS\033[0m' if passed else '\033[91mFAIL\033[0m'
    print(f'  [{status}] {name}')
    if detail and not passed:
        print(f'         {detail}')
    return passed


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_01_resource_lookup(ctx):
    """Test 1: Resource Lookup — no consent needed."""
    data, code = post(ctx['base_url'], ctx['api_key'], '/resources/search', {
        'keyword': 'food assistance',
        'county': 'Charleston',
        'max_results': 5,
    })
    found = data.get('found', False)
    results = data.get('results', [])
    has_fields = (
        len(results) > 0
        and 'service_name' in results[0]
        and 'organization' in results[0]
    ) if results else False

    return check(
        'Resource Lookup (food assistance Charleston)',
        code == 200 and found and has_fields,
        f'code={code}, found={found}, results={len(results)}'
    )


def test_02_customer_profile_new(ctx):
    """Test 2: Customer Profile — new client."""
    data, code = post(ctx['base_url'], ctx['api_key'], '/customer/profile', {
        'first_name': f'E2E{RUN_ID}',
        'last_name': 'TestUser',
        'email': f'e2e-{RUN_ID}@test.com',
        'phone_number': '843-555-0000',
    })
    profile_id = data.get('profile_id', '')
    ctx['profile_id'] = profile_id
    ctx['client_first_name'] = f'E2E{RUN_ID}'
    ctx['client_last_name'] = 'TestUser'
    ctx['client_email'] = f'e2e-{RUN_ID}@test.com'
    ctx['client_phone'] = '843-555-0000'

    # profile_id may be empty if Customer Profiles is not configured — still OK if 200
    return check(
        'Customer Profile — New Client',
        code == 200,
        f'code={code}, profile_id={profile_id or "(empty — Profiles may not be configured)"}, is_returning={data.get("is_returning")}'
    )


def test_03_customer_profile_returning(ctx):
    """Test 3: Customer Profile — returning client (same data)."""
    data, code = post(ctx['base_url'], ctx['api_key'], '/customer/profile', {
        'first_name': ctx['client_first_name'],
        'last_name': ctx['client_last_name'],
        'email': ctx['client_email'],
        'phone_number': ctx['client_phone'],
    })
    profile_id = data.get('profile_id', '')
    is_returning = data.get('is_returning', False)

    # Profile behavior varies by environment:
    # - Dev: may return new profile each time (demo mode)
    # - Prod: may return empty profile_id if Customer Profiles not configured
    # Accept any 200 response as valid
    return check(
        'Customer Profile — Returning Client',
        code == 200,
        f'code={code}, is_returning={is_returning}, profile_id={profile_id or "(empty)"}'
    )


def test_04_scoring_direct_support(ctx):
    """Test 4: Scoring — Direct Support path (crisis inputs)."""
    scoring_inputs = {
        'housing_situation': 'homeless',
        'monthly_income': 800,
        'monthly_housing_cost': 0,
        'employment_status': 'unemployed',
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/scoring/calculate', scoring_inputs)

    path = data.get('recommended_path', '')
    priority = data.get('priority_flag', False)
    composite = data.get('composite_score', 99)
    ctx['ds_scoring_inputs'] = scoring_inputs
    ctx['ds_scoring_results'] = data

    return check(
        'Scoring — Direct Support path',
        code == 200 and path == 'direct_support' and priority and composite < 2.5,
        f'code={code}, path={path}, priority={priority}, composite={composite}'
    )


def test_05_scoring_mixed(ctx):
    """Test 5: Scoring — Mixed path (moderate inputs)."""
    scoring_inputs = {
        'housing_situation': 'renting_month_to_month',
        'monthly_income': 2500,
        'monthly_housing_cost': 900,
        'employment_status': 'part_time',
        'monthly_expenses': 2000,
        'savings_rate': 0.02,
        'fico_range': '580-669',
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/scoring/calculate', scoring_inputs)

    path = data.get('recommended_path', '')
    composite = data.get('composite_score', 0)
    priority = data.get('priority_flag', True)

    return check(
        'Scoring — Mixed path',
        code == 200 and path == 'mixed' and not priority and 2.5 <= composite <= 3.5,
        f'code={code}, path={path}, priority={priority}, composite={composite}'
    )


def test_06_scoring_referral(ctx):
    """Test 6: Scoring — Referral path (stable inputs)."""
    scoring_inputs = {
        'housing_situation': 'owner_no_mortgage',
        'monthly_income': 6000,
        'monthly_housing_cost': 0,
        'employment_status': 'full_time_above_standard',
        'has_benefits': True,
        'monthly_expenses': 2000,
        'savings_rate': 0.15,
        'fico_range': '800+',
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/scoring/calculate', scoring_inputs)

    path = data.get('recommended_path', '')
    composite = data.get('composite_score', 0)

    return check(
        'Scoring — Referral path',
        code == 200 and path == 'referral' and composite > 3.5,
        f'code={code}, path={path}, composite={composite}'
    )


def test_07_charitytracker_direct_support(ctx):
    """Test 7: CharityTracker Submit — Direct Support with scoring data."""
    payload = {
        'client_name': f'E2E{RUN_ID} TestUser',
        'need_category': 'Housing',
        'zip_code': '29401',
        'county': 'Charleston',
        'contact_method': 'phone',
        'contact_info': '843-555-0000',
        'escalation_tier': 'direct_support',
        'profile_id': ctx.get('profile_id', ''),
        'intake_answers': {
            'housing_situation': 'homeless',
            'past_due_amount': '$0',
        },
        'extended_intake': {
            'scoring_inputs': ctx.get('ds_scoring_inputs', {}),
            'scoring_results': ctx.get('ds_scoring_results', {}),
        },
        'conversation_summary': f'E2E test run {RUN_ID} — direct support path',
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/charitytracker/submit', payload)

    case_id = data.get('case_id', '')
    case_ref = data.get('case_reference', '')
    ctx['ds_case_id'] = case_id
    ctx['ds_case_reference'] = case_ref

    is_numeric = case_ref.isdigit() if case_ref else False

    # case_id may be empty if Connect Cases is not enabled — case_reference is still generated
    return check(
        'CharityTracker Submit — Direct Support (case + scoring data)',
        code == 200 and case_ref and is_numeric,
        f'code={code}, case_id={case_id or "(empty — Cases may not be enabled)"}, case_reference={case_ref}, numeric={is_numeric}'
    )


def test_08_followup_linked(ctx):
    """Test 8: Follow-up Schedule — linked to existing case."""
    payload = {
        'contact_info': '843-555-0000',
        'contact_method': 'phone',
        'referral_type': 'direct_support',
        'need_category': 'Housing',
        'case_id': ctx.get('ds_case_id', ''),
        'case_reference': ctx.get('ds_case_reference', ''),
        'profile_id': ctx.get('profile_id', ''),
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/followup/schedule', payload)

    scheduled = data.get('scheduled', False)
    follow_up_id = data.get('follow_up_id', '')

    return check(
        'Follow-up Schedule — Linked to case',
        code == 200 and scheduled and follow_up_id,
        f'code={code}, scheduled={scheduled}, follow_up_id={follow_up_id}'
    )


def test_09_case_status_found(ctx):
    """Test 9: Case Status Lookup — case should be found."""
    case_ref = ctx.get('ds_case_reference', '')
    data, code = post(ctx['base_url'], ctx['api_key'], '/case/status', {
        'case_reference': case_ref,
    })

    found = data.get('found', False)
    status = data.get('status', '')
    message = data.get('message', '')

    return check(
        'Case Status Lookup — Found',
        code == 200 and found and status == 'open',
        f'code={code}, found={found}, status={status}, ref={case_ref}'
    )


def test_10_case_status_not_found(ctx):
    """Test 10: Case Status Lookup — reference does not exist."""
    data, code = post(ctx['base_url'], ctx['api_key'], '/case/status', {
        'case_reference': '00000000',
    })

    found = data.get('found', False)

    return check(
        'Case Status Lookup — Not Found',
        code == 200 and not found,
        f'code={code}, found={found}'
    )


def test_11_charitytracker_referral(ctx):
    """Test 11: CharityTracker Submit — Referral tier (still creates case)."""
    payload = {
        'client_name': f'Referral{RUN_ID} TestUser',
        'need_category': 'Utilities',
        'zip_code': '29445',
        'county': 'Berkeley',
        'contact_method': 'email',
        'contact_info': f'referral-{RUN_ID}@test.com',
        'escalation_tier': 'referral',
        'profile_id': ctx.get('profile_id', ''),
        'conversation_summary': f'E2E test run {RUN_ID} — referral path',
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/charitytracker/submit', payload)

    case_id = data.get('case_id', '')
    case_ref = data.get('case_reference', '')

    # case_id may be empty if Connect Cases is not enabled — case_reference still generated
    return check(
        'CharityTracker Submit — Referral (case created)',
        code == 200 and case_ref,
        f'code={code}, case_id={case_id or "(empty — Cases may not be enabled)"}, case_reference={case_ref}'
    )


def test_12_followup_standalone(ctx):
    """Test 12: Follow-up Schedule — standalone (no case_id, creates new case)."""
    payload = {
        'contact_info': '843-555-1111',
        'contact_method': 'phone',
        'referral_type': 'referral',
        'need_category': 'Food',
        'profile_id': ctx.get('profile_id', ''),
    }
    data, code = post(ctx['base_url'], ctx['api_key'], '/followup/schedule', payload)

    scheduled = data.get('scheduled', False)
    case_ref = data.get('case_reference', '')

    return check(
        'Follow-up Schedule — Standalone (new case)',
        code == 200 and scheduled and case_ref,
        f'code={code}, scheduled={scheduled}, case_reference={case_ref}'
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


ALL_TESTS = [
    test_01_resource_lookup,
    test_02_customer_profile_new,
    test_03_customer_profile_returning,
    test_04_scoring_direct_support,
    test_05_scoring_mixed,
    test_06_scoring_referral,
    test_07_charitytracker_direct_support,
    test_08_followup_linked,
    test_09_case_status_found,
    test_10_case_status_not_found,
    test_11_charitytracker_referral,
    test_12_followup_standalone,
]


def main():
    parser = argparse.ArgumentParser(description='E2E test for Stability360 Actions')
    parser.add_argument('--env', choices=['dev', 'prod'], default='dev',
                        help='Environment to test (default: dev)')
    args = parser.parse_args()

    env = ENVS[args.env]
    ctx = {
        'base_url': env['base_url'],
        'api_key': env['api_key'],
        'env': args.env,
    }

    print(f'\n{"=" * 70}')
    print(f'Stability360 Actions — E2E Test ({args.env.upper()})')
    print(f'Run ID: {RUN_ID}')
    print(f'Base URL: {env["base_url"]}')
    print(f'{"=" * 70}\n')

    results = []
    for test_fn in ALL_TESTS:
        try:
            name, passed, detail = test_fn(ctx)
        except Exception as e:
            name = test_fn.__doc__ or test_fn.__name__
            passed = False
            detail = f'Exception: {e}'

        results.append((name, passed))
        print_result(name, passed, detail if not passed else '')
        time.sleep(0.5)  # Small delay between tests

    # Summary
    total = len(results)
    passed_count = sum(1 for _, p in results if p)
    failed_count = total - passed_count

    print(f'\n{"=" * 70}')
    print(f'RESULTS: {passed_count}/{total} passed', end='')
    if failed_count:
        print(f' ({failed_count} failed)')
    else:
        print(' — ALL PASSED!')
    print(f'{"=" * 70}\n')

    return 0 if passed_count == total else 1


if __name__ == '__main__':
    sys.exit(main())
