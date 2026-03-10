"""
Stability360 Actions -- Shared Configuration

Central place for environment variables, constants, maps, and logger setup.
All modules import from here instead of duplicating config.
"""

import json
import logging
import os
import re

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()

CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')
CONNECT_REGION = os.environ.get('CONNECT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
RESULTS_BUCKET = os.environ.get('RESULTS_BUCKET_NAME', '')

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Partner employers (Thrive@Work program) -- defined in partner_employers.py
# Re-exported here for convenience.
# ---------------------------------------------------------------------------

from partner_employers import PARTNER_EMPLOYERS, EMPLOYER_CORRECTIONS  # noqa: E402

# ---------------------------------------------------------------------------
# Contact attribute map (request body key -> Connect attribute name)
# ---------------------------------------------------------------------------

ATTR_MAP = {
    # Core intake
    'firstName': 'firstName', 'lastName': 'lastName',
    'zipCode': 'zipCode', 'zip_code': 'zipCode',
    'contactMethod': 'contactMethod',
    'contactInfo': 'contactInfo',
    'phoneNumber': 'phoneNumber', 'emailAddress': 'emailAddress',
    'preferredDays': 'preferredDays', 'preferredTimes': 'preferredTimes',
    # Need
    'keyword': 'needCategory',
    # Demographics
    'age': 'age', 'hasChildrenUnder18': 'hasChildrenUnder18',
    'childrenUnder18': 'hasChildrenUnder18',
    'employmentStatus': 'employmentStatus',
    'employer': 'employer',
    'militaryAffiliation': 'militaryAffiliation',
    'publicAssistance': 'publicAssistance',
    # Scoring inputs
    'housingSituation': 'housingSituation',
    'monthlyIncome': 'monthlyIncome',
    'monthlyHousingCost': 'monthlyHousingCost',
    # Partner
    'partnerEmployee': 'partnerEmployee', 'partnerEmployer': 'partnerEmployer',
    # Routing
    'escalationRoute': 'escalationRoute',
    'priorityFlag': 'priorityFlag',
    # Disposition
    'disposition': 'callDisposition',
    # Task/profile/case
    'taskCreated': 'taskCreated',
    'taskContactId': 'taskContactId',
    'customerProfileId': 'customerProfileId',
    'caseId': 'caseId',
}

# ---------------------------------------------------------------------------
# Phone normalization (E.164)
# ---------------------------------------------------------------------------

def normalize_phone(phone):
    """Normalize a phone number to E.164 format (+1XXXXXXXXXX).

    Returns the normalized number, or the original string if it doesn't
    look like a valid US phone number.
    """
    digits = re.sub(r'\D', '', str(phone))
    if len(digits) == 10:
        digits = '1' + digits
    if len(digits) == 11 and digits.startswith('1'):
        return '+' + digits
    return phone  # not a recognizable phone number — return as-is


# ---------------------------------------------------------------------------
# Scoring field maps
# ---------------------------------------------------------------------------

SCORING_TRIGGER_FIELDS = {
    'housing_situation', 'monthly_income', 'monthly_housing_cost',
    'housingSituation', 'monthlyIncome', 'monthlyHousingCost',
}

HOUSING_MAP = {
    'homeless': 'homeless', 'no housing': 'homeless', 'on the street': 'homeless',
    'shelter': 'shelter', 'emergency shelter': 'shelter',
    'couch surfing': 'couch_surfing', 'staying with friends': 'couch_surfing',
    'staying with family': 'couch_surfing', 'couch': 'couch_surfing',
    'temporary': 'temporary', 'temp': 'temporary', 'temp housing': 'temporary',
    'transitional': 'transitional', 'transitional housing': 'transitional',
    'renting unstable': 'renting_unstable', 'behind on rent': 'renting_unstable',
    'month to month': 'renting_month_to_month', 'month-to-month': 'renting_month_to_month',
    'renting': 'renting_stable', 'rent': 'renting_stable', 'renter': 'renting_stable',
    'renting stable': 'renting_stable', 'lease': 'renting_stable',
    'own with mortgage': 'owner_with_mortgage', 'mortgage': 'owner_with_mortgage',
    'homeowner with mortgage': 'owner_with_mortgage',
    'own': 'owner', 'homeowner': 'owner', 'owner': 'owner',
    'own no mortgage': 'owner_no_mortgage', 'paid off': 'owner_no_mortgage',
}

EMPLOYMENT_MAP = {
    'unable to work': 'unable_to_work', 'disabled': 'unable_to_work',
    'disability': 'unable_to_work', 'cannot work': 'unable_to_work',
    'unemployed': 'unemployed', 'not working': 'unemployed', 'no job': 'unemployed',
    'looking for work': 'unemployed', 'job seeking': 'unemployed',
    'gig': 'gig_work', 'gig work': 'gig_work', 'freelance': 'gig_work',
    'seasonal': 'seasonal', 'seasonal work': 'seasonal',
    'part time': 'part_time', 'part-time': 'part_time',
    'full time below standard': 'full_time_below_standard',
    'self employed': 'self_employed', 'self-employed': 'self_employed',
    'own business': 'self_employed',
    'student': 'student', 'in school': 'student',
    'retired': 'retired', 'retirement': 'retired',
    'full time': 'full_time', 'full-time': 'full_time', 'employed': 'full_time',
    'working': 'full_time',
    'full time above standard': 'full_time_above_standard',
}

# ---------------------------------------------------------------------------
# Structured JSON logger
# ---------------------------------------------------------------------------


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'environment': ENVIRONMENT,
        }
        if hasattr(record, 'extra'):
            entry.update(record.extra)
        if record.exc_info and record.exc_info[0]:
            entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def get_logger(name):
    """Create a structured JSON logger."""
    lgr = logging.getLogger(name)
    lgr.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    if not lgr.handlers:
        h = logging.StreamHandler()
        h.setFormatter(StructuredFormatter())
        lgr.addHandler(h)
    return lgr
