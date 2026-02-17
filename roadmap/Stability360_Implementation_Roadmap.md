# Stability360 Phase 0 — Implementation Roadmap

**Project:** Stability360 Agentic AI Prototype
**Client:** Trident United Way
**Date:** February 16, 2026
**Platform:** Amazon Connect + Amazon Bedrock

---

## Architecture Principle

The AI agent handles the vast majority of work through **KB retrieval + prompts + Connect native tools**. MCP tools (Lambda functions) are reserved exclusively for special calculations and external actions that the agent fundamentally cannot do on its own.

```
AI Agent (prompts + built-in tools)
    |
    |-- READS from --> KB 1 (rules, programs, Appendix B, eligibility, language)
    |                  KB 2 (211 resources, providers, county data)
    |
    |-- USES natively --> QUESTION, FOLLOW_UP_QUESTION, ESCALATION, COMPLETE, CONVERSATION
    |
    |
    |-- CALLS MCP tools (only when it needs hands) -->
            |
            |-- Tool 1: Employee ID Lookup --- YAML 1 (Thrive@Work)
            |-- Tool 2: Scoring Calculator --- YAML 2 (Actions)
            |-- Tool 3: CharityTracker + SES -- YAML 2 (Actions)
            |-- Tool 4: Follow-up Scheduler -- YAML 2 (Actions)
```

**Rule of thumb:**
- Agent needs to **know something** --> KB
- Agent needs to **decide something conversationally** --> KB + prompt
- Agent needs to **write something** (create/update records) --> DynamoDB via MCP tool
- Agent needs to **compute something** (math, scoring) --> Lambda via MCP tool
- Agent needs to **send something** (email, task, campaign) --> Lambda via MCP tool

---

## What the AI Agent Handles Natively (No MCP Tool)

| Capability | How It Works | Decision Tree Node |
|---|---|---|
| Greeting, identity, consent | Agent prompt + KB approved language | Node 2 |
| Need identification (11 categories, subcategories) | Agent presents Quick Replies, reads KB for definitions | Node 3 |
| Path classification (referral vs direct support) | Agent reads Appendix B from KB 1, classifies in conversation | Node 5 |
| Eligibility guidance (ZIP, age, children, military) | Agent reads routing rules from KB 1 | Node 6 |
| Intake question collection | Agent asks one at a time, stores in session attributes | Node 6 |
| General inquiries | Agent retrieves from KB 1 (RAG) | Node 7 |
| Referral delivery | Agent retrieves providers from KB 2 by need + county | Node 8A |
| Escalation decisions | Agent reads escalation rules from KB 1 | Node 9, 10 |
| Escalation execution | Built-in ESCALATION tool (native) | Node 9, 10 |
| Follow-up questions | Built-in FOLLOW_UP_QUESTION tool (native) | All nodes |
| Conversation end | Built-in COMPLETE tool (native) | End states |
| Escalation handoff | AI packages conversation context + session attributes into escalation (native ESCALATION tool) | Node 9, 10 |
| Tone, language, guardrails | Prompts + 3 Bedrock Guardrails (native) | All nodes |
| Error handling language | Agent reads approved error messages from KB 1 | Node 13 |

This covers Nodes 2, 3, 5, 6, 7, 8A (delivery), 9, 10, 13 — the bulk of the conversation flow.

**Thrive@Work employees and KB access:** A Thrive@Work employee enters through Node 4 (employee ID validation via MCP Tool 1), but after validation they flow into the same KB-driven experience as any other client. The MCP tool only validates identity — it does not restrict the employee to a subset of knowledge. The employee can:
- Ask general questions answered from KB 1 (Node 7)
- Browse 211 community resources from KB 2 (Node 8A)
- Go through need identification and path classification like any client (Nodes 3, 5)
- Access referral or direct support paths (Nodes 8A, 8B)
- Request human escalation (Nodes 9, 10)

The only difference is that validated employees also have access to employer-specific programs returned by the DynamoDB lookup (stored in session attributes), and their employee ID + employer context is carried through the entire session for CharityTracker payloads and escalation handoffs.

---

## What Requires MCP Tools (4 Tools Only)

### MCP Tool 1: Employee ID Lookup

