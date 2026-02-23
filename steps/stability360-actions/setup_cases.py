"""
Stability360 — Amazon Connect Cases Setup

Standalone script to create all case fields and a case template
for the Stability360 AI agent session attributes.

This script:
  1. Finds or creates the Cases domain for the Connect instance
  2. Creates 39 custom case fields matching all session attributes
  3. Creates a layout with fields organized into sections
  4. Creates a case template named "Stability360 Intake" with the layout

Usage:
  python setup_cases.py --connect-instance-id <INSTANCE_ID> --region <REGION>
  python setup_cases.py --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d --region us-west-2
  python setup_cases.py --teardown --connect-instance-id <INSTANCE_ID> --region <REGION>

Prerequisites:
  pip install boto3
"""

import argparse
import boto3
import json
import logging
import sys
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s',
                    datefmt='%H:%M:%S')
logger = logging.getLogger('setup_cases')

TEMPLATE_NAME = 'Stability360 Intake'
LAYOUT_NAME = 'Stability360 Layout'

# ---------------------------------------------------------------------------
# All 39 session attributes as case fields
# ---------------------------------------------------------------------------

FIELD_DEFINITIONS = [
    # --- Core Attributes (from intake) ---
    {'name': 'firstName',        'description': "Client's first name",                     'type': 'Text'},
    {'name': 'lastName',         'description': "Client's last name",                      'type': 'Text'},
    {'name': 'zipCode',          'description': "Client's ZIP code",                       'type': 'Text'},
    {'name': 'county',           'description': 'County derived from ZIP or asked directly','type': 'Text'},
    {'name': 'contactMethod',    'description': 'Preferred contact method (phone_call, text, email)', 'type': 'Text'},
    {'name': 'phoneNumber',      'description': 'Phone in E.164 format (+1XXXXXXXXXX)',    'type': 'Text'},
    {'name': 'emailAddress',     'description': "Client's email address",                  'type': 'Text'},
    {'name': 'preferredDays',    'description': 'Days available for follow-up contact',    'type': 'Text'},
    {'name': 'preferredTimes',   'description': 'Time of day preference for contact',      'type': 'Text'},

    # --- Need Attributes ---
    {'name': 'needCategory',     'description': 'Primary need category (e.g. Housing, Food)', 'type': 'Text'},
    {'name': 'needSubcategory',  'description': 'Specific subcategory (e.g. Utilities, Food Pantries)', 'type': 'Text'},
    {'name': 'path',             'description': 'Intake path: referral or direct_support', 'type': 'Text'},

    # --- Need-Specific Attributes ---
    {'name': 'age',                  'description': "Client's age",                        'type': 'Text'},
    {'name': 'hasChildrenUnder18',   'description': 'Children under 18 at home (true/false)', 'type': 'Text'},
    {'name': 'employmentStatus',     'description': 'Current employment status',           'type': 'Text'},
    {'name': 'employer',             'description': 'Employer name (if employed)',          'type': 'Text'},
    {'name': 'militaryAffiliation',  'description': 'Military or service affiliation',     'type': 'Text'},
    {'name': 'publicAssistance',     'description': 'Public benefits received (SNAP, Medicaid, etc.)', 'type': 'Text'},

    # --- Scoring Inputs (Direct Support path only) ---
    {'name': 'housingSituation',         'description': 'Current housing situation for scoring', 'type': 'Text'},
    {'name': 'monthlyIncome',            'description': 'Monthly household income in dollars',   'type': 'Text'},
    {'name': 'monthlyHousingCost',       'description': 'Monthly rent or mortgage in dollars',   'type': 'Text'},
    {'name': 'monthlyExpenses',          'description': 'Total monthly expenses in dollars',     'type': 'Text'},
    {'name': 'savingsRate',              'description': 'Savings rate as decimal',               'type': 'Text'},
    {'name': 'ficoRange',               'description': 'Credit score range',                    'type': 'Text'},
    {'name': 'hasBenefits',             'description': 'Whether employer provides benefits',    'type': 'Text'},

    # --- Scoring Results ---
    {'name': 'housingScore',             'description': 'Housing stability score (1-5)',         'type': 'Text'},
    {'name': 'employmentScore',          'description': 'Employment stability score (1-5)',      'type': 'Text'},
    {'name': 'financialResilienceScore', 'description': 'Financial resilience score (1-5)',      'type': 'Text'},
    {'name': 'compositeScore',           'description': 'Average of 3 domain scores',           'type': 'Text'},
    {'name': 'priorityFlag',            'description': 'Urgent priority indicator',             'type': 'Text'},
    {'name': 'recommendedPath',         'description': 'Scoring-based path recommendation',    'type': 'Text'},

    # --- Partner Attributes ---
    {'name': 'partnerEmployee',  'description': 'Whether client works for a Thrive@Work partner', 'type': 'Text'},
    {'name': 'partnerEmployer',  'description': 'Name of the partner employer',            'type': 'Text'},

    # --- Eligibility Flags ---
    {'name': 'eligibleBCDCOG',               'description': 'Eligible for BCDCOG services (age 65+)',        'type': 'Text'},
    {'name': 'eligibleSiemer',               'description': 'Eligible for Siemer / Rental Reserve (children under 18)', 'type': 'Text'},
    {'name': 'eligibleMissionUnited',        'description': 'Eligible for Mission United (veteran/active duty)',        'type': 'Text'},
    {'name': 'eligibleBarriersToEmployment', 'description': 'Eligible for Barriers to Employment (looking for work)',   'type': 'Text'},
    {'name': 'employmentServicesNeeded',     'description': 'Flag that employment services are needed',                 'type': 'Text'},

    # --- Routing Attributes ---
    {'name': 'escalationRoute',  'description': 'Routing: live_agent or callback',         'type': 'Text'},
]

