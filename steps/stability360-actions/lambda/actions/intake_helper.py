"""
Stability360 Actions — Intake Helper (MCP Tool)

Handler for 2 intake-support actions:
  1. getNextSteps       — Return post-search options text
  2. recordDisposition  — Record call outcome (callback, live_transfer, etc.)

Classification, ZIP validation, field requirements, and partner checks
are handled by the AI agent via KB Retrieve (knowledge base documents).
"""

import logging

from partner_employers import PARTNER_EMPLOYERS, EMPLOYER_CORRECTIONS
from queue_checker import check_queue_availability

logger = logging.getLogger('intake_helper')

# ---------------------------------------------------------------------------
# Tri-county ZIP codes (Berkeley, Charleston, Dorchester)
# ---------------------------------------------------------------------------

SERVICE_ZIPS = {
    '29018', '29059', '29401', '29403', '29404', '29405', '29406', '29407',
    '29410', '29412', '29414', '29418', '29420', '29426', '29429', '29431',
    '29432', '29434', '29436', '29437', '29438', '29445', '29448', '29449',
    '29450', '29451', '29453', '29455', '29456', '29458', '29461', '29464',
    '29466', '29468', '29469', '29470', '29471', '29472', '29477', '29479',
    '29482', '29483', '29485', '29486', '29487', '29492',
}

# ---------------------------------------------------------------------------
# Field requirements by route
# ---------------------------------------------------------------------------

# [R] route — lighter intake
ROUTE_R_FIELDS = [
    'firstName+lastName',
    'zipCode',
    'contactMethod+contactInfo',
    'employmentStatus',
    'employer',
]

# [D] route — deeper intake (all fields)
ROUTE_D_FIELDS = [
    'firstName+lastName',
    'zipCode',
    'contactMethod+contactInfo',
    'age',
    'childrenUnder18',
    'employmentStatus',
    'employer',
    'militaryAffiliation+publicAssistance',
    'housingSituation+monthlyHousingCost',
    'monthlyIncome',
]

# Categories mapped to routes
ROUTE_R_CATEGORIES = {
    'food', 'health', 'transport', 'childcare', 'employment',
    'legal', 'financial', 'repairs', 'disaster', 'hygiene',
}

ROUTE_D_CATEGORIES = {
    'utilities', 'rental', 'shelter', 'eviction',
}

# ---------------------------------------------------------------------------
# Partner employers (case-insensitive matching)
# ---------------------------------------------------------------------------

# PARTNER_EMPLOYERS and EMPLOYER_CORRECTIONS imported from partner_employers.py


# ---------------------------------------------------------------------------
# Need classification (keyword → category mapping)
# ---------------------------------------------------------------------------

NEED_KEYWORDS = {
    # Food
    'food': 'food', 'hungry': 'food', 'groceries': 'food', 'food pantry': 'food',
    'meals': 'food', 'snap': 'food', 'food stamps': 'food', 'wic': 'food',
    # Health
    'health': 'health', 'medical': 'health', 'doctor': 'health', 'dental': 'health',
    'mental health': 'health', 'counseling': 'health', 'therapy': 'health',
    'prescription': 'health', 'medicine': 'health', 'insurance': 'health',
    # Transport
    'transport': 'transport', 'transportation': 'transport', 'ride': 'transport',
    'bus': 'transport', 'car': 'transport',
    # Childcare
    'childcare': 'childcare', 'child care': 'childcare', 'daycare': 'childcare',
    'babysitter': 'childcare', 'after school': 'childcare',
    # Employment
    'employment': 'employment', 'job': 'employment', 'work': 'employment',
    'resume': 'employment', 'career': 'employment', 'training': 'employment',
    # Legal
    'legal': 'legal', 'lawyer': 'legal', 'attorney': 'legal',
    'court': 'legal', 'custody': 'legal', 'divorce': 'legal',
    # Financial
    'financial': 'financial', 'debt': 'financial', 'credit': 'financial',
    'budget': 'financial', 'taxes': 'financial', 'tax': 'financial',
    # Repairs
    'repairs': 'repairs', 'home repair': 'repairs', 'fix': 'repairs',
    # Disaster
    'disaster': 'disaster', 'flood': 'disaster', 'hurricane': 'disaster',
    'storm': 'disaster', 'fire': 'disaster',
    # Hygiene
    'hygiene': 'hygiene', 'diapers': 'hygiene', 'toiletries': 'hygiene',
    'cleaning': 'hygiene',
    # Utilities (D-route)
    'utilities': 'utilities', 'electric': 'utilities', 'electricity': 'utilities',
    'water': 'utilities', 'gas': 'utilities', 'power': 'utilities',
    'electric bill': 'utilities', 'water bill': 'utilities', 'gas bill': 'utilities',
    'light bill': 'utilities', 'shutoff': 'utilities', 'shut off': 'utilities',
    'disconnection': 'utilities',
    # Rental (D-route)
    'rental': 'rental', 'rent': 'rental', 'rent assistance': 'rental',
    'behind on rent': 'rental',
    # Shelter (D-route)
    'shelter': 'shelter', 'homeless': 'shelter', 'housing': 'shelter',
    'place to stay': 'shelter', 'no home': 'shelter',
    # Eviction (D-route)
    'eviction': 'eviction', 'evicted': 'eviction', 'eviction notice': 'eviction',
    'kicked out': 'eviction',
}

