# Stability360 — Architecture, Customer Journey & Scoring Logic

---

## System Overview

Stability360 is an AI-powered community resource platform built on Amazon Connect.
It helps people access social services, assess their needs, and connect with case
managers — all through a chat interface. The system has two AI agents, an intake
bot for routing, and a knowledge base of community resources.

```
                         ┌─────────────────────┐
                         │   Amazon Connect     │
                         │   Chat Widget        │
                         └────────┬────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │       Contact Flow           │
                    │  "Get customer input"         │
                    │   (Intake Bot - Lex V2)       │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                                 │
              ▼                                 ▼
   selectedRoute =                   selectedRoute =
   "CommunityResources"             "ThriveAtWork"
              │                                 │
              ▼                                 ▼
┌──────────────────────┐          ┌──────────────────────┐
│  Stability360 Actions│          │    Thrive@Work       │
│  AI Agent (Aria)     │          │    AI Agent (Aria)    │
│                      │          │                      │
│  6 MCP Tools         │          │  1 MCP Tool          │
│  + KB Retrieve       │          │  + KB Retrieve       │
└──────────┬───────────┘          └──────────┬───────────┘
           │                                 │
     ┌─────┼─────┐                           │
     ▼     ▼     ▼                           ▼
  Lambda  SES  Connect               Lambda (DynamoDB)
(DynamoDB)     Cases                 Employee Lookup
```

---

## Customer Journey

### Journey 1: Community Resources Path

```
Customer opens chat
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ INTAKE BOT                                                         │
│                                                                     │
│ Shows ListPicker menu:                                              │
│   ┌──────────────────────┐  ┌──────────────────────┐               │
│   │ Community Resources  │  │    Thrive@Work       │               │
│   │ 211 resources,       │  │ Employee assistance  │               │
│   │ housing, utilities,  │  │ and employer benefits│               │
│   │ food, and more       │  │                      │               │
│   └──────────┬───────────┘  └──────────────────────┘               │
│              │                                                      │
│    Customer clicks                                                  │
│    "Community Resources"                                            │
│              │                                                      │
│    Lambda sets selectedRoute = "CommunityResources"                 │
│    Session closes                                                   │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ CONTACT FLOW                                                        │
│                                                                     │
│ Check contact attributes → selectedRoute = "CommunityResources"     │
│ Route to Stability360 Actions AI Agent (Aria)                       │
└──────────────┬──────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ARIA — COMMUNITY RESOURCES AGENT                                    │
│                                                                     │
│ Customer: "I need help with housing"                                │
│                                                                     │
│ ┌─ PATH A: Quick Resource Lookup (no consent needed) ───────────┐  │
│ │                                                                │  │
│ │  Aria: "Let me search for resources in your area."             │  │
│ │       → Calls resourceLookup (keyword, county/ZIP)             │  │
│ │       → Returns providers with name, phone, address            │  │
│ │  Aria: Shares top 2-3 providers                                │  │
│ │       → "Would you like more help or is that what you needed?" │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ┌─ PATH B: Full Intake + Scoring (consent required) ────────────┐  │
│ │                                                                │  │
│ │  1. ASK CONSENT                                                │  │
│ │     Aria: "I'll need to ask some personal questions..."        │  │
│ │     Customer: "Yes"                                            │  │
│ │                                                                │  │
│ │  2. COLLECT DATA (no tools called)                             │  │
│ │     Aria: "What's your name, phone/email, and county?"         │  │
│ │     Customer: "Maria Johnson, 803-555-1234, Richland County"   │  │
│ │     Aria: "Housing situation? Income? Employment?"             │  │
│ │     Customer: "Renting, $2000/mo, part-time"                   │  │
│ │                                                                │  │
│ │  3. SCORE (first tool call)                                    │  │
│ │     → Calls scoringCalculate                                   │  │
│ │     → Returns composite score + recommended path               │  │
│ │                                                                │  │
│ │  4. PRESENT OPTIONS (wait for customer choice)                 │  │
│ │     See "After Scoring" section below                          │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ┌─ PATH C: Case Status Check (no consent needed) ───────────────┐  │
│ │  Customer: "Check my case CS-20260218-AB12"                    │  │
│ │  → Calls caseStatusLookup                                      │  │
│ │  → Returns status and description                              │  │
│ └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Journey 2: Thrive@Work Path

```
Customer opens chat
        │
        ▼
   Intake Bot → Customer clicks "Thrive@Work"
        │
        ▼
   Contact Flow → selectedRoute = "ThriveAtWork"
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│ ARIA — THRIVE@WORK AGENT                                            │
│                                                                     │
│ ┌─ Employee Verification ────────────────────────────────────────┐  │
│ │  Customer: "My employee ID is TW-10001"                        │  │
│ │  → Calls employeeLookup(employee_id="TW-10001")                │  │
│ │  → Returns: matched, employer_name, partnership_status,        │  │
│ │             eligible_programs, date_enrolled                   │  │
│ │  Aria: "You're enrolled through [Employer] and eligible for    │  │
│ │         [programs]."                                           │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ┌─ General Questions ────────────────────────────────────────────┐  │
│ │  Customer: "What is Thrive@Work?"                              │  │
│ │  → Calls Retrieve (Knowledge Base)                             │  │
│ │  → Returns program info from seeded documents                  │  │
│ │  Aria: Shares program details conversationally                 │  │
│ └────────────────────────────────────────────────────────────────┘  │
│                                                                     │
│ ┌─ Escalation ───────────────────────────────────────────────────┐  │
│ │  Customer: "I need to speak to someone"                        │  │
│ │  Aria: "What are you hoping they can help with?"               │  │
│ │  → Tries to answer from KB first                               │  │
│ │  → If customer still wants a person → Escalate tool            │  │
│ └────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## After Scoring: Three Paths

