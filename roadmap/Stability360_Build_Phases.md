# Stability360 Phase 0 — Build Phases

**Project:** Stability360 Agentic AI Prototype
**Date:** February 16, 2026

---

## Build Order Logic

The build follows one rule: **nothing downstream can start until its inputs exist.** The AI agent can't be prompted until the KBs and MCP tools exist. The contact flows can't route until the agent is configured. Testing can't start until the flows work.

```
PHASE 1: Content + Backend (parallel)
    |
    v
PHASE 2: Agent Configuration (depends on Phase 1)
    |
    v
PHASE 3: Conversation Flows + Widget (depends on Phase 2)
    |
    v
PHASE 4: Testing + Tuning (depends on Phase 3)
    |
    v
PHASE 5: UAT + Iteration (depends on Phase 4)
```

---

## PHASE 1: Foundation (Parallel Tracks)

Everything in Phase 1 can be built simultaneously — no dependencies between tracks.

### Track A: KB 1 — Programs & Rules

**What:** Build the S3-backed Knowledge Base that the AI agent reads for all program logic, routing rules, eligibility guidance, and approved language.

**Steps:**

1. Get TUW sign-off on KB v1 content (program descriptions, Appendix B classification, eligibility rules, approved/prohibited language)
2. Write Class A documents following the Governance Protocol:
   - Thrive@Work program doc (tagged `program:thriveatwork`)
   - Utility Assistance program doc (tagged `program:utility-assistance`)
   - Referrals light-touch doc (tagged `program:referrals`)
   - Referral vs Direct Support classification doc — all 47 subcategories from Appendix B (tagged `type:routing`)
   - ZIP → county → agency routing doc (tagged `type:routing`)
   - Age, children, military, employer eligibility rules doc (tagged `type:eligibility`)
   - Global language guardrails + escalation templates (tagged `type:guardrails`)
   - FAQ content (tagged `type:faq`)
3. Validate each document against the ingestion checklist (Class A? Named owner? Under 1 MB? No "MUST NOT say" content?)
4. Upload to S3 bucket with metadata tags
5. Create KB in Amazon Connect (Q in Connect) pointing to S3
6. Test retrieval: query KB with sample questions, verify correct documents are returned with correct tag filtering

**Depends on:** TUW content approval
**Blocks:** Phase 2 (agent prompts need KB to exist)

---

### Track B: KB 2 — 211 Community Resources

**What:** Build the S3-backed Knowledge Base for community resource lookups.

**Steps:**

1. Confirm 211 data source and format with TUW (sc211_tricounty_resources.md is the current draft — is this the final dataset?)
2. Chunk the resource directory into documents by county and/or service category:
   - Berkeley County resources (tagged `county:berkeley`)
   - Charleston County resources (tagged `county:charleston`)
   - Dorchester County resources (tagged `county:dorchester`)
   - Tri-county resources (tagged `county:all`)
   - Optionally also tag by service type: `service:food`, `service:housing`, `service:health`, etc.
3. Validate each chunk is under 1 MB
4. Upload to separate S3 bucket with metadata tags
5. Create KB 2 in Amazon Connect
6. Test retrieval: "Where can I get food help in Berkeley County?" — verify correct providers returned

**Depends on:** TUW 211 data confirmation
**Blocks:** Phase 2 (agent needs KB 2 for referral delivery)

---

### Track C: YAML 1 — Thrive@Work Stack (CloudFormation)

**What:** Deploy the DynamoDB table + Lambda MCP tool for employee ID validation.

**Steps:**

1. Resolve open question: individual employee IDs or employer-level validation? (TUW decision — blocks schema)
2. Adapt hotel-api-customer.yaml patterns:
   - Replace `HotelsTable` → `Stability360-ThriveAtWork-Employees` (employee_id PK, employer_id GSI)
   - Replace `GetCustomerReservationsFunction` → Employee ID Lookup Lambda
   - Replace `DataSeedingFunction` → Employee data seeder (same pattern, different data shape)
   - Strip out unused resources (ReservationsTable, SearchHotels, CreateReservation, CancelReservation, ModifyReservation, OpenAPI bucket)
   - Keep: API Gateway endpoint, IAM roles, CloudWatch logs