# Categories that need disambiguation
DISAMBIGUATE_CATEGORIES = {
    'utilities': {
        'question': 'Which type of utility do you need help with?',
        'options': ['Electric/Power', 'Water', 'Gas'],
    },
}

# Category menu for vague requests
CATEGORY_MENU = [
    '1. Food assistance',
    '2. Health/Medical',
    '3. Utilities (electric, water, gas)',
    '4. Rent/Housing assistance',
    '5. Shelter',
    '6. Employment/Job help',
    '7. Childcare',
    '8. Transportation',
    '9. Legal help',
    '10. Something else',
]

# Emergency keywords
EMERGENCY_KEYWORDS = {
    'shutoff', 'shut off', 'cut off', 'cutt off', 'cut electricity', 'cut my power',
    'electricity cut', 'power cut', 'water cut', 'gas cut',
    'turn off', 'turned off', 'disconnect', 'disconnection', 'disconnected',
    'about to cut', 'going to cut', 'behind on', 'not paid', 'haven\'t paid',
    'no power', 'no electricity', 'no water', 'no gas', 'no heat',
    'homeless', 'no home', 'on the street', 'no food', 'starving',
    'kicked out', 'sleeping outside', 'no place to stay',
    'eviction notice', 'being evicted', 'about to be evicted',
    'emergency', 'crisis', 'urgent',
}


# ---------------------------------------------------------------------------
# Action handlers
# ---------------------------------------------------------------------------


def _classify_need(body):
    """Classify the caller's stated need into a category."""
    need = str(body.get('need', '')).strip().lower()
    if not need:
        return {
            'classified': False,
            'menu': CATEGORY_MENU,
            'message': 'Could not classify need. Show the numbered menu to the caller.',
        }

    # Check for emergency — AI can also flag via isEmergency param
    ai_flagged = body.get('isEmergency', False)
    is_emergency = ai_flagged or any(kw in need for kw in EMERGENCY_KEYWORDS)

    # Try to match to a category
    best_match = None
    best_len = 0
    for keyword, category in NEED_KEYWORDS.items():
        if keyword in need and len(keyword) > best_len:
            best_match = category
            best_len = len(keyword)

    if not best_match:
        return {
            'classified': False,
            'isEmergency': is_emergency,
            'menu': CATEGORY_MENU,
            'message': (
                'EMERGENCY: Fast-track intake — name, ZIP, contact only.'
                if is_emergency else
                'Could not classify need. Show the numbered menu to the caller.'
            ),
        }

    result = {
        'classified': True,
        'category': best_match,
        'isEmergency': is_emergency,
    }

    # Check if disambiguation needed (skip for emergencies)
    if not is_emergency and best_match in DISAMBIGUATE_CATEGORIES:
        disambig = DISAMBIGUATE_CATEGORIES[best_match]
        result['needsDisambiguation'] = True
        result['disambiguationQuestion'] = disambig['question']
        result['options'] = disambig['options']
        result['message'] = f'Category: {best_match}. Ask which specific type.'
    else:
        result['needsDisambiguation'] = False
        if is_emergency:
            result['message'] = (
                f'EMERGENCY — category: {best_match}. '
                'Fast-track: collect name, ZIP, contact only, then search immediately.'
            )
        else:
            result['message'] = f'Category: {best_match}. Proceed to consent, then collect fields.'

    return result


