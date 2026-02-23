# Stability360 AI Agent (Aria) — Customer Journey Manual Test Plan

**Version:** 2.0 (Post consent/intake fix)
**Date:** 2026-02-22
**Environment:** Dev (us-west-2) / Prod (us-east-1)
**Agent:** Aria — Stability360 by Trident United Way
**Tools:** scoringCalculate, resourceLookup, Retrieve (KB), Escalate, Complete

---

## How to Use This Document

1. Open the Amazon Connect console → Q in Connect → Test chat
2. For each journey, send the **Client** messages one at a time
3. Compare Aria's responses against the **Expected Aria Response** column
4. Check each **Validation Point** and mark Pass/Fail
5. Record any deviations in the **Notes** column

### Key Abbreviations

| Abbrev | Meaning |
|--------|---------|
| [R] | Referral path (condensed intake) |
| [D] | Direct Support path (full intake + scoring) |
| ZIP ✓ | ZIP is in the tri-county service area |
| ZIP ✗ | ZIP is outside the service area |

---

## Journey 1: Referral — Food Assistance (Unemployed)

**Path:** Referral [R]
**Category:** Food → Food Pantries
**Consent:** Required
**Expected Tools:** resourceLookup (after intake)

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | "Hi there! I'm Aria with Stability360 by Trident United Way. How can I help you today?" |
| 2 | Client | I need help finding food | |
| 3 | Aria | *(confirm need)* | Confirms food need: "It sounds like you need help with food — is that right?" |
| 4 | Client | Yes | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT:** "To help connect you with the right resources, I'll need to ask some personal questions..." |
| 6 | Client | Yes that's fine | |
| 7 | Aria | *(Q1)* | "What ZIP code do you live in?" |
| 8 | Client | 29407 | |
| 9 | Aria | *(Q2)* | "How would you like to be contacted — by phone call, text, or email?" |
| 10 | Client | Text | |
| 11 | Aria | *(Q3)* | "What's the best phone number to reach you?" |
| 12 | Client | 843-555-1234 | |
| 13 | Aria | *(Q4)* | "Are you currently employed?" |
| 14 | Client | No | |
| 15 | Aria | *(resource search)* | Status message + calls resourceLookup. Q5 (employer) SKIPPED since unemployed. |
| 16 | Aria | *(results)* | Shares 2-3 food providers (name, city, phone, services, website) |
| 17 | Aria | *(follow-up)* | "Would you also like one of our team members to follow up with you?" |
| 18 | Client | No, this is great. Thank you! | |
| 19 | Aria | *(close)* | Warm closing. Calls Complete. |

### Validation Checklist — Journey 1

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Aria confirms food need before anything else | | |
| 2 | Consent asked BEFORE any data collection | | |
| 3 | Consent asked BEFORE ZIP code question | | |
| 4 | All 4 intake questions asked one at a time (Q1-Q4) | | |
| 5 | Q5 (employer) skipped because client is unemployed | | |
| 6 | resourceLookup called ONLY after all intake questions | | |
| 7 | Did NOT jump straight to resourceLookup after "I need help finding food" | | |
| 8 | Resources formatted correctly (name, city, phone, services) | | |
| 9 | Follow-up offered | | |
| 10 | Conversation ended with Complete | | |

**Session Attributes Expected:**
- needCategory = Food
- needSubcategory = Food Pantries
- path = referral
- zipCode = 29407
- county = Charleston
- contactMethod = text
- phoneNumber = 843-555-1234
- employmentStatus = unemployed

---

## Journey 2: Referral — Food Assistance (Employed, Partner Employer)