3. Create sample employee seed data JSON (test employers, test employee IDs)
4. Deploy stack to dev environment
5. Test: call the API with a valid employee ID → get match. Call with invalid → get no match. Call with inactive → get inactive status.

**Depends on:** TUW employee ID schema decision
**Blocks:** Phase 2 (ORCHESTRATION agent needs the MCP tool registered)

---

### Track D: YAML 2 — Actions Stack (CloudFormation)

**What:** Deploy the 3 action Lambdas (scoring, payload+SES, follow-up).

**Steps:**

1. Resolve open questions: CharityTracker email address? Self-Sufficiency Matrix Score 5 doc error? (TUW decisions)
2. Build Scoring Calculator Lambda:
   - Implement housing ratio calculation from Appendix C
   - Implement employment score mapping from Appendix C
   - Implement financial resilience calculation from Appendix C
   - Implement composite scoring + priority flag logic
   - Unit test with sample inputs from the matrix tables
3. Build CharityTracker Payload Lambda:
   - Define payload schema (all fields from session attributes)
   - Implement SES email sending
   - Verify SES sender identity in dev environment
4. Build Follow-up Scheduler Lambda:
   - Implement Connect Tasks API call (create task with scheduled date, assign to queue)
   - OR implement Outbound Campaign trigger
   - Test: verify task appears in agent workspace
5. Create API Gateway with 3 endpoints
6. Deploy stack to dev environment
7. Test each Lambda independently

**Depends on:** TUW decisions on email + scoring
**Blocks:** Phase 2 (ORCHESTRATION agent needs these MCP tools registered)

---

### Track E: Guardrails (3)

**What:** Create the 3 Bedrock Guardrails in Amazon Connect.

**Steps:**

1. Create Guardrail 1 (Content Safety):
   - Configure content filters: hate, violence, sexual, insults, misconduct, prompt attacks
   - Add denied topics: legal advice, medical advice, financial advice, payment processing, eligibility determinations
   - Add word filters: profanity list + "MUST NOT say" phrases from Governance doc
2. Create Guardrail 2 (PII & Privacy):
   - Configure PII detection: email → anonymize, credit card → block, SSN → block
   - Add custom regex for employee ID masking in logs
3. Create Guardrail 3 (Grounding & Language):
   - Set contextual grounding threshold: 0.7 (dev), will increase to 0.8 (prod)
   - Configure conditional language enforcement
   - Block internal system references

**Depends on:** "MUST NOT say" phrases from TUW Governance doc
**Blocks:** Phase 2 (guardrails are attached to agent configuration)

---

## Phase 1 Summary

```
Track A: KB 1 (Programs & Rules) ------+
                                       |
Track B: KB 2 (211 Resources) ---------+--> All feed into Phase 2
                                       |
Track C: YAML 1 (Thrive@Work) --------+
                                       |
Track D: YAML 2 (Actions) ------------+
                                       |
Track E: Guardrails (3) ---------------+
```

**All 5 tracks run in parallel.** None depend on each other. The single prerequisite for all of them is TUW answering the open questions.

---

## PHASE 2: Agent Configuration

**Starts when:** At least KB 1, KB 2, and the MCP tools from YAML 1 + YAML 2 are deployed and tested.

### Step 1: Register MCP Tools

Register each Lambda as an MCP tool that the AI agent can call:

| MCP Tool | Lambda Source | Input Schema |
|---|---|---|
| Employee ID Lookup | YAML 1 | `{ employee_id: string }` |
| Scoring Calculator | YAML 2 | `{ housing_situation, monthly_income, monthly_housing_cost, ... }` |
| CharityTracker Payload | YAML 2 | `{ client_name, employee_id, need_category, zip_code, ... }` |
| Follow-up Scheduler | YAML 2 | `{ contact_info, referral_id, follow_up_type, scheduled_date }` |

Each tool registered via flow module or AgentCore Gateway with a clear name and description so the AI agent knows when to invoke it.

### Step 2: Configure SELF_SERVICE Agent

Create the SELF_SERVICE AI agent with:

- Custom self-service answer generation prompt:
  - Identity: "You are a supportive guide for Stability360..."
  - Tone rules: calm, warm, plain language, conditional phrasing
  - Resolution-first: always try KB before escalation
  - Tier 3 handling: ask reason → answer first → respect choice
  - One question at a time
  - "Talk to a person" Quick Reply in every response
  - Never give legal/medical/financial advice
  - Never make eligibility determinations
- Custom self-service pre-processing prompt:
  - Extract intent from client messages
  - Map to need categories when possible
- Attach KB 1 and KB 2
- Attach Guardrails 1, 2, 3

### Step 3: Configure ORCHESTRATION Agent

Create the ORCHESTRATION AI agent with:

- Orchestration prompt with ReAct loop:
  - When Thrive@Work employee → invoke Employee ID Lookup tool
  - When direct support intake complete → invoke CharityTracker Payload tool
  - When referral delivered → invoke Follow-up Scheduler tool
  - When live agent requests scoring → invoke Scoring Calculator tool
  - Decision logic for when to chain tools vs when to return to conversation
- Attach all 4 MCP tools
- Attach KB 1 and KB 2
- Attach Guardrails 1, 2, 3

### Step 4: Smoke Test

Test basic conversations in the Amazon Connect test console:

- "What is Stability360?" → KB 1 answer (no tools)
- "I need help with food" → need identification → subcategories → path classification (KB 1)
- "I'm connecting through my employer" → employee ID prompt → MCP Tool 1 → validation result
- Ask for a person → Tier 3 flow → reason → answer attempt → respect choice

**Depends on:** Phase 1 complete
**Blocks:** Phase 3

---

## PHASE 3: Conversation Flows + Widget

**Starts when:** Both agents are configured and smoke-tested.

### Step 1: Build Contact Flows

Create the Amazon Connect contact flows that wire everything together:

**Main Inbound Flow:**
- Entry → set initial session attributes → invoke Q in Connect (SELF_SERVICE agent)
- Agent handles the entire conversation via prompts + KB + tools

**Escalation Flow:**
- Triggered by ESCALATION tool
- Check session attributes for escalation reason
- Route to appropriate human agent queue
- Pass full conversation context

**Disconnect Flow:**
- Kiosk: clear session, display "Your session has ended" message
- Web: save contactId for persistent chat resumption

**Transfer Flow (if needed):**
- Route from one queue to another based on need category or program

### Step 2: Configure Queues

