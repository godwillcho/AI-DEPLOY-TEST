# Stability360 — Session Attributes Reference

All session attributes that can be created by the Aria AI agent during a conversation. These are stored as string key-value pairs on the Amazon Connect contact and used by the contact flow for case creation, profile management, routing, and follow-up scheduling.

---

## Core Attributes (from intake)

| # | Attribute | Type | Description | Example Values | Path |
|---|-----------|------|-------------|----------------|------|
| 1 | `firstName` | string | Client's first name | `Maria` | Direct Support |
| 2 | `lastName` | string | Client's last name | `Johnson` | Direct Support |
| 3 | `zipCode` | string | Client's ZIP code | `29401` | Both |
| 4 | `county` | string | County derived from ZIP or asked directly | `Charleston`, `Berkeley`, `Dorchester` | Both |
| 5 | `contactMethod` | string | Preferred contact method | `phone_call`, `text`, `email` | Both |
| 6 | `phoneNumber` | string | Phone in E.164 format (no dashes, no spaces) | `+18435551234` | Both (if call or text) |
| 7 | `emailAddress` | string | Client's email address | `maria@example.com` | Both (if email) |
| 8 | `preferredDays` | string | Days available for follow-up contact | `Monday through Wednesday`, `Weekdays` | Direct Support |
| 9 | `preferredTimes` | string | Time of day preference for contact | `Mornings`, `Afternoons`, `Evenings` | Direct Support |

---

## Need Attributes

| # | Attribute | Type | Description | Example Values | Path |
|---|-----------|------|-------------|----------------|------|
| 10 | `needCategory` | string | Primary need category (1 of 11) | `Housing`, `Food`, `Transportation`, `Health`, `Child Care`, `Disaster`, `Employment & Education`, `Legal Aid`, `Financial Literacy`, `Hygiene` | Both |
| 11 | `needSubcategory` | string | Specific subcategory within the category | `Utilities`, `Food Pantries`, `Rental Assistance`, `Shelter`, `Bus Tickets` | Both |
| 12 | `path` | string | Intake path determined by the subcategory | `referral`, `direct_support` | Both |

---

## Need-Specific Attributes

Only collected if the client's need category requires it. See the matrix below.

| # | Attribute | Type | Description | Example Values |
|---|-----------|------|-------------|----------------|
| 13 | `age` | string | Client's age | `34`, `67` |
| 14 | `hasChildrenUnder18` | string | Whether client has children under 18 at home | `true`, `false` |
| 15 | `employmentStatus` | string | Current employment status | `full_time`, `part_time`, `self_employed`, `unemployed`, `looking_for_work`, `retired`, `student`, `unable_to_work`, `gig_work`, `seasonal` |
| 16 | `employer` | string | Employer name (only if employed) | `Walmart`, `Boeing`, `MUSC` |
| 17 | `militaryAffiliation` | string | Military or service affiliation | `veteran`, `active_duty`, `reserve_national_guard`, `first_responder`, `none`, `prefer_not_to_answer` |
| 18 | `publicAssistance` | string | Public benefits the household receives | `SNAP`, `SNAP, Medicaid`, `WIC, TANF`, `SSI`, `SSDI`, `none` |

### Need-to-Question Matrix (which attributes are collected per need)

| Need Category | age | hasChildrenUnder18 | employmentStatus | employer | militaryAffiliation | publicAssistance |
|---------------|-----|--------------------|------------------|----------|---------------------|------------------|
| Housing / Utilities | Yes | Yes | Yes | Yes | Yes | Yes |
| Transportation | - | - | Yes | Yes | - | Yes |
| Food | - | Yes | Yes | Yes | - | Yes |
| Health | Yes | - | Yes | Yes | Yes | Yes |
| Child Care | - | Yes | Yes | Yes | - | Yes |
| Disaster | - | - | Yes | Yes | - | Yes |
| Employment & Education | - | - | Yes | Yes | Yes | - |
| Legal Aid | Yes | - | - | - | Yes | - |
| Financial Literacy | - | Yes | Yes | Yes | - | Yes |
| Hygiene | - | - | - | - | - | - |

---

## Scoring Inputs (Direct Support path only)

Collected after the full intake, before calling the `scoringCalculate` tool.