**Path:** Referral [R]
**Category:** Food
**Consent:** Required
**Expected Tools:** Retrieve (silent partner check), resourceLookup

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help with food | |
| 3 | Aria | *(confirm)* | Confirms food need |
| 4 | Client | Yes | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT** |
| 6 | Client | Sure | |
| 7 | Aria | *(Q1)* | ZIP code question |
| 8 | Client | 29466 | |
| 9 | Aria | *(Q2)* | Contact method question |
| 10 | Client | Phone call | |
| 11 | Aria | *(Q3)* | Phone number question |
| 12 | Client | 843-555-9876 | |
| 13 | Aria | *(Q4)* | Employment question |
| 14 | Client | Yes, part time | |
| 15 | Aria | *(Q5)* | **"Who is your current employer?"** (asked because employed) |
| 16 | Client | Bosch | |
| 17 | Aria | *(resource search)* | **SILENTLY** checks KB for Bosch (no status message for KB check). Then calls resourceLookup with status message. |
| 18 | Aria | *(results)* | Shares food providers |
| 19 | Aria | *(follow-up)* | "Would you also like one of our team members to follow up with you?" |
| 20 | Client | Yes please | |
| 21 | Aria | *(callback)* | "I'll make sure someone from our team **gives you a call**." (matches phone choice) |

### Validation Checklist — Journey 2

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Q5 (employer) asked because client is employed | | |
| 2 | Retrieve (KB) called SILENTLY — no "Let me check on that" | | |
| 3 | Thrive@Work NOT mentioned to client | | |
| 4 | Partner status NOT disclosed | | |
| 5 | Resources shared after all intake questions | | |
| 6 | Follow-up uses correct contact method ("gives you a call") | | |
| 7 | escalationRoute = callback | | |

**Session Attributes Expected (if Bosch is a partner):**
- partnerEmployee = true
- partnerEmployer = Bosch
- contactMethod = phone
- escalationRoute = callback

---

## Journey 3: Referral — Vague Request → Menu → Housing → Rent

**Path:** Referral [R]
**Category:** Housing → Rental Assistance
**Consent:** Required
**Expected Tools:** resourceLookup

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help | |
| 3 | Aria | *(menu)* | **Presents numbered category menu** (1. Housing, 2. Transportation, ... 11. Something else) |
| 4 | Client | 1 | |
| 5 | Aria | *(subcategory)* | "Could you tell me a bit more about your housing need? For example, are you looking for help with rent, shelter, eviction prevention, housing repairs, or utilities?" |
| 6 | Client | Rent | |
| 7 | Aria | *(consent)* | **MUST ASK CONSENT** (Rental Assistance is [R] path) |
| 8 | Client | Yes | |
| 9 | Aria | *(Q1)* | ZIP code |
| 10 | Client | 29401 | |
| 11 | Aria | *(Q2)* | Contact method |
| 12 | Client | Email | |
| 13 | Aria | *(Q3)* | Email address |
| 14 | Client | test@example.com | |
| 15 | Aria | *(Q4)* | Employment |
| 16 | Client | No | |
| 17 | Aria | *(resource search)* | Calls resourceLookup for rental assistance in Charleston |
| 18 | Aria | *(results)* | Shares rental assistance providers |
| 19 | Aria | *(follow-up)* | Offers team member follow-up |
| 20 | Client | No thanks | |
| 21 | Aria | *(close)* | Warm closing. Complete. |

### Validation Checklist — Journey 3

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Menu presented for vague "I need help" | | |
| 2 | Menu NOT presented upfront in greeting | | |
| 3 | Subcategory follow-up asked for Housing | | |
| 4 | Consent asked AFTER classification, BEFORE data collection | | |
| 5 | Condensed intake (not full Direct Support intake) | | |
| 6 | Resources shared after intake | | |

---

## Journey 4: Direct Support — Utilities (Non-Urgent)