# Layout fields for the Cases UI (one section per panel — API limitation)
# topPanel: primary fields visible at top of case
# moreInfo: additional details in the "More Info" tab
LAYOUT_TOP_FIELDS = [
    # Client info
    'firstName', 'lastName', 'zipCode', 'county',
    'contactMethod', 'phoneNumber', 'emailAddress',
    'preferredDays', 'preferredTimes',
    # Need assessment
    'needCategory', 'needSubcategory', 'path',
    # Scoring results
    'housingScore', 'employmentScore', 'financialResilienceScore',
    'compositeScore', 'priorityFlag', 'recommendedPath',
    # Routing
    'escalationRoute',
]

LAYOUT_MORE_INFO_FIELDS = [
    # Need-specific details
    'age', 'hasChildrenUnder18', 'employmentStatus', 'employer',
    'militaryAffiliation', 'publicAssistance',
    # Scoring inputs
    'housingSituation', 'monthlyIncome', 'monthlyHousingCost',
    'monthlyExpenses', 'savingsRate', 'ficoRange', 'hasBenefits',
    # Partner & eligibility
    'partnerEmployee', 'partnerEmployer', 'eligibleBCDCOG',
    'eligibleSiemer', 'eligibleMissionUnited',
    'eligibleBarriersToEmployment', 'employmentServicesNeeded',
]

# Required fields for the template (must have a value to create a case)
REQUIRED_FIELD_NAMES = ['firstName', 'lastName', 'zipCode', 'needCategory', 'path']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_cases_domain(connect_client, cases_client, instance_id):
    """Find the Cases domain associated with the Connect instance."""
    next_token = None
    while True:
        kwargs = {}
        if next_token:
            kwargs['nextToken'] = next_token
        resp = cases_client.list_domains(**kwargs)
        for domain in resp.get('domains', []):
            logger.info('Found Cases domain: %s (%s)', domain['name'], domain['domainId'])
            return domain['domainId']
        next_token = resp.get('nextToken')
        if not next_token:
            break

    logger.error('No Cases domain found. Enable Cases in the Amazon Connect console first.')
    sys.exit(1)


def _list_all(client, method_name, key, **kwargs):
    """Generic paginator using nextToken for connectcases APIs."""
    results = []
    next_token = None
    while True:
        call_kwargs = dict(kwargs)
        if next_token:
            call_kwargs['nextToken'] = next_token
        resp = getattr(client, method_name)(**call_kwargs)
        results.extend(resp.get(key, []))
        next_token = resp.get('nextToken')
        if not next_token:
            break
    return results


def get_existing_fields(cases_client, domain_id):
    """Get all existing fields in the domain, returning a name->id map."""
    fields = _list_all(cases_client, 'list_fields', 'fields', domainId=domain_id)
    return {f['name']: f['fieldId'] for f in fields}