- General escalation queue (Tier 2 / Tier 3 default)
- Optionally: separate queues by program or need category (TUW decision — open question #10)
- Operating hours: define when live agents are available
- After-hours message: "Our team is currently offline. We've saved your information and someone will follow up during business hours."

### Step 3: Deploy Chat Widget

**Web configuration:**
- Embed JS snippet on TUW website
- Custom branding: Stability360/TUW logo, colors
- Responsive layout (min 300px)
- Persistent chat: store contactId for session resumption
- Interactive messages enabled (Quick Reply, List Picker)
- Rich text enabled (bold, links)

**Kiosk configuration:**
- Same widget with:
  - `fullscreen.fullscreenOnLoad: true`
  - `skipIconButtonAndAutoLaunch: true`
  - Idle timeout: configurable (TUW decision — open question #11)
  - Auto-disconnect timeout after idle
- No persistent chat — fresh session every time

### Step 4: End-to-End Smoke Test

Walk through the complete flow on both web and kiosk:
- Entry → greeting → need selection → intake → referral delivery → follow-up
- Entry → greeting → Thrive@Work → employee ID → validation → continue to needs
- Mid-conversation general question → KB answer → back to flow
- Request human → Tier 3 flow → escalation

**Depends on:** Phase 2 complete
**Blocks:** Phase 4

---

## PHASE 4: Testing + Tuning

**Starts when:** End-to-end flow works on web and kiosk.

### Round 1: Happy Path Testing

Test every node of the decision tree end-to-end:

| Test | Path |
|---|---|
| General inquiry only | Entry → question → KB answer → complete |
| Referral (food pantry, Berkeley) | Entry → food → food pantries → intake → KB 2 → referral → follow-up |
| Referral (transportation, Charleston) | Entry → transportation → bus tickets → intake → KB 2 → referral → follow-up |
| Direct Support (utility assistance) | Entry → housing → utilities → intake → extended intake → MCP Tool 3 → payload sent → follow-up |
| Thrive@Work + referral | Entry → employer → employee ID → MCP Tool 1 → validated → food → food pantries → KB 2 → referral |
| Thrive@Work + direct support | Entry → employer → employee ID → MCP Tool 1 → validated → housing → rental → intake → MCP Tool 3 → payload |
| Mixed path (referral + direct support) | Entry → food pantries + rental assistance → referral first → then direct support → both followed up |

### Round 2: Escalation Testing

| Test | Expected Behavior |
|---|---|
| Client requests human (reason given, AI can answer) | AI answers from KB → "Still want a person?" → Yes → escalate with context |
| Client requests human (reason given, AI can't answer) | AI escalates immediately with context |
| Client requests human (no reason) | AI escalates to general queue |
| Safety concern disclosed | Immediate Tier 2 escalation |
| System failure (Lambda timeout) | Calm error message → escalation |
| Employee ID not found | Prompt retry once → escalate |
| Imminent utility shutoff (72 hrs) | Priority Tier 2 escalation |

### Round 3: Edge Cases

| Test | Expected Behavior |
|---|---|
| Client disengages mid-intake | Partial data preserved in session attributes. Follow-up scheduled if contact info collected. |
| Out-of-service-area ZIP | AI acknowledges limitation, offers 211 as fallback |
| Client selects "Other" (free text) | AI classifies from context, routes appropriately |
| Same question asked 3 times | AI detects frustration, offers escalation |
| Prompt injection attempt | Guardrail 1 blocks it |
| Client asks for medical advice | Guardrail 1 denied topic → AI declines, offers escalation |
| Message exceeds 1024 chars | Split across multiple messages |
| 11 need categories (exceeds List Picker 10-item max) | Split into 2 messages or "Show More" |

### Round 4: Platform Constraint Testing

| Test | Expected |
|---|---|
| MCP tool completes under 30 seconds | All 4 tools pass |
| Quick Reply items ≤ 10 per message | Pass |
| Text messages ≤ 1024 characters | Pass or correctly split |
| Guardrails fire on blocked content | All 3 fire correctly |
| KB retrieval uses correct metadata filters | program and county tags work |
| Persistent chat resumes on web | Session rehydrated correctly |
| Kiosk auto-disconnect clears state | Next user gets fresh session |
| Kiosk next session has no prior data | Confirmed isolated |

### Round 5: Prompt Tuning

Based on Rounds 1-4 results:
- Adjust agent prompts where AI deviates from expected behavior
- Tighten KB content where retrieval returns wrong or incomplete info
- Tune guardrail thresholds if too aggressive (blocking valid content) or too loose (letting prohibited content through)
- Adjust grounding threshold if hallucination detected

Prompt tuning is iterative — expect 2-3 cycles minimum.

### Round 6: Scoring Validation

Test MCP Tool 2 (Self-Sufficiency Matrix) against known inputs from Appendix C:

| Input Scenario | Expected Scores |
|---|---|
| Homeless, unemployed seeking work, expenses > income | Housing: 1, Employment: 1, Financial: 1, Composite: PRIORITY |
| Temporary housing, part-time seeking full-time, income = expenses | Housing: 2, Employment: 2, Financial: 2, Composite: Direct Support |
| Stable rent with subsidy, full-time below standard, limited savings | Housing: 3, Employment: 3, Financial: 3, Composite: Mixed |
| Own home <35% income, full-time above standard, 5% savings | Housing: 4, Employment: 4, Financial: 4, Composite: Referral |

**Depends on:** Phase 3 complete
**Blocks:** Phase 5

---

## PHASE 5: UAT + Iteration

**Starts when:** All testing rounds pass and prompts are tuned.

### UAT Participants

| Who | What They Test |
|---|---|
| TUW staff | All 3 programs end-to-end. Content accuracy. Tone and language. |
| Coalition partners (live agents) | Escalation context quality. Do they have enough info to help without re-asking? |
| Test users (client personas) | Real-world conversation patterns. Unexpected questions. Natural language variation. |
| Kiosk testers | Physical device testing. Fullscreen UX. Timeout behavior. Session isolation. |

### UAT Scenarios

1. **Persona: Single parent, needs food + child care**
   - Mixed path: food pantry (referral) + child care subsidies (direct support)
   - Expects: referral delivered + payload sent + follow-up scheduled for both

2. **Persona: Thrive@Work employee, utility shutoff in 48 hours**
   - Thrive@Work validation + utility assistance (direct support) + PRIORITY escalation
   - Expects: immediate Tier 2 escalation with all context

3. **Persona: Veteran, needs legal aid + housing**
   - Military eligibility → Mission United. Housing (direct support). Legal aid (direct support).
   - Expects: both flagged as direct support, veteran programs surfaced

4. **Persona: Client just wants to talk to someone**
   - Tier 3 immediately. Declines to give reason.
   - Expects: escalated to general queue with whatever data was collected

5. **Persona: Client asks off-topic questions**
   - "What's the weather?" "Can you help me with my taxes?" "Tell me a joke"
   - Expects: polite decline, redirect to what AI can help with

6. **Kiosk: Client walks away mid-conversation**
   - Idle timeout → auto-disconnect → session cleared
   - Next person gets fresh session with no prior data visible

### Iteration

Based on UAT feedback:
- Content corrections in KB 1 / KB 2 (re-upload to S3, re-sync)
- Prompt adjustments (no redeployment needed — prompts are configuration)
- Guardrail tuning
- Flow adjustments
- Repeat UAT cycle until TUW approves

---

## Timeline View

```
PHASE 1: Foundation (parallel tracks)
|  Track A: KB 1 content          |████████████████|
|  Track B: KB 2 content          |████████████████|
|  Track C: YAML 1 (Thrive@Work) |████████████████|
|  Track D: YAML 2 (Actions)     |████████████████|
|  Track E: Guardrails            |████████████████|
                                   |
PHASE 2: Agent Configuration       |████████|
                                            |
PHASE 3: Flows + Widget                    |████████|
                                                    |
PHASE 4: Testing + Tuning                          |████████████|
                                                                |
PHASE 5: UAT + Iteration                                       |████████████|
```

Phase 1 is the longest because it depends on TUW decisions and content creation. Phases 2-3 are configuration, not code. Phase 4-5 are iterative.

---

## What Blocks Everything

```
TUW DECISIONS (must happen before Phase 1 starts)
    |
    |-- Employee ID schema (individual vs employer-level)
    |   --> Blocks Track C (YAML 1)
    |
    |-- 211 data format + confirmation
    |   --> Blocks Track B (KB 2)
    |
    |-- CharityTracker email address
    |   --> Blocks Track D (YAML 2, MCP Tool 3)
    |
    |-- KB v1 content sign-off
    |   --> Blocks Track A (KB 1)
    |
    |-- "MUST NOT say" phrases
    |   --> Blocks Track E (Guardrails)
    |
    |-- Scoring doc error (Score 5 = Score 1?)
    |   --> Blocks Track D (YAML 2, MCP Tool 2)
```

**Recommendation:** Schedule a single TUW decision session to resolve all 6 blockers at once. Everything else can proceed in parallel after that.

---

## Start Here (Day 1)

If TUW decisions are pending, these can start immediately without any approvals:

1. **Set up the Amazon Connect instance** — create instance, enable Q in Connect, configure basic settings
2. **Set up the dev AWS environment** — S3 buckets for KBs, DynamoDB provisioning, Lambda execution roles, SES verification
3. **Adapt YAML 1 from hotel-api-customer.yaml** — strip unused resources, rename to Stability360, set up DynamoDB schema placeholder (finalize after TUW decision)
4. **Scaffold YAML 2** — create the CloudFormation template structure for the 3 action Lambdas with placeholder logic
5. **Draft agent prompts** — write the SELF_SERVICE and ORCHESTRATION prompts based on the PRD tone/behavior requirements (can iterate before KBs exist)
6. **Draft KB 1 documents** — start writing program descriptions, routing rules, eligibility docs based on existing docs/ content (finalize after TUW sign-off)
7. **Prepare KB 2 documents** — chunk sc211_tricounty_resources.md by county/service type into KB-ready documents

Items 1-4 are infrastructure. Items 5-7 are content. Both tracks can happen simultaneously on day 1.