**Path:** Direct Support [D] (ONLY [D] subcategory in Phase 0)
**Category:** Housing → Utilities
**Consent:** Required
**Expected Tools:** Retrieve (silent), scoringCalculate, then Escalate or resourceLookup

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help with my utility bills | |
| 3 | Aria | *(confirm)* | "It sounds like you need help with utilities — is that right?" |
| 4 | Client | Yes | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT** |
| 6 | Client | Yes, that's okay | |
| 7 | Aria | *(Q-FIRSTNAME)* | "Could you tell me your first name?" |
| 8 | Client | Maria | |
| 9 | Aria | *(Q-LASTNAME)* | "And your last name?" |
| 10 | Client | Gonzalez | |
| 11 | Aria | *(Q-ZIP)* | "What ZIP code do you live in?" |
| 12 | Client | 29414 | |
| 13 | Aria | *(Q-CONTACT)* | "How would you like to be contacted — by phone call, text, or email?" |
| 14 | Client | Email | |
| 15 | Aria | *(Q-EMAIL)* | "What's your email address?" |
| 16 | Client | maria.g@email.com | |
| 17 | Aria | *(Q-DAYS)* | "What days work best for you to be contacted?" |
| 18 | Client | Weekdays | |
| 19 | Aria | *(Q-TIMES)* | "What time of day works best?" |
| 20 | Client | Morning | |
| 21 | Aria | *(Q-AGE)* | "How old are you?" |
| 22 | Client | 34 | |
| 23 | Aria | *(Q-CHILDREN)* | "Do you have any children under 18 living at home?" |
| 24 | Client | Yes, two kids | |
| 25 | Aria | *(Q-EMPLOYMENT)* | "What is your current employment status?" |
| 26 | Client | Employed full time | |
| 27 | Aria | *(Q-EMPLOYER)* | "Who is your current employer?" |
| 28 | Client | Boeing | |
| 29 | Aria | *(Q-MILITARY)* | **SILENTLY checks KB for Boeing** then asks: "Do you have a military or service affiliation?" |
| 30 | Client | None | |
| 31 | Aria | *(Q-ASSISTANCE)* | "Do you or anyone in your household currently receive any public assistance?" |
| 32 | Client | We get SNAP | |
| 33 | Aria | *(Q-HOUSING)* | "Can you describe your current housing situation — are you renting, owning, staying with family?" |
| 34 | Client | Renting | |
| 35 | Aria | *(Q-INCOME)* | "What is your monthly household income?" |
| 36 | Client | $2,800 | |
| 37 | Aria | *(Q-HOUSINGCOST)* | "How much do you pay for housing each month?" |
| 38 | Client | $1,200 | |
| 39 | Aria | *(scoring)* | "Thank you for sharing all of that. Let me review your situation now." → calls **scoringCalculate** |
| 40 | Aria | *(offer)* | "Based on what you've shared, it sounds like you could really benefit from working directly with one of our team members. Would you like me to connect you with someone now?" |
| 41 | Client | Yes please | |
| 42 | Aria | *(escalate)* | Sets escalationRoute = live_agent → calls **Escalate** |

### Validation Checklist — Journey 4

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Consent asked BEFORE first name | | |
| 2 | Full intake collected (first, last, ZIP, contact, email, days, times) | | |
| 3 | Need-specific questions asked (age, children, employment, military, assistance) | | |
| 4 | Employer asked because employed | | |
| 5 | KB check for Boeing done SILENTLY | | |
| 6 | Thrive@Work NOT mentioned | | |
| 7 | Scoring questions asked (housing situation, income, housing cost) | | |
| 8 | scoringCalculate called (FIRST action tool call) | | |
| 9 | Escalation offered after scoring | | |
| 10 | Scores/path labels NOT shared with client | | |
| 11 | Questions asked ONE at a time (not grouped) | | |
| 12 | Eligibility flags noted: eligibleSiemer (children under 18) | | |

**Session Attributes Expected:**
- firstName = Maria, lastName = Gonzalez
- zipCode = 29414, county = Charleston/Dorchester
- contactMethod = email, emailAddress = maria.g@email.com
- preferredDays = Weekdays, preferredTimes = Morning
- age = 34, hasChildrenUnder18 = true
- employmentStatus = full_time, employer = Boeing
- militaryAffiliation = none, publicAssistance = SNAP
- needCategory = Housing, needSubcategory = Utilities, path = direct_support
- housingSituation = renting_stable/renting_month_to_month
- monthlyIncome = 2800, monthlyHousingCost = 1200
- compositeScore, recommendedPath, priorityFlag (from scoring)
- escalationRoute = live_agent
- eligibleSiemer = true
- partnerEmployee / partnerEmployer (if Boeing is a partner)

