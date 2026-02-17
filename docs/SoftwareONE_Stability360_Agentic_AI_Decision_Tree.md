*Agentic AI discovery x Trident United Way*
*01212026*
*Companion documentation to Intake Logic Branching, AI Decision-Making for Direct Support, Closed-Loop Referral Process*

# SoftwareONE – Stability360 Agentic AI Decision Tree (Prototype)

This decision tree translates the attached intake logic, chatbot draft, client journey logic map, and Self-Sufficiency Matrix into explicit, build-ready decision logic for the prototype.

---

## 1. Entry Point & Session Initialization

**START**

1. Client initiates interaction via Web / Mobile / Kiosk
2. System creates or retrieves Client Session ID
3. Conversation context persistence enabled (for closed-loop referrals)

---

## 2. Identity & Consent Gate

**Node 1: Identity**

- VA asks for first name (optional)
- VA explains purpose and data use

**Decision:**

- If client continues → proceed
- If client declines → offer human escalation or exit

---

## 3. Primary Need Identification (Intent Routing)

**Node 2: "How can I help you today?" (Multi-Select)**

Categories (these have subcategories as the conversation progresses):

- Housing
- Transportation
- Food
- Health
- Child Care
- Disaster
- Employment & Education
- Legal Aid
- Financial Literacy
- Hygiene
- Other (free text)

**Decision:**

- If ≥1 category selected → proceed
- If "Other" only → collect free-text → proceed

---

## 4. Referral vs Direct Support Determination

**Node 3: Support Path Classification**

For each selected sub-category (the above categories break down into subs, for example: Housing breaks into direct support, rental assistance, shelter, homelessness, eviction prevention, housing repairs, utilities (see Intake Form Logic Branching):

**IF** service is informational / self-directed → **Referral Path (connect to 211 database AND/OR additional referral partner in the data lake)**

**IF** service requires case manager involvement, eligibility verification, or scheduling → **Direct Support Path**

*(Logic derived from Intake Form Logic Branching)*

---

## 5. Intake & Screening (Automation-First)

**Node 4: Core Intake Questions**

Collected for ALL paths:

- ZIP code → derive county (County derivative not always true – may need separate state/county designation)
- Preferred contact method
- Availability (days/times)
- Age
- Children under 18 (Y/N)
- Employment status
- Military/service affiliation
- Public assistance indicators

**Decision:**

- If required fields missing → prompt one at a time
- If client disengages → save partial + offer follow-up

---

## 6. Referral Path Logic (Low-Touch)

**Node 5A: Referral Path**

1. Match client needs + geo location + eligibility rules
2. Generate referral list
3. Deliver referral information to client
4. Create referral record in system (that then creates an automated follow-up, did you receive assistance, additional assistance needed? Etc.)

**Decision:**

- If client requests more help → escalate to Direct Support
- Else → schedule automated follow-up (see above)

---

## 7. Direct Support Path Logic (High-Touch)

**Node 5B: Direct Support Path**

1. Trigger extended intake
2. Human escalation if "live agent" available, Schedule appointment with case manager if not available
3. Create Direct Support record
4. Pass full context to human

**Decision:**

- If scheduling fails → human escalation if "live agent" available if not *<need to revisit this point>*
- Else → confirmation + follow-up

---

## 8. Self-Sufficiency Matrix (Human-Facilitated)

**Node 6: Matrix Assessment (Post-Handoff)**

- Conducted by live agent
- Uses screening questions to score:
  - Housing
  - Employment
  - Financial Resilience

**Decision:**

- Score determines:
  - Service intensity
  - Follow-up cadence
  - Goal prioritization

*(Matrix used for tracking progress, not gatekeeping)*

---

## 9. Closed-Loop Referral & Follow-Up

**Decision:**

- If need resolved → close loop
- If unresolved → re-route or escalate

---

## 10. Escalation to Human (Global Rules)

**Escalation Triggers:**

- Ambiguous eligibility
- Sensitive disclosures
- Conflicting answers
- Client requests human
- System/tool failure
- Request for Direct Support

**Action:**

- Package conversation context
- Route to appropriate human queue

---

## 11. Error & Failure Handling

**Node 8: Failure State**

- Acknowledge issue
- Offer retry or alternate path
- Escalate if unresolved

---

## 12. Data Persistence & Governance

- All interactions saved to Data Lake
- Records synced with CRM (CharityTracker)
- Data used for:
  - Closed-loop referrals
  - Trend analysis
  - Reporting

---

## 13. End States

**Possible End States:**

- Referral delivered
- Direct Support scheduled
- Human escalation completed
- Client disengaged (with follow-up scheduled)

---

## 14. What Should Be Included in the Prototype

- Stateful decision engine
- Rule-based branching logic
- Tool calling orchestration
- Conversation persistence
- Referral vs Direct Support logic
- Escalation packaging
- Metrics capture

---

## 15. Explicit Non-Goals

- No final eligibility determinations
- No payments
- No voice
- No marketing personalization
