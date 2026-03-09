"""
Stability360 Actions -- Auto-Scoring Wrapper

Runs scoring automatically when D-route fields (housing, income) are present
in a resourceLookup call, then proceeds with the resource search. Also handles
auto-partner detection and eligibility flag derivation.
"""

from config import (
    SCORING_TRIGGER_FIELDS, HOUSING_MAP, EMPLOYMENT_MAP, get_logger,
)
from contact_attributes import (
    derive_eligibility_flags, save_extra_attributes,
)
from partner_employers import detect_partner_attributes
from scoring_calculator import handle_scoring
from sophia_resource_lookup import handle_resource_lookup

logger = get_logger('auto_scoring')


def _map_to_enum(value, enum_map, default):
    """Map a free-text value to the closest enum using case-insensitive lookup."""
    if not value:
        return default
    val = str(value).strip().lower().replace('_', ' ')
    # Exact match
    if val in enum_map:
        return enum_map[val]
    # Already a valid enum (snake_case)
    valid_enums = set(enum_map.values())
    if val.replace(' ', '_') in valid_enums:
        return val.replace(' ', '_')
    # Partial match -- longest key contained in value
    best = None
    best_len = 0
    for key, enum_val in enum_map.items():
        if key in val and len(key) > best_len:
            best = enum_val
            best_len = len(key)
    return best or default


def _normalize_scoring_fields(body):
    """Translate camelCase field names and map free-text to scoring enums."""
    scoring_body = dict(body)

    # housing_situation
    raw = body.get('housingSituation') or body.get('housing_situation')
    if raw:
        scoring_body['housing_situation'] = _map_to_enum(raw, HOUSING_MAP, 'renting_stable')

    # employment_status
    raw = body.get('employmentStatus') or body.get('employment_status')
    if raw:
        scoring_body['employment_status'] = _map_to_enum(raw, EMPLOYMENT_MAP, 'full_time')

    # monthly_income
    if 'monthlyIncome' in body and 'monthly_income' not in body:
        scoring_body['monthly_income'] = body['monthlyIncome']

    # monthly_housing_cost
    if 'monthlyHousingCost' in body and 'monthly_housing_cost' not in body:
        scoring_body['monthly_housing_cost'] = body['monthlyHousingCost']

    return scoring_body


def _run_scoring(body):
    """Run scoring and save results as contact attributes. Returns silently on failure."""
    scoring_body = _normalize_scoring_fields(body)
    try:
        scoring_result = handle_scoring(scoring_body)

        score_attrs = {}
        score_fields = {
            'housing_score': 'housingScore', 'housing_label': 'housingLabel',
            'employment_score': 'employmentScore', 'employment_label': 'employmentLabel',
            'financial_resilience_score': 'financialResilienceScore',
            'financial_label': 'financialLabel',
            'composite_score': 'compositeScore', 'composite_label': 'compositeLabel',
            'priority_flag': 'priorityFlag', 'priority_meaning': 'priorityMeaning',
            'recommended_path': 'recommendedPath', 'path_meaning': 'pathMeaning',
        }
        for k, v in score_fields.items():
            val = scoring_result.get(k)
            if val is not None:
                score_attrs[v] = str(val).strip()

        # Human-readable summary
        summary_parts = []
        if scoring_result.get('housing_score'):
            summary_parts.append(
                f"Housing: {scoring_result['housing_score']}/5 ({scoring_result.get('housing_label', '')})"
            )
        if scoring_result.get('employment_score'):
            summary_parts.append(
                f"Employment: {scoring_result['employment_score']}/5 ({scoring_result.get('employment_label', '')})"
            )
        if scoring_result.get('financial_resilience_score'):
            summary_parts.append(
                f"Financial: {scoring_result['financial_resilience_score']}/5 ({scoring_result.get('financial_label', '')})"
            )
        if scoring_result.get('composite_score'):
            summary_parts.append(
                f"Composite: {scoring_result['composite_score']}/5 ({scoring_result.get('composite_label', '')})"
            )
        if scoring_result.get('priority_flag'):
            summary_parts.append(
                f"Priority: {scoring_result['priority_meaning'] or scoring_result['priority_flag']}"
            )
        if scoring_result.get('recommended_path'):
            summary_parts.append(
                f"Path: {scoring_result['path_meaning'] or scoring_result['recommended_path']}"
            )
        if summary_parts:
            score_attrs['scoringSummary'] = ' | '.join(summary_parts)

        save_extra_attributes(body, score_attrs)
        logger.info('Auto-scoring: saved %d scoring attributes', len(score_attrs))

    except Exception:
        logger.warning('Auto-scoring failed, continuing with resource lookup', exc_info=True)


def handle_resource_with_autoscore(body):
    """Run scoring + eligibility + partner detection, then resource lookup.

    This is the wrapper that sits between the router and sophia_resource_lookup.
    """
    # 1. Eligibility flags
    eligibility_flags = derive_eligibility_flags(body)
    if eligibility_flags:
        save_extra_attributes(body, eligibility_flags)

    # 2. Auto-scoring (only if D-route fields present)
    has_scoring = any(body.get(f) is not None for f in SCORING_TRIGGER_FIELDS)
    if has_scoring:
        logger.info('Auto-scoring: scoring fields detected in resourceLookup call')
        _run_scoring(body)

    # 3. Auto-partner detection
    employer = body.get('employer', '').strip()
    if employer:
        partner_attrs = detect_partner_attributes(employer)
        if partner_attrs:
            save_extra_attributes(body, partner_attrs)
            logger.info('Auto-partner: saved %s', partner_attrs)

    # 4. Resource lookup
    return handle_resource_lookup(body)