---

## Journey 5: Direct Support — Imminent Shutoff (Priority Escalation)

**Path:** Direct Support [D] with PRIORITY flag
**Category:** Housing → Utilities
**Consent:** Required
**Expected Tools:** Escalate (scoring SKIPPED)

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | My power is getting cut off tomorrow, I need help | |
| 3 | Aria | *(consent or urgent ack)* | Should ask consent OR acknowledge urgency and offer immediate connection |
| 4 | Client | Yes | |
| 5 | Aria | *(connect)* | **During hours:** "I understand this is urgent. Let me connect you with someone on our team right away..." |
| 5alt | Aria | *(callback)* | **After hours:** "Our team is available Monday through Friday, 8:30 AM to 8:30 PM..." Sets callback. |
| 6 | Client | Yes | |
| 7 | Aria | *(escalate)* | Calls **Escalate** (during hours) or **Complete** with callback (after hours) |

### Validation Checklist — Journey 5

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Urgency recognized ("cut off tomorrow") | | |
| 2 | Scoring SKIPPED entirely | | |
| 3 | No scoring questions asked (housing situation, income, etc.) | | |
| 4 | priorityFlag = urgent | | |
| 5 | During hours → immediate escalation offered | | |
| 6 | After hours → callback scheduled with hours info | | |
| 7 | needSubcategory = Utilities | | |

---

## Journey 6: General Question — No Consent Needed

**Path:** None (general inquiry)
**Consent:** NOT required
**Expected Tools:** resourceLookup (direct)

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | What food banks are in Charleston? | |
| 3 | Aria | *(search + results)* | "Let me search for food banks in Charleston." → calls **resourceLookup** directly. Shares 2-3 providers. |
| 4 | Aria | *(offer more)* | "Is there anything else I can help you with?" |
| 5 | Client | No, thank you | |
| 6 | Aria | *(close)* | Warm closing. Complete. |

### Validation Checklist — Journey 6

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | **NO consent asked** (this is a general question) | | |
| 2 | **NO intake questions** (no ZIP, contact, employment) | | |
| 3 | resourceLookup called directly on first response | | |
| 4 | Resources formatted correctly | | |
| 5 | Compare to Journey 1: "I need help finding food" MUST trigger consent | | |

> **CRITICAL DISTINCTION:**
> - Journey 6: "What food banks are in Charleston?" → General question → No consent → Direct search
> - Journey 1: "I need help finding food" → Person seeking help → Consent → Intake → Then search

---

## Journey 7: Out-of-Area Client

**Path:** Referral [R] (stops at ZIP check)
**Consent:** Required (asked before ZIP)
**Expected Tools:** None (directed to 211)

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help with rent | |
| 3 | Aria | *(confirm)* | Confirms rental assistance need |
| 4 | Client | Yes | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT** |
| 6 | Client | Yes | |
| 7 | Aria | *(Q1)* | "What ZIP code do you live in?" |
| 8 | Client | 29201 | |
| 9 | Aria | *(out of area)* | "I appreciate you reaching out! Stability360 currently serves the Berkeley, Charleston, and Dorchester county area... I'd recommend reaching out to SC 211 — you can dial 2-1-1 or visit sc211.org..." |

### Validation Checklist — Journey 7

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Consent asked before ZIP | | |
| 2 | 29201 recognized as outside service area | | |
| 3 | Directed to 211 (dial 2-1-1 or sc211.org) | | |
| 4 | Tri-county area mentioned (Berkeley, Charleston, Dorchester) | | |
| 5 | Intake STOPS — no further questions after ZIP rejection | | |
| 6 | resourceLookup NOT called | | |

---

## Journey 8: Consent Declined

**Path:** Referral [R] (falls back to general)
**Consent:** Declined
**Expected Tools:** resourceLookup (general only)

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help with transportation | |
| 3 | Aria | *(confirm)* | Confirms transportation need |
| 4 | Client | Yes | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT** |
| 6 | Client | I'd rather not share personal info | |
| 7 | Aria | *(respect decline)* | "No problem at all. I can still share general information about programs and resources in your area without collecting any personal details." |
| 8 | Aria | *(ask location)* | Asks for area/county for general search |
| 9 | Client | Charleston | |
| 10 | Aria | *(results)* | Calls resourceLookup for transportation in Charleston. Shares providers. |