**Why it can't be KB:** Employee IDs are structured records with real-time status (active/inactive). KB is for documents, not row-level queries. You can't ask a KB "is employee ID 47291 active?" — it needs a precise DynamoDB key lookup.

- **Input:** employee_id
- **Action:** DynamoDB query on Stability360-ThriveAtWork-Employees table
- **Output:** { matched, employer_name, partnership_status, eligible_programs }
- **Used by:** Node 4 (Thrive@Work gate)
- **Validation logic:**
  - Not provided --> prompt once --> escalate (Tier 2)
  - No match --> escalate: "Employee ID not recognized"
  - Match + ACTIVE --> unlock employer-specific programs + continue with full KB access
  - Match + INACTIVE --> escalate: "Partnership no longer active"
- **Post-validation behavior:** A validated Thrive@Work employee is NOT restricted to Thrive@Work content only. After validation, the employee has full access to:
  - **KB 1** — all program info, eligibility guidance, Appendix B routing, general inquiries
  - **KB 2** — 211 community resources, provider lookups by need + county
  - **All conversation nodes** — need identification, intake, referrals, direct support, escalation
  - **Employer-unlocked programs** — additional programs returned in eligible_programs from DynamoDB are added to the employee's session as available options alongside the standard Stability360 services
  - The employee ID + employer context is carried in session attributes throughout the conversation and included in any CharityTracker payload (MCP Tool 3) or escalation handoff
- **Deployed in:** YAML 1 (Thrive@Work stack)

### MCP Tool 2: Self-Sufficiency Matrix Scoring

**Why it can't be KB or LLM:** Math. The Roadmap explicitly prohibits LLM arithmetic. Housing ratio = monthly_housing_cost / monthly_income. Financial resilience = savings rate + FICO thresholds. Composite scoring with crisis flags. An LLM will get these wrong.

- **Input:** Screening answers (housing situation, income, expenses, savings, FICO, employment, benefits)
- **Action:** Compute housing score (1-5), employment score (1-5), financial resilience score (1-5), composite score, priority flags
- **Output:** { housing_score, employment_score, financial_resilience_score, composite, priority_flag }
- **Scoring rules:**
  - Score 1 (Crisis) --> immediate escalation + priority routing
  - Score 2 (Vulnerable) --> Direct Support recommended
  - Score 3 (Stable) --> Direct Support or Referral based on need
  - Score 4 (Self-Sufficient) --> Referral Path unless client requests more
  - Score 5 (Thriving) --> Referral Path only if specific need
  - ANY domain = 1 --> overall PRIORITY flag
  - Average < 2.5 --> full Direct Support engagement
  - Average 2.5-3.5 --> mixed path
  - Average > 3.5 --> Referral Path default
- **Used by:** Node 11 (post-handoff, live agent facilitated)
- **Deployed in:** YAML 2 (Actions stack)

### MCP Tool 3: CharityTracker Payload + SES Email

**Why it can't be KB:** It's an outbound action — constructing a structured data payload and sending it to an external system. KB retrieves information, it doesn't send emails.

- **Input:** Session attributes (collected during conversation)
- **Action:** Build structured payload --> send via SES
- **Payload fields:**
  - Client name
  - Employee ID (if Thrive@Work)
  - Employer name
  - Need category and subcategories
  - ZIP code / county
  - Intake responses (all fields)
  - Extended intake (if Direct Support)
  - Conversation summary
  - Escalation tier + reason
  - Solution already provided (if Tier 3)
  - Timestamp
- **Output:** { sent: true, messageId }
- **Used by:** Node 8B (Direct Support handoff)
- **Phase 0:** SES email. When CharityTracker API available: direct API call.
- **Deployed in:** YAML 2 (Actions stack)

### MCP Tool 4: Follow-up Scheduler

**Why it can't be KB:** It's an outbound action — creating a scheduled task or triggering an outbound campaign. The agent can't call the Connect Tasks API or Outbound Campaign API through conversation alone.