| # | Attribute | Type | Description | Example Values |
|---|-----------|------|-------------|----------------|
| 19 | `housingSituation` | string | Current housing situation | `homeless`, `shelter`, `couch_surfing`, `temporary`, `transitional`, `renting_unstable`, `renting_month_to_month`, `renting_stable`, `owner_with_mortgage`, `owner`, `owner_no_mortgage` |
| 20 | `monthlyIncome` | string | Monthly household income in dollars | `1800`, `3200`, `0` |
| 21 | `monthlyHousingCost` | string | Monthly rent or mortgage payment in dollars | `950`, `1200`, `0` |
| 22 | `monthlyExpenses` | string | Total monthly expenses in dollars | `1600`, `2500` |
| 23 | `savingsRate` | string | Savings rate as decimal | `0`, `0.03`, `0.10` |
| 24 | `ficoRange` | string | Credit score range | `below_580`, `580-669`, `670-739`, `740-799`, `800+`, `unknown` |
| 25 | `hasBenefits` | string | Whether employer provides benefits | `true`, `false` |

---

## Scoring Results (from scoringCalculate response)

Set automatically after the `scoringCalculate` tool returns.

| # | Attribute | Type | Description | Example Values |
|---|-----------|------|-------------|----------------|
| 26 | `housingScore` | string | Housing stability score (1-5) | `1`, `3`, `5` |
| 27 | `employmentScore` | string | Employment stability score (1-5) | `1`, `3`, `5` |
| 28 | `financialResilienceScore` | string | Financial resilience score (1-5) | `1`, `3`, `5` |
| 29 | `compositeScore` | string | Average of the 3 domain scores | `1.67`, `3.0`, `4.33` |
| 30 | `priorityFlag` | string | Whether the case is urgent priority | `true`, `false` |
| 31 | `recommendedPath` | string | Scoring-based path recommendation | `direct_support`, `mixed`, `referral` |

### Scoring Logic Summary

- **Any domain score = 1** OR housing priority trigger → `priorityFlag = true`
- **Composite < 2.5** OR priority → `recommended_path = direct_support`
- **Composite 2.5–3.5** → `recommended_path = mixed`
- **Composite > 3.5** → `recommended_path = referral`

---

## Partner Attributes

Set silently when the client's employer matches a Thrive@Work partner in the knowledge base.

| # | Attribute | Type | Description | Example Values |
|---|-----------|------|-------------|----------------|
| 32 | `partnerEmployee` | string | Whether client works for a partner employer | `true` |
| 33 | `partnerEmployer` | string | Name of the partner employer | `Boeing`, `Bosch` |

---

## Eligibility Flags

Noted during intake based on the client's answers. Used for downstream program matching.

| # | Attribute | Type | Description | Trigger |
|---|-----------|------|-------------|---------|
| 34 | `eligibleBCDCOG` | string | Eligible for BCDCOG aging services | Age 65+ |
| 35 | `eligibleSiemer` | string | Eligible for Siemer / Rental Reserve | Children under 18 at home |
| 36 | `eligibleMissionUnited` | string | Eligible for Mission United / veteran services | Veteran, active duty, or reserve |
| 37 | `eligibleBarriersToEmployment` | string | Eligible for Barriers to Employment program | Client is looking for work |
| 38 | `employmentServicesNeeded` | string | Flag that employment services are needed | Client is unemployed |

---

## Routing Attributes

Determine what happens after the AI conversation ends.

| # | Attribute | Type | Description | Example Values |
|---|-----------|------|-------------|----------------|
| 39 | `escalationRoute` | string | How the contact should be routed | `live_agent` (transfer now during business hours), `callback` (team member follows up later) |

---

## Total: 39 Possible Session Attributes

### By Path

| Path | Attributes Set |
|------|---------------|
| **General question** (no consent) | None — no session attributes stored |
| **Referral [R]** | #3–7, #10–12, #15–16 (5–10 attributes) |
| **Direct Support [D]** | #1–31, plus any eligibility/routing flags (up to 39 attributes) |
| **Priority escalation** (imminent shutoff) | #10–12, #39, `priorityFlag = urgent` (minimal set) |

### By Lifecycle Stage

| Stage | Attributes |
|-------|-----------|
| Need identification | `needCategory`, `needSubcategory`, `path` |
| Consent + intake | `firstName`, `lastName`, `zipCode`, `county`, `contactMethod`, `phoneNumber`/`emailAddress`, `preferredDays`, `preferredTimes` |
| Need-specific questions | `age`, `hasChildrenUnder18`, `employmentStatus`, `employer`, `militaryAffiliation`, `publicAssistance` |
| Partner check | `partnerEmployee`, `partnerEmployer` |
| Eligibility flags | `eligibleBCDCOG`, `eligibleSiemer`, `eligibleMissionUnited`, `eligibleBarriersToEmployment`, `employmentServicesNeeded` |
| Scoring | `housingSituation`, `monthlyIncome`, `monthlyHousingCost`, `monthlyExpenses`, `savingsRate`, `ficoRange`, `hasBenefits` |
| Scoring results | `housingScore`, `employmentScore`, `financialResilienceScore`, `compositeScore`, `priorityFlag`, `recommendedPath` |
| Routing | `escalationRoute` |