def _validate_zip(body):
    """Check if ZIP code is in the tri-county service area."""
    zip_code = str(body.get('zipCode', '')).strip()
    if not zip_code:
        return {
            'valid': False,
            'message': 'No ZIP code provided. Please ask the caller for their ZIP code.',
        }

    if zip_code in SERVICE_ZIPS:
        return {
            'valid': True,
            'zipCode': zip_code,
            'message': f'ZIP {zip_code} is in our tri-county service area.',
        }

    return {
        'valid': False,
        'zipCode': zip_code,
        'message': (
            f'ZIP {zip_code} is outside our tri-county service area '
            '(Berkeley, Charleston, Dorchester counties in SC). '
            'Let the caller know and offer to connect them with our team '
            'who may be able to help find resources in their area.'
        ),
    }


FIELD_INSTRUCTIONS = (
    'Ask ALL fields in order. Do NOT skip any. Do NOT add extra fields. '
    'Combine paired fields (marked with +) into one natural question. '
    'For contactMethod+contactInfo: ask "Would you prefer to be reached '
    'by phone or email?" then ask ONLY for that one (phone number OR '
    'email address — not both).'
)


def _get_required_fields(body):
    """Return the required intake fields for a given need category."""
    category = str(body.get('category', '')).strip().lower()
    if not category:
        return {
            'route': 'unknown',
            'fields': [],
            'message': 'No category provided. Classify the need first.',
        }

    if category in ROUTE_D_CATEGORIES:
        fields = list(ROUTE_D_FIELDS)
        # Utilities: skip housingSituation+monthlyHousingCost
        if category == 'utilities':
            fields = [f for f in fields
                      if f != 'housingSituation+monthlyHousingCost']
        return {
            'route': 'D',
            'category': category,
            'fields': fields,
            'instructions': FIELD_INSTRUCTIONS,
        }

    if category in ROUTE_R_CATEGORIES:
        return {
            'route': 'R',
            'category': category,
            'fields': list(ROUTE_R_FIELDS),
            'instructions': FIELD_INSTRUCTIONS,
        }

    # Unknown category — default to R route
    return {
        'route': 'R',
        'category': category,
        'fields': list(ROUTE_R_FIELDS),
        'instructions': FIELD_INSTRUCTIONS,
    }


def _check_partner(body):
    """Check if the employer is a partner organization."""
    employer = str(body.get('employer', '')).strip()
    if not employer:
        return {
            'partnerEmployee': False,
            'suggestion': None,
            'message': 'No employer provided.',
        }

    employer_lower = employer.lower()

    # Check for misspellings first
    if employer_lower in EMPLOYER_CORRECTIONS:
        correct_name = EMPLOYER_CORRECTIONS[employer_lower]
        return {
            'partnerEmployee': False,
            'suggestion': correct_name,
            'message': f'Did you mean {correct_name}?',
        }

    # Check for exact partner match
    if employer_lower in PARTNER_EMPLOYERS:
        return {
            'partnerEmployee': True,
            'partnerEmployer': PARTNER_EMPLOYERS[employer_lower],
            'suggestion': None,
            'message': 'Partner employer confirmed.',
        }

    # Partial match — check if any partner name is contained in the input
    for key, name in PARTNER_EMPLOYERS.items():
        if key in employer_lower or employer_lower in key:
            return {
                'partnerEmployee': True,
                'partnerEmployer': name,
                'suggestion': None,
                'message': 'Partner employer confirmed.',
            }

    return {
        'partnerEmployee': False,
        'suggestion': None,
        'message': 'Not a partner employer.',
    }


def _get_next_steps(body):
    """Return post-search options for the caller.

    Checks real-time agent availability in BasicQueue. If agents are
    available, offers live transfer. Otherwise, only offers callback.
    """
    has_results = body.get('hasResults', True)
    instance_id = body.get('instance_id', '')

    # Check agent availability
    availability = check_queue_availability(instance_id or None)
    agents_available = availability.get('is_available', False)

    result = {
        'hasResults': has_results,
        'agentsAvailable': agents_available,
        'canOfferLiveTransfer': agents_available,
        'canOfferCallback': True,
        'canOfferAdditionalSearch': True,
    }

    if has_results:
        result['message'] = (
            'Resources were found. Conversationally ask the caller what they would like to do next. '
            'You may offer: callback (always available)'
            + (', speaking with someone now (agents are available)' if agents_available else '')
            + ', or searching for something else. '
            'Do NOT offer to speak with someone if agentsAvailable is false. '
            'Keep it natural — do not list numbered options.'
        )
    else:
        result['message'] = (
            'No resources were found for this search. Let the caller know gently, then ask what they would like to do. '
            'You may offer: callback (always available)'
            + (', connecting with the team (agents are available)' if agents_available else '')
            + ', or trying a different search. '
            'Do NOT offer to speak with someone if agentsAvailable is false. '
            'Keep it natural — do not list numbered options.'
        )

    return result


