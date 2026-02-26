# Stability360 Actions — Contact Attributes Reference

All contact attributes are saved automatically by the Lambda router middleware
when the AI agent includes `instance_id` and `contact_id` in a tool call.

---

## Core Intake Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `firstName` | Intake Q1 | Client first name |
| `lastName` | Intake Q2 | Client last name |
| `zipCode` | Intake Q3 | Client ZIP code |
| `county` | Derived from ZIP / Q-COUNTY | Client county (Berkeley, Charleston, or Dorchester) |
| `contactMethod` | Intake Q4 | Preferred contact method (phone, text, or email) |
| `phoneNumber` | Intake Q5 | Client phone number (E.164 format: +1XXXXXXXXXX) |
| `emailAddress` | Intake Q5 | Client email address |
| `preferredDays` | Intake Q-DAYS | Preferred days for contact (Direct Support only) |
| `preferredTimes` | Intake Q-TIMES | Preferred time of day for contact (Direct Support only) |

## Need Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `needCategory` | Need identification | Primary need category (Housing, Food, Health, etc.) |
| `needSubcategory` | Need identification | Specific subcategory (Utilities, Rental Assistance, etc.) |
| `path` | Need identification | Intake path: `referral` or `direct_support` |

## Need-Specific Attributes (collected only if relevant)

| Attribute | Source | Description |
|-----------|--------|-------------|
| `age` | Intake Q-AGE | Client age |
| `hasChildrenUnder18` | Intake Q-CHILDREN | Whether client has children under 18 at home |
| `employmentStatus` | Intake Q-EMPLOYMENT | Employment status (full_time, part_time, unemployed, etc.) |
| `employer` | Intake Q-EMPLOYER | Employer name |
| `militaryAffiliation` | Intake Q-MILITARY | Military affiliation (veteran, active_duty, reserve, none, etc.) |
| `publicAssistance` | Intake Q-ASSISTANCE | Public assistance received (SNAP, WIC, Medicaid, etc.) |

## Scoring Inputs (Direct Support path only)

| Attribute | Source | Description |
|-----------|--------|-------------|
| `housingSituation` | Intake Q-HOUSING | Housing situation category |
| `monthlyIncome` | Intake Q-INCOME | Gross monthly income in USD |
| `monthlyHousingCost` | Intake Q-HOUSINGCOST | Monthly housing cost (rent/mortgage) in USD |
| `monthlyExpenses` | Tool call (optional) | Total monthly expenses in USD |
| `savingsRate` | Tool call (optional) | Savings rate as decimal (0.03 = 3%) |
| `ficoRange` | Tool call (optional) | FICO credit score range |
| `hasBenefits` | Tool call (optional) | Whether client has employer-provided benefits |

## Scoring Results (from scoringCalculate response)

| Attribute | Source | Description |
|-----------|--------|-------------|
| `housingScore` | scoringCalculate | Housing stability score (1–5) |
| `employmentScore` | scoringCalculate | Employment stability score (1–5) |
| `financialResilienceScore` | scoringCalculate | Financial resilience score (1–5) |
| `compositeScore` | scoringCalculate | Average of all 3 domain scores |
| `priorityFlag` | scoringCalculate | `true` if any domain score is 1 or critical trigger present |
| `recommendedPath` | scoringCalculate | Recommended service path: `referral`, `mixed`, or `direct_support` |

## Partner Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `partnerEmployee` | KB lookup (silent) | `true` if employer is a Thrive@Work partner |
| `partnerEmployer` | KB lookup (silent) | Partner employer name |

## Routing Attributes

| Attribute | Source | Description |
|-----------|--------|-------------|
| `escalationRoute` | Post-scoring decision | `live_agent` (connected now) or `callback` (follow-up later) |

---

## Enum Values Reference

### `path`
- `referral` — Referral [R] path (light touch)
- `direct_support` — Direct Support [D] path (high touch)

### `recommendedPath` (from scoring)
- `referral` — Client can self-navigate with resources
- `mixed` — Some domains need support, others self-sufficient
- `direct_support` — Case manager involvement recommended

### `escalationRoute`
- `live_agent` — Client connected to a team member during business hours
- `callback` — Team member will follow up via client's preferred contact method

### `housingSituation`
- `homeless`, `shelter`, `couch_surfing`, `temporary`, `transitional`
- `renting_unstable`, `renting_month_to_month`, `renting_stable`
- `owner_with_mortgage`, `owner`, `owner_no_mortgage`

### `employmentStatus`
- `unable_to_work`, `unemployed`, `gig_work`, `seasonal`, `part_time`
- `full_time_below_standard`, `self_employed`, `student`, `retired`
- `full_time`, `full_time_above_standard`

### `contactMethod`
- `phone`, `text`, `email`

### `militaryAffiliation`
- `veteran`, `active_duty`, `reserve`, `first_responder`, `none`, `prefer_not_to_answer`

### `ficoRange`
- `below_580`, `580-669`, `670-739`, `740-799`, `800+`, `unknown`