### Validation Checklist — Journey 8

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Consent was asked | | |
| 2 | Decline acknowledged gracefully | | |
| 3 | NO intake questions after decline (no name, employment, etc.) | | |
| 4 | General resources still offered | | |
| 5 | resourceLookup called with just location (no personal data) | | |

---

## Journey 9: Hybrid — Food [R] + Utilities [D]

**Path:** Hybrid (Direct Support drives the intake)
**Category:** Food [R] + Housing → Utilities [D]
**Consent:** Required
**Expected Tools:** scoringCalculate, resourceLookup, Escalate

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help with food and my electric bill | |
| 3 | Aria | *(confirm)* | Acknowledges both needs: food and utilities |
| 4 | Client | Yes | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT** |
| 6 | Client | Yes | |
| 7-20 | | *(Full Direct Support intake)* | First name, last name, ZIP, contact, phone/email, days, times, age, children, employment, employer, military, assistance |
| 21-24 | | *(Scoring data)* | Housing situation, income, housing cost |
| 25 | Aria | *(scoring)* | Calls **scoringCalculate** |
| 26 | Aria | *(food resources)* | Calls **resourceLookup** for food assistance |
| 27 | Aria | *(results + offer)* | Shares food providers + offers to connect for utility help |
| 28 | Client | Yes | |
| 29 | Aria | *(escalate)* | Calls **Escalate** |

### Validation Checklist — Journey 9

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Both needs acknowledged (food + utilities) | | |
| 2 | Full Direct Support intake (not condensed) — [D] drives the path | | |
| 3 | Scoring collected and scoringCalculate called | | |
| 4 | resourceLookup called for food (the [R] need) | | |
| 5 | Escalation offered for utilities (the [D] need) | | |
| 6 | One tool call per turn | | |

---

## Journey 10: Info Question — "What is Stability360?"

**Path:** None (answered from prompt)
**Consent:** NOT required
**Expected Tools:** None

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | What is Stability360? | |
| 3 | Aria | *(info)* | Describes Stability360: program by Trident United Way, helps people in tri-county area access community resources, etc. |

### Validation Checklist — Journey 10

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Answered from prompt knowledge (no tool called) | | |
| 2 | No consent asked | | |
| 3 | No intake questions | | |
| 4 | Mentions Trident United Way | | |
| 5 | Mentions community resources / support | | |

---

## Journey 11: Human Escalation — Client Requests a Person

**Path:** Escalation (Tier 3)
**Consent:** NOT required
**Expected Tools:** Escalate

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I want to talk to a real person | |
| 3 | Aria | *(offer help first)* | "Of course! Before I connect you, is there something specific I can help you with? I might be able to answer your question right away." |
| 4 | Client | No, I just want a person | |
| 5a | Aria | *(during hours)* | "Absolutely, let me connect you with a team member now." → Escalate |
| 5b | Aria | *(after hours)* | "Our team is available Monday through Friday, 8:30 AM to 8:30 PM, and Saturdays 9:00 AM to noon, Eastern Time. Can I take your phone number so someone can call you during business hours?" |

### Validation Checklist — Journey 11

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Tier 3: Offered KB answer first | | |
| 2 | Respected client's choice after decline | | |
| 3 | During hours → live escalation | | |
| 4 | After hours → callback with hours info | | |

---

## Journey 12: Thrive@Work Mention — Redirected

**Path:** Referral [R] (after redirect)
**Consent:** Required (for subsequent intake)
**Expected Tools:** Retrieve (silent), resourceLookup

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I heard my employer has a program through Thrive@Work? | |
| 3 | Aria | *(redirect)* | **"I can help you find community resources in your area. What kind of help are you looking for?"** — Does NOT discuss Thrive@Work |
| 4 | Client | I need help with childcare | |
| 5 | Aria | *(consent)* | **MUST ASK CONSENT** |
| 6 | Client | Sure | |
| 7-13 | | *(Condensed intake)* | ZIP, contact method, phone/email, employment, employer |
| 14 | Aria | *(results)* | resourceLookup for childcare. Shares providers. |