Once the scoring calculator returns a recommended path, Aria presents
options and waits for the customer to choose. The customer is never
shown scores, numbers, or path labels.

```
                    scoringCalculate returns
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    DIRECT SUPPORT      MIXED          REFERRAL
   (composite < 2.5    (2.5 – 3.5)    (composite > 3.5)
    or priority flag)
           │               │               │
           ▼               ▼               ▼
  "It sounds like you   "I have a      "I have some
   could benefit from    couple of      resources that
   working with one      options        should help."
   of our team           for you."
   members."                               │
           │               │               ▼
           ▼               ▼         resourceLookup
    Customer chooses:  Customer          │
                       chooses:          ▼
  ┌──────────┬──────┐                Share providers
  │          │      │  ┌──────────┐  "Would you like
  ▼          ▼      │  │          │   a case created?"
Connect   Case for  │  ▼          ▼        │
 now      review    │ Connect   Case       ▼
  │          │      │  now      review   If yes:
  │          │      │   │         │    customerProfile
  ▼          ▼      │   ▼         ▼    charityTracker
customerProfile     │  Same as   Same    followup
  │                 │  left      as
  ▼                 │  column    left
charityTracker      │
  │                 │
  ▼                 │
Share case ref      │
  │                 │
  ▼                 │
Escalate to         │
live agent          │
                    │
              followupSchedule
              (case manager task)
```

---

## Scoring Calculator — How It Works

The Self-Sufficiency Matrix scores clients across three domains on a 1–5
scale. The AI agent NEVER calculates scores — it always delegates to the
scoringCalculate tool which uses deterministic math.

### Domain 1: Housing Stability (1–5)

```
STEP 1 — Base score from housing situation:

  Situation                    Base Score
  ─────────────────────────    ──────────
  homeless, shelter                 1
  couch_surfing, temporary,
    transitional                    2
  renting_unstable,
    renting_month_to_month         3
  renting_stable,
    owner_with_mortgage            4
  owner, owner_no_mortgage         5

STEP 2 — Housing cost-to-income ratio adjustment:

  Ratio                   Adjustment
  ────────────────        ──────────
  > 50% of income            -2
  > 40% of income            -1
  > 20% of income             0
  ≤ 20% of income            +1

STEP 3 — Challenge penalties (-0.5 each, max -2):

  eviction_notice, shutoff_notice, homeless
  → Also sets PRIORITY flag

FINAL = clamp(base + ratio_adj + challenge_adj, 1, 5)
```

