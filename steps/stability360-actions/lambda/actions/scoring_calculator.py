"""
Stability360 Actions — Self-Sufficiency Matrix Scoring Calculator (MCP Tool 2)

Computes housing, employment, and financial resilience scores (1–5 each),
a composite score, priority flag, and recommended path.

Logic from Appendix C — deterministic math only.  The LLM must NOT attempt
to calculate scores itself; it MUST delegate to this tool.

Scores are stored in DynamoDB for reporting.
"""

import json
import os
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger('scoring_calculator')

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

HOUSING_SITUATION_BASE = {
    'homeless': 1,
    'shelter': 1,
    'couch_surfing': 2,
    'temporary': 2,
    'transitional': 2,
    'renting_unstable': 3,
    'renting_month_to_month': 3,
    'renting_stable': 4,
    'owner_with_mortgage': 4,
    'owner': 5,
    'owner_no_mortgage': 5,
}

EMPLOYMENT_STATUS_BASE = {
    'unable_to_work': 1,
    'unemployed': 1,
    'gig_work': 2,
    'seasonal': 2,
    'part_time': 3,
    'full_time_below_standard': 3,
    'self_employed': 3,
    'student': 3,
    'retired': 4,
    'full_time': 4,
    'full_time_above_standard': 5,
}

FICO_RANGES = {
    'below_580': -1,
    '580-669': -0.5,
    '670-739': 0,
    '740-799': 0.5,
    '800+': 1,
    'unknown': 0,
}


def _clamp(value, low=1, high=5):
    return max(low, min(high, round(value, 2)))


# ---------------------------------------------------------------------------
# Domain scorers
# ---------------------------------------------------------------------------


def _score_housing(data):
    """Housing stability score (1–5)."""
    situation = data.get('housing_situation', 'renting_stable')
    monthly_income = data.get('monthly_income', 0)
    monthly_housing_cost = data.get('monthly_housing_cost', 0)
    challenges = data.get('housing_challenges', [])

    # Base score from situation
    base = HOUSING_SITUATION_BASE.get(situation, 3)

    # Housing-to-income ratio adjustment
    ratio = monthly_housing_cost / monthly_income if monthly_income > 0 else 1.0
    if ratio > 0.50:
        ratio_adj = -2
    elif ratio > 0.40:
        ratio_adj = -1
    elif ratio > 0.30:
        ratio_adj = 0
    elif ratio > 0.20:
        ratio_adj = 0
    else:
        ratio_adj = 1

    # Challenges adjustment (-0.5 each, max -2)
    priority_challenges = {'eviction_notice', 'shutoff_notice', 'homeless'}
    challenge_adj = -0.5 * min(len(challenges), 4)

    # Priority escalation: shutoff within 72 hours or eviction notice
    priority = bool(set(challenges) & priority_challenges) or situation == 'homeless'

    raw = base + ratio_adj + challenge_adj
    score = _clamp(raw)

    return {
        'score': score,
        'base': base,
        'housing_ratio': round(ratio, 3),
        'ratio_adjustment': ratio_adj,
        'challenge_adjustment': challenge_adj,
        'challenge_count': len(challenges),
        'priority_trigger': priority,
    }


def _score_employment(data):
    """Employment stability score (1–5)."""
    status = data.get('employment_status', 'full_time')
    has_benefits = data.get('has_benefits', False)
    monthly_income = data.get('monthly_income', 0)

    base = EMPLOYMENT_STATUS_BASE.get(status, 3)

    # Benefits adjustment
    benefits_adj = 0.5 if has_benefits else -0.5

    # Income-relative adjustment (area median ~$4,200/mo for SC tri-county)
    area_standard = 4200
    if monthly_income > 0:
        income_ratio = monthly_income / area_standard
        if income_ratio < 0.50:
            income_adj = -1
        elif income_ratio < 0.80:
            income_adj = 0
        else:
            income_adj = 0.5
    else:
        income_adj = -1

    raw = base + benefits_adj + income_adj
    score = _clamp(raw)

    return {
        'score': score,
        'base': base,
        'benefits_adjustment': benefits_adj,
        'income_adjustment': income_adj,
    }


def _score_financial(data):
    """Financial resilience score (1–5)."""
    monthly_income = data.get('monthly_income', 0)
    monthly_expenses = data.get('monthly_expenses', 0)
    savings_rate = data.get('savings_rate', 0)
    fico_range = data.get('fico_range', 'unknown')

    # Expense-to-income ratio
    if monthly_income > 0:
        expense_ratio = monthly_expenses / monthly_income
    else:
        expense_ratio = 1.5

    if expense_ratio > 1.0:
        base = 1
    elif expense_ratio > 0.90:
        base = 2
    elif expense_ratio > 0.70:
        base = 3
    elif expense_ratio > 0.50:
        base = 4
    else:
        base = 5

    # Savings rate adjustment
    if savings_rate <= 0:
        savings_adj = -1
    elif savings_rate < 0.03:
        savings_adj = -0.5
    elif savings_rate < 0.10:
        savings_adj = 0
    elif savings_rate < 0.20:
        savings_adj = 0.5
    else:
        savings_adj = 1

    # FICO adjustment
    fico_adj = FICO_RANGES.get(fico_range, 0)

    raw = base + savings_adj + fico_adj
    score = _clamp(raw)

    return {
        'score': score,
        'base': base,
        'expense_ratio': round(expense_ratio, 3),
        'savings_adjustment': savings_adj,
        'fico_adjustment': fico_adj,
    }


# ---------------------------------------------------------------------------
# Composite + path recommendation
# ---------------------------------------------------------------------------


def _compute_composite(housing, employment, financial):
    """Composite score and recommended path."""
    h = housing['score']
    e = employment['score']
    f = financial['score']

    composite = round((h + e + f) / 3, 2)

    # ANY domain = 1 → PRIORITY flag
    priority = (h == 1 or e == 1 or f == 1) or housing.get('priority_trigger', False)

    # Path recommendation
    if priority or composite < 2.5:
        path = 'direct_support'
    elif composite <= 3.5:
        path = 'mixed'
    else:
        path = 'referral'

    return composite, priority, path


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------


def handle_scoring(body):
    """Compute self-sufficiency matrix scores and store results."""

    if not body:
        raise ValueError('Request body is required')

    # Compute domain scores
    housing = _score_housing(body)
    employment = _score_employment(body)
    financial = _score_financial(body)

    composite, priority, path = _compute_composite(housing, employment, financial)

    record_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    result = {
        'status': 'success',
        'record_id': record_id,
        'housing_score': housing['score'],
        'employment_score': employment['score'],
        'financial_resilience_score': financial['score'],
        'composite_score': composite,
        'priority_flag': priority,
        'recommended_path': path,
        'message': (
            f'Scoring complete. Path: {path}. '
            f'Housing={housing["score"]}, Employment={employment["score"]}, '
            f'Financial={financial["score"]}, Composite={composite}.'
        ),
    }

    # Store full details in DynamoDB (not returned to agent to keep payload small)
    logger.info(
        'Scoring details: housing=%s, employment=%s, financial=%s',
        json.dumps(housing, default=str),
        json.dumps(employment, default=str),
        json.dumps(financial, default=str),
    )

    return result