# Valid disposition values
VALID_DISPOSITIONS = {
    'live_transfer': 'Live Transfer — caller wants to speak with someone now',
    'callback': 'Callback — caller requested a scheduled callback',
    'additional_search': 'Additional Search — caller wants to search for more resources',
    'self_service': 'Self Service — caller will use the resources provided',
    'out_of_area': 'Out of Area — caller ZIP is outside the service area',
    'declined': 'Declined — caller declined to continue',
    'emergency': 'Emergency — caller has an urgent/crisis need',
}


def _record_disposition(body):
    """Record the call disposition/outcome type.

    If the caller requests live_transfer but no agents are available,
    automatically redirects to callback disposition.
    """
    disposition = str(body.get('disposition', '')).strip().lower().replace(' ', '_')
    if not disposition:
        return {
            'recorded': False,
            'message': 'No disposition provided. Valid values: ' + ', '.join(VALID_DISPOSITIONS.keys()),
        }

    # Normalize common phrases to valid disposition keys
    DISPOSITION_ALIASES = {
        'speak': 'live_transfer', 'speak_now': 'live_transfer', 'transfer': 'live_transfer',
        'talk': 'live_transfer', 'agent': 'live_transfer', 'connect': 'live_transfer',
        'callback': 'callback', 'call_back': 'callback', 'schedule': 'callback',
        'search': 'additional_search', 'search_again': 'additional_search',
        'something_else': 'additional_search', 'new_search': 'additional_search',
        'self': 'self_service', 'done': 'self_service', 'no_thanks': 'self_service',
        'ok': 'self_service', 'good': 'self_service',
        'out_of_area': 'out_of_area', 'outside': 'out_of_area',
        'decline': 'declined', 'no': 'declined', 'refused': 'declined',
        'emergency': 'emergency', 'urgent': 'emergency', 'crisis': 'emergency',
    }

    resolved = DISPOSITION_ALIASES.get(disposition, disposition)
    if resolved not in VALID_DISPOSITIONS:
        # Try partial match
        for alias, key in DISPOSITION_ALIASES.items():
            if alias in disposition:
                resolved = key
                break

    # If live_transfer or emergency: verify agents are available
    if resolved in ('live_transfer', 'emergency'):
        instance_id = body.get('instance_id', '')
        availability = check_queue_availability(instance_id or None)
        if not availability.get('is_available', False):
            logger.info(
                'No agents available — redirecting %s to callback', resolved,
            )
            resolved = 'callback'
            label = VALID_DISPOSITIONS.get(resolved, resolved)
            return {
                'recorded': True,
                'disposition': resolved,
                'dispositionLabel': label,
                'redirected': True,
                'redirectReason': 'no_agents_available',
                'sessionAttributes': {
                    'callDisposition': resolved,
                    'callDispositionLabel': label,
                },
                'message': (
                    'No agents are currently available. '
                    'Ask the caller: "It looks like our team members are unavailable right now. '
                    'Let me set up a callback instead — what days and times work best for you?"'
                ),
            }

    label = VALID_DISPOSITIONS.get(resolved, resolved)

    return {
        'recorded': True,
        'disposition': resolved,
        'dispositionLabel': label,
        'sessionAttributes': {
            'callDisposition': resolved,
            'callDispositionLabel': label,
        },
        'message': f'Call disposition recorded: {label}',
    }


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

ACTION_MAP = {
    'getNextSteps': _get_next_steps,
    'recordDisposition': _record_disposition,
}


def handle_intake_helper(body):
    """Route to the appropriate intake helper action."""
    if not body:
        raise ValueError('Request body is required')

    action = body.get('action', '')
    if not action:
        raise ValueError('Missing required field: action')

    handler = ACTION_MAP.get(action)
    if not handler:
        raise ValueError(
            f'Unknown action: {action}. '
            f'Valid actions: {", ".join(ACTION_MAP.keys())}'
        )

    logger.info('Intake helper: action=%s', action)
    result = handler(body)
    result['action'] = action
    return result
