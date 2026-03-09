"""
Stability360 Actions -- Partner Employers (Thrive@Work)

Manages the list of Thrive@Work partner employers and common misspellings.
To add a new partner: add an entry to PARTNER_EMPLOYERS below.
To add a misspelling correction: add an entry to EMPLOYER_CORRECTIONS.
"""

# ---------------------------------------------------------------------------
# Partner employer list (lowercase key -> display name)
# ---------------------------------------------------------------------------

PARTNER_EMPLOYERS = {
    'amazon': 'Amazon',
    'boeing': 'Boeing',
    'volvo': 'Volvo',
    'bosch': 'Bosch',
    'blackbaud': 'Blackbaud',
    'musc': 'MUSC',
    'medical university': 'MUSC',
    'roper': 'Roper St. Francis',
    'trident health': 'Trident Health',
}

# ---------------------------------------------------------------------------
# Common misspellings -> correct employer name
# ---------------------------------------------------------------------------

EMPLOYER_CORRECTIONS = {
    'amazona': 'Amazon',
    'amazom': 'Amazon',
    'amozon': 'Amazon',
    'boieng': 'Boeing',
    'boeng': 'Boeing',
    'boing': 'Boeing',
    'volve': 'Volvo',
    'volvio': 'Volvo',
    'blackbad': 'Blackbaud',
    'blackbuad': 'Blackbaud',
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def check_partner(employer):
    """Check if an employer is a Thrive@Work partner.

    Returns dict with:
      - partnerEmployee (bool)
      - partnerEmployer (str or None)
      - suggestion (str or None) -- for misspelling corrections
      - message (str)
    """
    if not employer:
        return {
            'partnerEmployee': False,
            'suggestion': None,
            'message': 'No employer provided.',
        }

    employer_lower = employer.strip().lower()

    # Check misspellings first
    if employer_lower in EMPLOYER_CORRECTIONS:
        correct_name = EMPLOYER_CORRECTIONS[employer_lower]
        return {
            'partnerEmployee': False,
            'suggestion': correct_name,
            'message': f'Did you mean {correct_name}?',
        }

    # Exact match
    if employer_lower in PARTNER_EMPLOYERS:
        return {
            'partnerEmployee': True,
            'partnerEmployer': PARTNER_EMPLOYERS[employer_lower],
            'suggestion': None,
            'message': 'Partner employer confirmed.',
        }

    # Partial match
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


def detect_partner_attributes(employer):
    """Auto-detect partner status and return contact attributes to save.

    Returns dict of attributes (empty if not a partner).
    """
    if not employer:
        return {}

    employer_lower = employer.strip().lower()
    attrs = {}

    if employer_lower in EMPLOYER_CORRECTIONS:
        corrected = EMPLOYER_CORRECTIONS[employer_lower]
        attrs = {'partnerEmployee': 'true', 'partnerEmployer': corrected, 'employer': corrected}
    elif employer_lower in PARTNER_EMPLOYERS:
        attrs = {'partnerEmployee': 'true', 'partnerEmployer': PARTNER_EMPLOYERS[employer_lower]}
    else:
        for key, name in PARTNER_EMPLOYERS.items():
            if key in employer_lower or employer_lower in key:
                attrs = {'partnerEmployee': 'true', 'partnerEmployer': name}
                break

    return attrs