def get_existing_templates(cases_client, domain_id):
    """Get all existing templates in the domain, returning a name->id map."""
    templates = _list_all(cases_client, 'list_templates', 'templates', domainId=domain_id)
    return {t['name']: t['templateId'] for t in templates}


def get_existing_layouts(cases_client, domain_id):
    """Get all existing layouts in the domain, returning a name->id map."""
    layouts = _list_all(cases_client, 'list_layouts', 'layouts', domainId=domain_id)
    return {l['name']: l['layoutId'] for l in layouts}


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------


def create_fields(cases_client, domain_id):
    """Create all case fields. Skips fields that already exist."""
    existing = get_existing_fields(cases_client, domain_id)
    field_map = {}  # name -> fieldId

    for defn in FIELD_DEFINITIONS:
        name = defn['name']
        if name in existing:
            logger.info('  Field already exists: %s (%s)', name, existing[name])
            field_map[name] = existing[name]
            continue

        try:
            resp = cases_client.create_field(
                domainId=domain_id,
                name=name,
                description=defn['description'],
                type=defn['type'],
            )
            field_id = resp['fieldId']
            field_map[name] = field_id
            logger.info('  Created field: %s (%s)', name, field_id)
        except cases_client.exceptions.ConflictException:
            # Race condition — field was created between list and create
            logger.info('  Field already exists (conflict): %s', name)
            refreshed = get_existing_fields(cases_client, domain_id)
            field_map[name] = refreshed.get(name, '')
        except Exception as e:
            logger.error('  Failed to create field %s: %s', name, e)
            raise

    return field_map


def create_layout(cases_client, domain_id, field_map):
    """Create the layout with fields organized into sections."""
    existing = get_existing_layouts(cases_client, domain_id)

    if LAYOUT_NAME in existing:
        layout_id = existing[LAYOUT_NAME]
        logger.info('  Layout already exists: %s (%s) — updating...', LAYOUT_NAME, layout_id)
        content = _build_layout_content(field_map)
        cases_client.update_layout(
            domainId=domain_id,
            layoutId=layout_id,
            name=LAYOUT_NAME,
            content=content,
        )
        logger.info('  Layout updated.')
        return layout_id

    content = _build_layout_content(field_map)
    resp = cases_client.create_layout(
        domainId=domain_id,
        name=LAYOUT_NAME,
        content=content,
    )
    layout_id = resp['layoutId']
    logger.info('  Created layout: %s (%s)', LAYOUT_NAME, layout_id)
    return layout_id


def _build_layout_content(field_map):
    """Build the layout content structure (one section per panel)."""
    def build_field_list(field_names):
        fields = []
        for name in field_names:
            fid = field_map.get(name)
            if fid:
                fields.append({'id': fid})
            else:
                logger.warning('  Field %s not found in field_map — skipping in layout', name)
        return fields

    return {
        'basic': {
            'topPanel': {
                'sections': [{
                    'fieldGroup': {
                        'fields': build_field_list(LAYOUT_TOP_FIELDS),
                    }
                }]
            },
            'moreInfo': {
                'sections': [{
                    'fieldGroup': {
                        'fields': build_field_list(LAYOUT_MORE_INFO_FIELDS),
                    }
                }]
            },
        }
    }


def create_template(cases_client, domain_id, field_map, layout_id):
    """Create the case template with required fields and layout."""
    existing = get_existing_templates(cases_client, domain_id)

    required_fields = []
    for name in REQUIRED_FIELD_NAMES:
        fid = field_map.get(name)
        if fid:
            required_fields.append({'fieldId': fid})

    if TEMPLATE_NAME in existing:
        template_id = existing[TEMPLATE_NAME]
        logger.info('  Template already exists: %s (%s) — updating...', TEMPLATE_NAME, template_id)
        cases_client.update_template(
            domainId=domain_id,
            templateId=template_id,
            name=TEMPLATE_NAME,
            description='Case template for Stability360 AI agent intake — 39 session attributes',
            layoutConfiguration={'defaultLayout': layout_id},
            requiredFields=required_fields,
            status='Active',
        )
        logger.info('  Template updated.')
        return template_id

    resp = cases_client.create_template(
        domainId=domain_id,
        name=TEMPLATE_NAME,
        description='Case template for Stability360 AI agent intake — 39 session attributes',
        layoutConfiguration={'defaultLayout': layout_id},
        requiredFields=required_fields,
        status='Active',
    )
    template_id = resp['templateId']
    logger.info('  Created template: %s (%s)', TEMPLATE_NAME, template_id)
    return template_id