- **Input:** Client contact info, referral/case ID, follow-up type, scheduled date
- **Action:** Create Connect Task assigned to live agent queue, OR trigger Outbound Campaign (SMS/email)
- **Output:** { taskId or campaignId, scheduledDate }
- **Follow-up content:** "Did you receive assistance? Do you need additional help?"
- **Logic:**
  - Referral path --> schedule automated follow-up
  - Direct Support path --> create task for assigned case manager
  - No response to follow-up --> create re-engagement campaign
- **Used by:** Node 8A (post-referral), Node 12 (closed-loop tracking)
- **Deployed in:** YAML 2 (Actions stack)

---

## CloudFormation Stacks (2 YAMLs)

### YAML 1: Thrive@Work Stack

Supports MCP Tool 1. Based on the existing hotel-api-customer.yaml patterns.

| Resource | Purpose |
|---|---|
| `Stability360-ThriveAtWork-Employees` DynamoDB table | employee_id (PK), employer_id (GSI), employer_name, partnership_status, eligible_programs, date_enrolled |
| Employee ID Lookup Lambda | MCP Tool 1 — query DynamoDB, return match result |
| Employee Data Seeding custom resource | Batch load employer/employee JSON from S3 or HTTP |
| API Gateway endpoint | Exposes the lookup for MCP tool invocation |
| IAM roles, CloudWatch logs | Supporting infrastructure |

**Source pattern:** hotel-api-customer.yaml — DynamoDB table + GetCustomerReservationsFunction + DataSeedingFunction + API Gateway. Schema and business logic change; infrastructure patterns reuse directly.

### YAML 2: Actions Stack

Supports MCP Tools 2, 3, 4. Lightweight action Lambdas sharing one stack.

| Resource | Purpose |
|---|---|
| `Stability360-ScoringResults` DynamoDB table | Stores computed matrix scores for reporting |
| Scoring Calculator Lambda | MCP Tool 2 — math from Appendix C |
| CharityTracker Payload Lambda | MCP Tool 3 — build payload + send via SES |
| Follow-up Scheduler Lambda | MCP Tool 4 — create Connect Task or Outbound trigger |
| SES verified sender identity | Email sending for CharityTracker payloads |
| API Gateway endpoints (3) | Expose each Lambda for MCP tool invocation |
| IAM roles (SES, DynamoDB, Connect Tasks) | Scoped permissions per Lambda |
| CloudWatch logs | Observability |

---

## Knowledge Bases (2 S3-Backed KBs)

### KB 1: Programs & Rules

| Content | Metadata Tag | Source |
|---|---|---|
| Thrive@Work program description, confidentiality rules, approved language, routing logic | program:thriveatwork | Governance doc |
| Utility Assistance eligibility, extended intake fields, priority escalation rules | program:utility-assistance | Governance doc |
| Referrals light-touch description, escalation thresholds | program:referrals | Governance doc |
| Referral vs Direct Support classification for all subcategories (Appendix B) | type:routing | Decision Tree |
| ZIP --> county --> agency routing rules | type:routing | Decision Tree |
| Age, children, military, employer eligibility rules | type:eligibility | Decision Tree |
| Global language guardrails, escalation templates | type:guardrails | Governance doc |
| FAQs, process explanations, document requirements | type:faq | Governance doc |

**Format:** HTML or plain text files, max 1 MB each, total under 5 GB. Each document tagged by program, content type, and version.

**Ingestion rule:** Only Class A (Authoritative) documents per Governance Protocol.

### KB 2: 211 Community Resources

| Content | Metadata Tag | Source |
|---|---|---|
| Berkeley County providers | county:berkeley | sc211_tricounty_resources.md |
| Charleston County providers | county:charleston | sc211_tricounty_resources.md |
| Dorchester County providers | county:dorchester | sc211_tricounty_resources.md |
| Tri-county providers | county:all | sc211_tricounty_resources.md |

Per resource: provider name, service description, address, phone, hours, eligibility notes, county coverage.

**Chunked** by county or service category to stay under 1 MB per document. Tagged by county and service type for filtered retrieval.

---

## AI Agent Configuration (2 Client-Facing Agent Types)

Only client-facing agents are deployed. No agent-assist agents (ANSWER_RECOMMENDATION, NOTE_TAKING, CASE_SUMMARIZATION) are included — live agents manage their own workflows post-escalation.