### Validation Checklist — Journey 12

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | Thrive@Work details NOT shared | | |
| 2 | No mention of "partner", "employer program", or "employer benefit" | | |
| 3 | Redirected to general resource help | | |
| 4 | Normal intake flow proceeded for childcare | | |
| 5 | Silent KB check during employer question (if employed) | | |

---

## Journey 13: Consent/Intake Distinction — THE CRITICAL FIX

> This is the most important test. It validates the core behavioral fix.
> Run **two separate conversations** back-to-back.

### Conversation A: General Question

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | What food banks are in Charleston? | |
| 3 | Aria | *(direct search)* | **Immediately** calls resourceLookup. Shares food bank providers. **No consent. No intake.** |

### Conversation B: Person Seeking Help

| Turn | Speaker | Message | Expected Aria Response |
|------|---------|---------|----------------------|
| 1 | Aria | *(greeting)* | Standard greeting |
| 2 | Client | I need help finding food | |
| 3 | Aria | *(confirm + consent)* | Confirms need, then asks consent. **Does NOT call resourceLookup yet.** |

### Validation Checklist — Journey 13

| # | Check | Pass/Fail | Notes |
|---|-------|-----------|-------|
| 1 | **A:** "What food banks are in Charleston?" → direct search, no consent | | |
| 2 | **A:** Resources returned immediately | | |
| 3 | **B:** "I need help finding food" → consent asked | | |
| 4 | **B:** resourceLookup NOT called on first response | | |
| 5 | **B:** Intake questions follow consent | | |
| 6 | **A and B produce DIFFERENT behaviors** | | |

---

## Quick Reference Matrix

| # | Journey | Path | Consent? | Intake | First Tool | Key Validation |
|---|---------|------|----------|--------|------------|----------------|
| 1 | Food (unemployed) | Referral [R] | Yes | Condensed (4 Qs) | resourceLookup | Consent before intake |
| 2 | Food (employed, partner) | Referral [R] | Yes | Condensed (5 Qs) | Retrieve (silent) → resourceLookup | Silent KB check, no Thrive@Work |
| 3 | Vague → Menu → Rent | Referral [R] | Yes | Condensed | resourceLookup | Menu for vague, subcategory follow-up |
| 4 | Utilities (non-urgent) | Direct Support [D] | Yes | Full + Scoring | scoringCalculate → Escalate | Full intake, scoring, one Q at a time |
| 5 | Utilities (shutoff) | Direct Support [D] | Yes | Minimal | Escalate | Skip scoring, priority flag |
| 6 | "Food banks in Charleston?" | General | **No** | **None** | resourceLookup | No consent, direct search |
| 7 | Out-of-area ZIP | Referral [R] | Yes | Stops at ZIP | None | 211 referral, intake stops |
| 8 | Consent declined | Referral [R] | Declined | None | resourceLookup (general) | Graceful decline, general help |
| 9 | Food + Utilities (hybrid) | Hybrid [R+D] | Yes | Full + Scoring | scoringCalculate → resourceLookup → Escalate | Both needs addressed |
| 10 | "What is Stability360?" | Info | **No** | **None** | None | Prompt knowledge only |
| 11 | "Talk to a person" | Escalation | **No** | **None** | Escalate | Tier 3, offer KB first |
| 12 | Thrive@Work mention | Referral [R] | Yes | Condensed | Retrieve (silent) → resourceLookup | Redirect, no Thrive@Work |
| 13 | Distinction test | Both | A: No / B: Yes | A: None / B: Condensed | A: resourceLookup / B: (after intake) | **Core fix validation** |

---

## Test Execution Log

| Date | Tester | Environment | Journey | Result | Notes |
|------|--------|-------------|---------|--------|-------|
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
| | | | | | |