# ---------------------------------------------------------------------------
# Teardown
# ---------------------------------------------------------------------------


def teardown(cases_client, domain_id):
    """Delete the template, layout, and all custom fields created by this script."""
    # Delete template
    existing_templates = get_existing_templates(cases_client, domain_id)
    if TEMPLATE_NAME in existing_templates:
        template_id = existing_templates[TEMPLATE_NAME]
        # Must deactivate before deleting
        try:
            cases_client.update_template(
                domainId=domain_id,
                templateId=template_id,
                status='Inactive',
            )
        except Exception:
            pass
        cases_client.delete_template(
            domainId=domain_id,
            templateId=template_id,
        )
        logger.info('  Deleted template: %s', TEMPLATE_NAME)
    else:
        logger.info('  Template not found: %s — skipping', TEMPLATE_NAME)

    # Delete layout
    existing_layouts = get_existing_layouts(cases_client, domain_id)
    if LAYOUT_NAME in existing_layouts:
        layout_id = existing_layouts[LAYOUT_NAME]
        cases_client.delete_layout(
            domainId=domain_id,
            layoutId=layout_id,
        )
        logger.info('  Deleted layout: %s', LAYOUT_NAME)
    else:
        logger.info('  Layout not found: %s — skipping', LAYOUT_NAME)

    # Delete fields
    existing_fields = get_existing_fields(cases_client, domain_id)
    field_names = {d['name'] for d in FIELD_DEFINITIONS}
    deleted = 0
    for name in field_names:
        if name in existing_fields:
            try:
                cases_client.delete_field(
                    domainId=domain_id,
                    fieldId=existing_fields[name],
                )
                logger.info('  Deleted field: %s', name)
                deleted += 1
            except Exception as e:
                logger.warning('  Could not delete field %s: %s', name, e)
    logger.info('  Deleted %d/%d fields', deleted, len(field_names))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description='Stability360 — Amazon Connect Cases Setup')
    parser.add_argument('--connect-instance-id', required=True,
                        help='Amazon Connect instance ID')
    parser.add_argument('--region', default='us-west-2',
                        help='AWS region (default: us-west-2)')
    parser.add_argument('--teardown', action='store_true',
                        help='Delete template, layout, and all custom fields')
    args = parser.parse_args()

    logger.info('=' * 60)
    logger.info('Stability360 — Cases Setup')
    logger.info('=' * 60)
    logger.info('Region:     %s', args.region)
    logger.info('Instance:   %s', args.connect_instance_id)

    connect_client = boto3.client('connect', region_name=args.region)
    cases_client = boto3.client('connectcases', region_name=args.region)

    # Step 1: Find Cases domain
    logger.info('')
    logger.info('Step 1: Finding Cases domain...')
    domain_id = get_cases_domain(connect_client, cases_client, args.connect_instance_id)
    logger.info('Using domain: %s', domain_id)

    if args.teardown:
        logger.info('')
        logger.info('Tearing down...')
        teardown(cases_client, domain_id)
        logger.info('')
        logger.info('Teardown complete.')
        return

    # Step 2: Create fields
    logger.info('')
    logger.info('Step 2: Creating %d case fields...', len(FIELD_DEFINITIONS))
    field_map = create_fields(cases_client, domain_id)
    logger.info('Fields ready: %d', len(field_map))

    # Step 3: Create layout
    logger.info('')
    logger.info('Step 3: Creating layout...')
    layout_id = create_layout(cases_client, domain_id, field_map)

    # Step 4: Create template
    logger.info('')
    logger.info('Step 4: Creating template...')
    template_id = create_template(cases_client, domain_id, field_map, layout_id)

    # Summary
    logger.info('')
    logger.info('=' * 60)
    logger.info('Setup complete!')
    logger.info('=' * 60)
    logger.info('Domain:     %s', domain_id)
    logger.info('Fields:     %d created/verified', len(field_map))
    logger.info('Layout:     %s (%s)', LAYOUT_NAME, layout_id)
    logger.info('Template:   %s (%s)', TEMPLATE_NAME, template_id)
    logger.info('Required:   %s', ', '.join(REQUIRED_FIELD_NAMES))
    logger.info('')
    logger.info('The template is now available in the Amazon Connect Cases console.')


if __name__ == '__main__':
    main()