### Domain 2: Employment Stability (1–5)

```
STEP 1 — Base score from employment status:

  Status                       Base Score
  ─────────────────────────    ──────────
  unable_to_work, unemployed        1
  gig_work, seasonal                2
  part_time, self_employed,
    student, full_time_below        3
  retired, full_time                4
  full_time_above_standard          5

STEP 2 — Benefits adjustment:

  Has employer benefits         +0.5
  No benefits                   -0.5

STEP 3 — Income relative to area median ($4,200/mo for SC):

  Income ratio              Adjustment
  ────────────────          ──────────
  < 50% of median              -1
  50–80% of median              0
  > 80% of median             +0.5

FINAL = clamp(base + benefits_adj + income_adj, 1, 5)
```

### Domain 3: Financial Resilience (1–5)

```
STEP 1 — Base score from expense-to-income ratio:

  Expense Ratio             Base Score
  ────────────────          ──────────
  > 100% (spending > income)     1
  90–100%                        2
  70–90%                         3
  50–70%                         4
  < 50%                          5

STEP 2 — Savings rate adjustment:

  Savings Rate              Adjustment
  ────────────────          ──────────
  ≤ 0%                         -1
  < 3%                         -0.5
  3–10%                         0
  10–20%                       +0.5
  > 20%                        +1

STEP 3 — FICO credit score adjustment:

  Range                     Adjustment
  ────────────────          ──────────
  below 580                    -1
  580–669                      -0.5
  670–739                       0
  740–799                      +0.5
  800+                         +1

FINAL = clamp(base + savings_adj + fico_adj, 1, 5)
```

### Composite Score & Path Recommendation

```
  Composite = (Housing + Employment + Financial) / 3

  ┌────────────────────────────────────────────────────────┐
  │                                                        │
  │  ANY domain score = 1  OR  priority_trigger = true     │
  │        → PRIORITY flag is set                          │
  │                                                        │
  │  PRIORITY  OR  composite < 2.5                         │
  │        → Path: DIRECT SUPPORT                          │
  │           Client needs immediate human help             │
  │                                                        │
  │  composite 2.5 – 3.5                                   │
  │        → Path: MIXED                                   │
  │           Client needs some direct help + referrals     │
  │                                                        │
  │  composite > 3.5                                       │
  │        → Path: REFERRAL                                │
  │           Client is mostly self-sufficient              │
  │           Share resources, offer optional case          │
  │                                                        │
  └────────────────────────────────────────────────────────┘
```

### Scoring Examples

```
EXAMPLE 1 — Crisis / Direct Support:
  Input:  homeless, $0 income, $0 housing cost, unemployed
  Housing:    base=1, ratio_adj=-2 (0/0→100%), challenge=0 → score=1
  Employment: base=1, benefits=-0.5, income=-1            → score=1
  Financial:  base=1 (no income), savings=-1, fico=0      → score=1
  Composite:  (1+1+1)/3 = 1.0
  Priority:   YES (housing=1)
  Path:       DIRECT SUPPORT

EXAMPLE 2 — Mixed:
  Input:  renting_stable, $2000/mo income, $800/mo rent, part_time
  Housing:    base=4, ratio_adj=-1 (40%), challenge=0     → score=3
  Employment: base=3, benefits=-0.5, income=-1            → score=1.5→2
  Financial:  base=3 (est), savings=-1, fico=0            → score=2
  Composite:  (3+2+2)/3 = 2.33
  Priority:   YES (employment clamped to 1 at extreme)
  Path:       DIRECT SUPPORT or MIXED (depends on exact calc)

EXAMPLE 3 — Referral:
  Input:  owner, $5000/mo income, $1200/mo mortgage, full_time
  Housing:    base=5, ratio_adj=0 (24%), challenge=0      → score=5
  Employment: base=4, benefits=-0.5, income=+0.5          → score=4
  Financial:  base=4 (est), savings=0, fico=0             → score=4
  Composite:  (5+4+4)/3 = 4.33
  Priority:   NO
  Path:       REFERRAL
```