| Agent Type | Role | Prompts |
|---|---|---|
| SELF_SERVICE | Client-facing front door. Handles intake, general inquiries, referral delivery, need identification, eligibility guidance | Self-service answer generation, self-service pre-processing |
| ORCHESTRATION | Multi-step workflow conductor. Chains MCP tools (employee lookup, scoring, payload, follow-up) and manages conversation state across nodes | Orchestration prompt with ReAct loop |

### Prompt Behavior Requirements

- Resolution-first: answer from KB before considering escalation
- Tier 3 handling: ask reason --> answer first if possible --> respect choice
- Tone: calm, warm, plain language, conditional ("may," "could," "might")
- One focused question at a time
- Short step-by-step messages
- No jargon, acronyms, or technical detail
- Explain why information is requested
- State-aware to avoid repetition

---

## Guardrails (3 — Platform Maximum)

| Guardrail | Policies |
|---|---|
| Guardrail 1: Content Safety | Content filtering (hate, violence, sexual, insults, misconduct, prompt attacks). Denied topics (legal/medical/financial advice, payment processing, eligibility determinations). Word filters (profanity, "MUST NOT say" phrases from governance doc) |
| Guardrail 2: PII & Privacy | PII detection (email --> anonymize, credit card --> block, SSN --> block). Custom regex for employee ID masking in logs. Data minimization enforcement |
| Guardrail 3: Grounding & Language | Contextual grounding threshold (dev: 0.7, prod: 0.8). Conditional language enforcement. Blocked internal system references |

---

## Resolution & Escalation Tiers

| Tier | When | Action | MCP Tool? |
|---|---|---|---|
| Tier 1: AI resolves | KB or session data has the answer | Answer directly. No escalation | No |
| Tier 2: AI escalates | AI genuinely cannot fulfill (complex, sensitive, system failure) | Package conversation context + session attributes --> route to human queue | No |
| Tier 3: Client requests human | Client asks for a person | Ask reason --> answer first if AI can --> respect final choice --> escalate with context | No |

All three tiers use KB + native Connect tools. No MCP tools involved in escalation.

---

## Decision Tree Node Map

| Node | Name | Handled By | MCP Tool? |
|---|---|---|---|
| 1 | Entry & Session Init | Connect contact flow | No |
| 2 | Identity & Consent | Agent prompt + KB | No |
| 3 | Need Identification | Agent + KB 1 + Quick Replies | No |
| 4 | Thrive@Work Gate | **MCP Tool 1** (Employee ID Lookup) --> then full KB 1 + KB 2 access | Yes (validation only) |
| 5 | Path Classification | Agent + KB 1 (Appendix B) | No |
| 6 | Core Intake | Agent + KB 1 + session attributes | No |
| 7 | General Inquiry (Tier 1) | Agent + KB 1 (RAG) | No |
| 8A | Referral Path | Agent + KB 2 (delivery) + **MCP Tool 4** (follow-up) | Yes (follow-up only) |
| 8B | Direct Support | Agent + KB 1 (intake fields) + **MCP Tool 3** (payload + SES) | Yes (payload only) |
| 9 | Tier 2 Escalation | Agent + KB 1 + ESCALATION (native) | No |
| 10 | Tier 3 Escalation | Agent + KB 1 + ESCALATION (native) | No |
| 11 | Self-Sufficiency Matrix | **MCP Tool 2** (Scoring Calculator) | Yes |
| 12 | Closed-Loop Follow-Up | **MCP Tool 4** (Follow-up Scheduler) | Yes |
| 13 | Error Handling | Agent + KB 1 + contact flow fallback | No |

**Summary:** 13 nodes. Only 4 use MCP tools. The other 9 are fully handled by the AI agent with KB + prompts + native Connect tools.

---

## Platform Limitations Affecting Design

