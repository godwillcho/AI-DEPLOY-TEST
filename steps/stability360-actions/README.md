# Stability360 Actions

AI-powered support agent (Aria) for Trident United Way, built on Amazon Connect Q with MCP Gateway tools.

## Session Attributes Reference

All attributes are stored as string key-value pairs on the Amazon Connect contact. The contact flow uses these for case creation, profile management, routing, and follow-up scheduling after the AI conversation ends.

### Core Attributes (from intake)

| Attribute | Description | Example | Collected When |
|-----------|-------------|---------|----------------|
| `firstName` | Client's first name | `Maria` | Direct Support intake |
| `lastName` | Client's last name | `Johnson` | Direct Support intake |
| `zipCode` | Client's ZIP code | `29401` | Both paths |
| `county` | Derived from ZIP or asked directly | `Charleston` | Both paths |
| `contactMethod` | Preferred contact method | `phone_call`, `text`, `email` | Both paths |
| `phoneNumber` | Phone in E.164 format (no dashes) | `+18435551234` | If contact method is call or text |
| `emailAddress` | Client's email address | `maria@example.com` | If contact method is email |
| `preferredDays` | Days available for contact | `Monday through Wednesday` | Direct Support intake |
| `preferredTimes` | Time of day preference | `Mornings` | Direct Support intake |

### Need Attributes

| Attribute | Description | Example | Collected When |
|-----------|-------------|---------|----------------|
| `needCategory` | Primary need category (1 of 11) | `Housing` | Both paths |
| `needSubcategory` | Specific subcategory | `Utilities` | Both paths |
| `path` | Intake path determined by subcategory | `referral`, `direct_support` | Both paths |

### Need-Specific Attributes (only if relevant questions were asked)

| Attribute | Description | Example | Collected When |
|-----------|-------------|---------|----------------|
| `age` | Client's age | `34` | Housing, Health, Legal Aid |
| `hasChildrenUnder18` | Children under 18 at home | `true`, `false` | Housing, Food, Child Care, Financial Literacy |
| `employmentStatus` | Current employment status | `part_time`, `unemployed`, `full_time`, `retired`, etc. | Housing, Transportation, Food, Health, Child Care, Disaster, Employment/Education, Financial Literacy |
| `employer` | Employer name (if employed) | `Walmart` | If employed full-time or part-time |
| `militaryAffiliation` | Military or service affiliation | `veteran`, `active_duty`, `none` | Housing, Health, Employment/Education, Legal Aid |
| `publicAssistance` | Public benefits received | `SNAP, Medicaid` | Housing, Food, Health, Child Care, Transportation, Disaster, Financial Literacy |

### Scoring Inputs (Direct Support path only)

| Attribute | Description | Example | Collected When |
|-----------|-------------|---------|----------------|
| `housingSituation` | Current housing situation | `renting_month_to_month`, `homeless`, `owner`, etc. | Before calling scoringCalculate |
| `monthlyIncome` | Monthly household income | `1800` | Before calling scoringCalculate |
| `monthlyHousingCost` | Monthly rent/mortgage cost | `950` | Before calling scoringCalculate |
| `scoringEmploymentStatus` | Employment for scoring (if not already captured) | `part_time` | Before calling scoringCalculate (skipped if Q-EMPLOYMENT already answered) |

#### Valid `housingSituation` values

| Value | Base Score |
|-------|-----------|
| `homeless` | 1 |
| `shelter` | 1 |
| `couch_surfing` | 2 |
| `temporary` | 2 |
| `transitional` | 2 |
| `renting_unstable` | 3 |
| `renting_month_to_month` | 3 |
| `renting_stable` | 4 |
| `owner_with_mortgage` | 4 |
| `owner` / `owner_no_mortgage` | 5 |

#### Valid `employmentStatus` values

| Value | Base Score |
|-------|-----------|
| `unable_to_work` | 1 |
| `unemployed` | 1 |
| `gig_work` | 2 |
| `seasonal` | 2 |
| `part_time` | 3 |
| `full_time_below_standard` | 3 |
| `self_employed` | 3 |
| `student` | 3 |
| `retired` | 4 |
| `full_time` | 4 |
| `full_time_above_standard` | 5 |

### Scoring Results (Direct Support path only, from scoringCalculate response)

| Attribute | Description | Example |
|-----------|-------------|---------|
| `housingScore` | Housing stability score (1-5) | `1` |
| `employmentScore` | Employment stability score (1-5) | `2` |
| `financialResilienceScore` | Financial resilience score (1-5) | `2` |
| `compositeScore` | Average of 3 domain scores | `1.67` |
| `priorityFlag` | Urgent priority indicator | `true`, `false`, `urgent` |
| `recommendedPath` | Scoring-based path recommendation | `direct_support`, `mixed`, `referral` |

### Partner Attributes (only if employer is a Thrive@Work partner)

| Attribute | Description | Example |
|-----------|-------------|---------|
| `partnerEmployee` | Whether client works for a partner employer | `true` |
| `partnerEmployer` | Name of the partner employer | `Boeing` |

### Eligibility Flags (noted during intake based on answers)

| Attribute | Description | Trigger |
|-----------|-------------|---------|
| `eligibleBCDCOG` | Eligible for BCDCOG services | Age 65+ |
| `eligibleSiemer` | Eligible for Siemer / Rental Reserve | Children under 18 |
| `eligibleMissionUnited` | Eligible for Mission United / veteran services | Veteran or active duty |
| `eligibleBarriersToEmployment` | Eligible for Barriers to Employment program | Looking for work |

### Routing Attributes

| Attribute | Description | Values |
|-----------|-------------|--------|
| `escalationRoute` | How the contact should be routed after the AI conversation | `live_agent` (transfer now), `callback` (team member follows up later) |

## MCP Tools

| Tool | Endpoint | Description |
|------|----------|-------------|
| `scoringCalculate` | `POST /scoring/calculate` | Computes housing, employment, and financial resilience scores (1-5 each), composite score, priority flag, and recommended path |
| `resourceLookup` | `POST /resources/search` | Queries SC 211 (Sophia API) for community resources by keyword, county, city, or ZIP |

## Deployment

```bash
# Full deploy (dev)
python deploy.py --stack-name stability360-actions-dev --region us-west-2 \
  --environment dev --enable-mcp \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d

# Update Lambda code only
python deploy.py --update-code-only --stack-name stability360-actions-dev --region us-west-2

# Update orchestration prompt only
python deploy.py --update-prompt --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d \
  --stack-name stability360-actions-dev --region us-west-2

# Teardown
python deploy.py --teardown --stack-name stability360-actions-dev --region us-west-2
```