---

## Behind the Scenes: What Happens When Tools Are Called

### resourceLookup

```
Customer message
        │
        ▼
   Aria extracts keyword + location
        │
        ▼
┌──────────────────────────────────────────────┐
│  MCP Gateway                                  │
│  → Forwards to API Gateway                    │
│  → POST /resources/search                     │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  Lambda: sophia_resource_lookup.py            │
│                                               │
│  1. Build search URL for sophia-app.com       │
│     (SC 211 directory API)                    │
│  2. Query with keyword + county/ZIP/city      │
│  3. Parse HTML response                       │
│  4. Extract provider details:                 │
│     - service_name, organization              │
│     - description, address, phones            │
│     - url, eligibility, fees                  │
│  5. Return structured JSON to agent           │
└──────────────────────────────────────────────┘
```

### charityTrackerSubmit

```
Customer says "Yes, create a case"
        │
        ▼
┌──────────────────────────────────────────────┐
│  MCP Gateway → API Gateway                    │
│  → POST /charitytracker/submit                │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│  Lambda: charitytracker_payload.py            │
│                                               │
│  1. Validate required fields                  │
│  2. Build HTML email from session data         │
│     (client info, intake answers, scoring,    │
│      conversation summary)                    │
│  3. Send email via Amazon SES                  │
│     → To CharityTracker inbox                 │
│  4. Store submission record in DynamoDB        │
│     (record_id, client_name, county,          │
│      escalation_tier, payload data)           │
│  5. Create Amazon Connect Case                │
│     → Generates case reference number         │
│     → Links to customer profile               │
│  6. Return record_id + case_reference          │
│     → Agent shares reference with client       │
└──────────────────────────────────────────────┘
```

### customerProfileLookup

```
┌──────────────────────────────────────────────┐
│  Lambda: customer_profile.py                  │
│                                               │
│  1. Search Amazon Connect Customer Profiles   │
│     by name, email, or phone                  │
│  2. If found → return existing profile_id     │
│     and is_returning = true                   │
│  3. If not found → create new profile         │
│     and is_returning = false                  │
│  4. Return profile_id to agent                │
│     (used to link cases to this customer)     │
└──────────────────────────────────────────────┘
```

### followupSchedule

```
┌──────────────────────────────────────────────┐
│  Lambda: followup_scheduler.py                │
│                                               │
│  If referral_type = "direct_support":         │
│    → Create Amazon Connect Task               │
│      (assigned to case manager queue)         │
│                                               │
│  If referral_type = "referral":               │
│    → Send scheduled reminder email via SES    │
│      (default: 7 days out)                    │
│                                               │
│  Store follow-up record in DynamoDB            │
│  Link to existing case via case_id             │
│  Return follow_up_id + scheduled_date          │
└──────────────────────────────────────────────┘
```

### employeeLookup (Thrive@Work only)

```
┌──────────────────────────────────────────────┐
│  Lambda: employee_lookup/index.py             │
│                                               │
│  1. Query DynamoDB employees table             │
│     by employee_id                            │
│  2. If matched:                                │
│     - employer_name                           │
│     - partnership_status (active/inactive)     │
│     - eligible_programs (list)                │
│     - date_enrolled                           │
│  3. If not matched:                            │
│     - matched = false                         │
│     - message = "Employee not found"          │
└──────────────────────────────────────────────┘
```

---