| Limitation | Impact | Workaround |
|---|---|---|
| Self-service: English only | No multi-lingual in Phase 0 | English only (documented constraint) |
| No multi-select in web chat | Need categories can't be checkboxes | Iterative Quick Replies + "anything else?" |
| List Picker max 10 items | 11 need categories exceeds limit | Split across 2 messages or use "Show More" |
| Max 3 guardrails per instance | Must consolidate all rules | 3 guardrails defined above |
| 30-second MCP tool timeout | All 4 Lambdas must complete within 30s | Keep Lambdas lightweight |
| 1,024 char message limit (text) | Long referral lists must be split | Multiple messages or Interactive Message Panels |
| No persistent "Talk to a person" button | Must include option in every response | Quick Reply in every AI response |
| KB: 1 MB per doc, 5 GB total | 211 data must be chunked | Split by county/service category |
| LLM unreliable for math | Scoring MUST use Lambda | MCP Tool 2 handles all scoring |

---

## Execution Order

```
KB 1 (Programs & Rules) --------+
                                |
KB 2 (211 Resources) -----------+--> Agent Prompts (M4) --> Contact Flows (M5)
                                |                               |
YAML 1 (Thrive@Work) ----------+                               |
                                                                |
YAML 2 (Actions) --------------+                               |
                                                                |
Guardrails (3) <-- continuous ----------------------------------+
                                                                |
Chat Widget (web + kiosk) <-- parallel -------------------------+
                                                                |
                                                   Testing (M8) +
                                                        |
                                                    UAT (M9)
```

- **KB 1 + KB 2 + YAML 1 + YAML 2** in parallel (no dependencies between them)
- **Agent Prompts** depend on KB 1, KB 2, YAML 1, YAML 2 (prompts reference KB content and MCP tools)
- **Contact Flows** depend on Agent Prompts
- **Guardrails, Chat Widget** parallel with Contact Flows
- **Testing** after all above complete
- **UAT** after Testing

---

## Open Questions (Need TUW Decisions)

| # | Question | Impact |
|---|---|---|
| 1 | Individual employee IDs or employer-level validation? | YAML 1 DynamoDB schema |
| 2 | 211 data format and export source? | KB 2 structure (must stay under 5 GB / 1 MB per doc) |
| 3 | 211 API available during Phase 0? | If yes, MCP Tool 4 could also resolve 211 via API instead of KB 2 |
| 4 | Email address for CharityTracker payloads? Per environment? | MCP Tool 3 SES config |
| 5 | Scheduling failure — no live agent available, what happens? | Contact flow design |
| 6 | ZIP --> county unreliable — separate county question? | Intake flow (Node 6) |
| 7 | Mixed referral + direct support — process order? | Path classification (Node 5) |
| 8 | Self-employed, retired, student, unable to work — routing? | Employment routing in KB 1 |
| 9 | Self-Sufficiency Matrix Score 5 (Financial Resilience) = Score 1 in source doc — doc error? | MCP Tool 2 scoring logic |
| 10 | Who receives escalations? Single queue or by type/reason? | Contact flow routing |
| 11 | Kiosk inactivity timeout duration? | Widget config (2-480 min range) |
| 12 | Kiosk device specs (screen size, touch)? | Widget UX |
| 13 | Which domains need allowlisting? (max 5) | Widget deployment |

---

## What the Prototype Delivers

- **Single interface:** Amazon Connect chat widget (web + kiosk fullscreen)
- **2 AI agents (client-facing only):** SELF_SERVICE (front door) + ORCHESTRATION (multi-step workflows)
- **2 Knowledge Bases:** Programs/rules (KB 1, tagged by program) + 211 resources (KB 2, tagged by county)
- **4 MCP tools:** Employee ID lookup, scoring calculator, CharityTracker payload + SES, follow-up scheduler
- **2 CloudFormation stacks:** Thrive@Work (YAML 1) + Actions (YAML 2)
- **3 Guardrails:** Content safety, PII/privacy, grounding/language
- **3-tier resolution:** AI resolves (Tier 1), AI escalates (Tier 2), client requests human (Tier 3)
- **13-node decision tree:** 9 nodes KB-driven, 4 nodes use MCP tools
- **Closed-loop referral tracking** via follow-up scheduler
- **Automated follow-up** via Connect Tasks + Outbound Campaigns
- **English only** (platform constraint)
- **Simulated multi-select** via iterative Quick Replies (platform constraint)
- **"Talk to a person"** as Quick Reply in every response (no persistent button in hosted widget)