## Infrastructure Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AWS Account                                  │
│                                                                     │
│  ┌─────────────────────┐   ┌─────────────────────┐                 │
│  │ Step 1: Thrive@Work │   │ Step 2: Actions      │                 │
│  │                     │   │                      │                 │
│  │ CloudFormation      │   │ CloudFormation       │                 │
│  │ Stack               │   │ Stack                │                 │
│  │  ├─ DynamoDB        │   │  ├─ DynamoDB         │                 │
│  │  │  (employees)     │   │  │  (actions)        │                 │
│  │  ├─ Lambda          │   │  ├─ Lambda           │                 │
│  │  │  (lookup)        │   │  │  (6-tool router)  │                 │
│  │  ├─ Lambda          │   │  ├─ Lambda           │                 │
│  │  │  (intake bot)    │   │  │  (intake bot)     │                 │
│  │  ├─ API Gateway     │   │  ├─ API Gateway      │                 │
│  │  │  (1 endpoint)    │   │  │  (6 endpoints)    │                 │
│  │  ├─ MCP Gateway     │   │  ├─ MCP Gateway      │                 │
│  │  │  (1 tool)        │   │  │  (6 tools)        │                 │
│  │  └─ S3 Bucket       │   │  ├─ S3 Bucket        │                 │
│  │     (KB docs)       │   │  │  (OpenAPI spec)   │                 │
│  │                     │   │  └─ SES              │                 │
│  └─────────────────────┘   │     (email sending)  │                 │
│                            └─────────────────────┘                  │
│                                                                     │
│  ┌─────────────────────────────────────────────────┐               │
│  │ Shared Resources                                 │               │
│  │  ├─ Amazon Connect Instance                      │               │
│  │  ├─ Q Connect (Amazon Q in Connect)              │               │
│  │  │   ├─ Assistant                                │               │
│  │  │   ├─ Knowledge Base (shared S3 bucket)        │               │
│  │  │   ├─ AI Agent: Thrive@Work (default)          │               │
│  │  │   └─ AI Agent: Stability360 Actions (Aria)    │               │
│  │  ├─ Customer Profiles domain                     │               │
│  │  ├─ Amazon Connect Cases domain                  │               │
│  │  └─ Lex V2 Intake Bot                           │               │
│  └─────────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Summary

```
┌──────────┐   chat    ┌──────────┐  Lex V2   ┌──────────┐
│ Customer │ ────────► │ Connect  │ ────────► │ Intake   │
│          │           │ Instance │           │ Bot      │
└──────────┘           └────┬─────┘           └────┬─────┘
                            │                      │
                            │  selectedRoute       │
                            │  session attribute    │
                            ▼                      │
                    ┌───────────────┐               │
                    │ Contact Flow  │ ◄─────────────┘
                    │ (Check attr)  │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼                           ▼
     ┌─────────────┐            ┌─────────────┐
     │ Q Connect   │            │ Q Connect   │
     │ AI Agent    │            │ AI Agent    │
     │ (Actions)   │            │ (Thrive)    │
     └──────┬──────┘            └──────┬──────┘
            │                          │
            ▼                          ▼
     ┌─────────────┐            ┌─────────────┐
     │ MCP Gateway │            │ MCP Gateway │
     │ (6 tools)   │            │ (1 tool)    │
     └──────┬──────┘            └──────┬──────┘
            │                          │
            ▼                          ▼
     ┌─────────────┐            ┌─────────────┐
     │ API Gateway │            │ API Gateway │
     │ (6 POST)    │            │ (1 POST)    │
     └──────┬──────┘            └──────┬──────┘
            │                          │
            ▼                          ▼
     ┌─────────────┐            ┌─────────────┐
     │   Lambda    │            │   Lambda    │
     │  (router)   │            │  (lookup)   │
     └──────┬──────┘            └──────┬──────┘
            │                          │
     ┌──────┼──────┐                   │
     ▼      ▼      ▼                   ▼
  DynamoDB  SES  Connect           DynamoDB
            │    Cases             (employees)
            ▼    Profiles
         Email to
       CharityTracker
```

---

## Key Rules the Agents Follow

| Rule | Why |
|------|-----|
| One tool call per turn | Prevents blank messages in Connect chat |
| Consent before data collection | Privacy — personal info is shared with case management |
| scoringCalculate is always the FIRST tool | Ensures no premature profile/case creation |
| Never share scores with the client | Scores are internal for routing decisions only |
| Always share case reference number | Client needs it to check status later |
| resourceLookup before Retrieve | Live 211 API has real-time provider data; KB is fallback |
| Status message before every tool call | Every agent turn must have visible text |
| No employee data in Actions agent | Separation of concerns; employee data is Thrive@Work only |
| Conditional language ("may", "could") | Agent cannot make eligibility determinations |
| Escalate only after creating case | Live agent needs case context when picking up |
