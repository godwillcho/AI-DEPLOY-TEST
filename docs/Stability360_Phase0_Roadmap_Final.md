# Stability360 CONNECT_AI — Phase 0 Prototype Roadmap (FINAL)

*Version: Final — Validated against Amazon Connect capabilities*
*Date: February 12, 2026*

---

## Feasibility Assessment

Every feature in this plan has been validated against Amazon Connect and Amazon Bedrock documentation. Each item is marked:

- **NATIVE** — Built-in Amazon Connect / Bedrock capability
- **SUPPORTED** — Achievable via Lambda, MCP tools, or flow modules
- **WORKAROUND** — Requires custom development or alternate approach
- **LIMITATION** — Platform constraint that affects design

---

## Platform Capabilities & Constraints

| Capability | Status | Documentation Reference |
|---|---|---|
| AI self-service chat | **NATIVE** — SELF_SERVICE agent type | [Self-service docs](https://docs.aws.amazon.com/connect/latest/adminguide/generative-ai-powered-self-service.html) |
| Multi-step orchestration | **NATIVE** — ORCHESTRATION agent type with ReAct loop | [Orchestration agent docs](https://docs.aws.amazon.com/connect/latest/adminguide/use-orchestration-ai-agent.html) |
| Lambda tool calls | **NATIVE** — via MCP tools, flow modules, AgentCore Gateway | [MCP tools docs](https://docs.aws.amazon.com/connect/latest/adminguide/ai-agent-mcp-tools.html) |
| DynamoDB queries | **SUPPORTED** — Lambda calls DynamoDB via boto3 | [Bedrock Agent + DynamoDB sample](https://github.com/build-on-aws/bedrock-agent-appointment-manager-dynamodb) |
| External API calls | **SUPPORTED** — Lambda makes HTTP calls to any API | [Action groups docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-action-add.html) |
| S3 Knowledge Base | **NATIVE** — Q in Connect KB backed by S3 | [KB setup docs](https://docs.aws.amazon.com/connect/latest/adminguide/setup-knowledgebase.html) |
| Multiple KBs per agent | **NATIVE** — since Nov 2025 | [Multiple KB announcement](https://aws.amazon.com/about-aws/whats-new/2025/11/amazon-connect-multiple-knowledge-bases-integrates-amazon-bedrock-knowledge-bases/) |
| KB metadata filtering | **NATIVE** — contentTagFilter + S3 prefix filtering | [Session context docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html) |
| Guardrails (content, PII, topics) | **NATIVE** — Bedrock Guardrails in Connect | [Guardrails docs](https://docs.aws.amazon.com/connect/latest/adminguide/create-ai-guardrails.html) |
| Contextual grounding | **NATIVE** — threshold-based hallucination detection | [Bedrock Guardrails docs](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html) |
| Email sending (SES) | **SUPPORTED** — Lambda calls SES | [Lambda for agents docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html) |
| Conversation state (within session) | **NATIVE** — session attributes + conversation history | [Session state docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-session-state.html) |
| Persistent chat (across sessions) | **NATIVE** — chat rehydration with SourceContactId | [Persistent chat docs](https://docs.aws.amazon.com/connect/latest/adminguide/chat-persistence.html) |
| Escalation to human | **NATIVE** — ESCALATION and HANDOFF tools with context | [Self-service docs](https://docs.aws.amazon.com/connect/latest/adminguide/generative-ai-powered-self-service.html) |
| Contact flow branching | **NATIVE** — Check contact attributes + custom branches | [Contact flows docs](https://docs.aws.amazon.com/connect/latest/adminguide/connect-contact-flows.html) |
| Automated follow-up | **NATIVE** — Outbound Campaigns (email, SMS) + Tasks API | [Outbound docs](https://aws.amazon.com/connect/outbound/), [Tasks docs](https://docs.aws.amazon.com/connect/latest/adminguide/tasks.html) |
| Mathematical scoring | **SUPPORTED** — Lambda or Code Interpreter (not LLM alone) | [Code Interpreter docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html) |
| Chat widget on web | **NATIVE** — embed JS snippet | [Chat widget docs](https://docs.aws.amazon.com/connect/latest/adminguide/add-chat-to-website.html) |
| Chat widget fullscreen (kiosk) | **NATIVE** — fullscreenOnLoad + fullscreen mode | [Custom styles docs](https://docs.aws.amazon.com/connect/latest/adminguide/pass-custom-styles.html) |
| Auto-disconnect / timeout | **NATIVE** — UpdateParticipantRoleConfig (2-480 min) | [Chat timeouts docs](https://docs.aws.amazon.com/connect/latest/adminguide/setup-chat-timeouts.html) |
| Rich text in chat | **NATIVE** — bold, italic, lists, links (no tables) | [Text formatting docs](https://docs.aws.amazon.com/connect/latest/adminguide/enable-text-formatting-chat.html) |
| Interactive messages | **NATIVE** — List Picker, Time Picker, Quick Reply, Panel, Carousel | [Interactive messages docs](https://docs.aws.amazon.com/connect/latest/adminguide/interactive-messages.html) |
| Step-by-step guides in chat | **NATIVE** — Form View, Detail View, Cards View | [Guides in chat docs](https://docs.aws.amazon.com/connect/latest/adminguide/step-by-step-guides-chat.html) |

### Platform Limitations That Affect Design

| Limitation | Impact | Documented Source |
|---|---|---|
| **Self-service: English only** | No multi-lingual AI self-service in Phase 0 | [Self-service docs](https://docs.aws.amazon.com/connect/latest/adminguide/generative-ai-powered-self-service.html) |
| **No multi-select in web chat** | Need categories cannot be collected as multi-select checkboxes. Must use sequential List Pickers or Quick Replies (single-select) or step-by-step guide Forms | [Interactive messages docs](https://docs.aws.amazon.com/connect/latest/adminguide/interactive-messages.html) |
| **List Picker max 10 items** | 11 need categories exceeds limit. Use "Show More" action buttons or split into two messages | [Interactive messages docs](https://docs.aws.amazon.com/connect/latest/adminguide/interactive-messages.html) |
| **Max 3 guardrails per instance** | Must consolidate all guardrail rules into 3 or fewer guardrail configurations | [Guardrails docs](https://docs.aws.amazon.com/connect/latest/adminguide/create-ai-guardrails.html) |
| **30-second MCP tool timeout** | Lambda functions (DynamoDB lookup, API calls, email) must complete within 30 seconds | [MCP tools docs](https://docs.aws.amazon.com/connect/latest/adminguide/ai-agent-mcp-tools.html) |
| **1,024 char message limit** (text/markdown) | Long referral lists or detailed program info must be split across multiple messages or use interactive messages (12,000 char JSON limit) | [Service quotas](https://docs.aws.amazon.com/connect/latest/adminguide/amazon-connect-service-limits.html) |
| **No always-visible "Talk to a person" button** (hosted widget) | Must include escalation option in every AI response via Quick Reply, or use custom/self-hosted widget | [Interactive messages docs](https://docs.aws.amazon.com/connect/latest/adminguide/interactive-messages.html) |
| **5 domain allowlist limit** | Hosted widget limited to 5 registered domains | [Chat widget docs](https://docs.aws.amazon.com/connect/latest/adminguide/add-chat-to-website.html) |
| **KB: 1 MB per document, 5 GB total, 5,000 items** | 211 data must be chunked appropriately. Large directories need multiple smaller documents | [KB setup docs](https://docs.aws.amazon.com/connect/latest/adminguide/setup-knowledgebase.html) |
| **Persistent chat requires custom storage** | Must build own repository to store/retrieve contactIds for session resumption | [Persistent chat docs](https://docs.aws.amazon.com/connect/latest/adminguide/chat-persistence.html) |
| **LLM unreliable for math** | Self-Sufficiency Matrix scoring MUST use Lambda, not LLM arithmetic | [Code Interpreter docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html) |

---

## Core Design Principles

| Principle | Detail |
|-----------|--------|
| **Single interface: Amazon Connect chat widget** | Web (embedded) and kiosk (fullscreen mode). Same widget, same agent |
| **Resolve first** | If KB or API can answer → answer directly. No unnecessary escalation |
| **Escalate only when necessary** | Only when AI genuinely cannot fulfill |
| **Client-requested escalation: answer first** | Ask why → answer if AI can → respect final choice |
| **API-first, KB-fallback** | API if configured → KB if not → escalate if both fail |
| **Full skeleton, scoped resolution** | All categories captured. Resolve what AI can. Escalate the rest |
| **English only (Phase 0)** | Platform limitation: self-service supports English only |

---

## Resolution & Escalation Logic

```
Client request / question
    │
    ├── Can the KB or API answer this?
    │   ├── YES → Answer directly. No escalation.
    │   │
    │   └── NO → Requires human involvement?
    │       ├── YES → Tier 2: Escalate with full context
    │       └── UNCERTAIN → Best answer with conditional language
    │                       → Offer specialist option
    │
    └── Client requests a human (Tier 3)
        │
        ▼
        AI: "Could you share what you're hoping they can help with?"
        │
        ├── Client gives reason
        │   ├── AI CAN answer from KB/API
        │   │   → Provide the answer first
        │   │   → "I hope that helps. Would you still like
        │   │      me to connect you with someone?"
        │   │   ├── Yes → Escalate (context + reason +
        │   │   │         solution already provided)
        │   │   └── No → Continue in AI flow
        │   │
        │   └── AI CANNOT answer
        │       → Escalate with context + reason
        │
        └── Client declines to give reason
            → "No problem at all."
            → Escalate to general queue with all data
```

**Three tiers:**

| Tier | When | Action |
|------|------|--------|
| **Tier 1: AI resolves** | KB or API has the answer | Answer directly. No escalation |
| **Tier 2: AI escalates** | AI genuinely cannot fulfill | Package context → escalate |
| **Tier 3: Client requests human** | Client asks for a person | Ask reason → answer first if AI can → respect final choice → escalate with context |

---

## What the AI Resolves Directly (Tier 1)

| Query Type | Source | Example |
|------------|--------|---------|
| Program information | KB | "What is Thrive@Work?" |
| Eligibility guidance (non-binding) | KB | "Am I eligible?" → conditional answer |
| Community resource lookup | 211 (API or KB) | "Where can I get food near me?" |
| Service area confirmation | KB | "Do you serve Dorchester County?" |
| Process explanation | KB | "What happens after intake?" |
| Document requirements | KB | "What do I need for my appointment?" |
| Provider hours/availability | 211 (API or KB) | "When is the food pantry open?" |
| General Stability360 info | KB | "What is Stability360?" |
| Referral delivery | 211 (API or KB) | Full referral flow end-to-end |
| Intake and routing | KB + DynamoDB | Full intake through to resolution |

---

## What Requires Human Escalation (Tier 2)

| Situation | AI Does First | Then Escalates |
|-----------|--------------|----------------|
| Final eligibility determination | Pre-screens with conditional language | "You may be eligible. Let me connect you with someone who can confirm." |
| Payment processing | Captures financial details | "Let me connect you with someone who can help process that." |
| Safety concern disclosure | Acknowledges with empathy | Immediate escalation to trained human |
| Out-of-scope program + no 211 match | Attempts 211 lookup, captures intake | "I've captured everything so a specialist can help." |
| Legal / medical / financial advice | Acknowledges the need | "That needs the right expertise. Let me connect you." |
| System failure (API + KB both down) | Acknowledges calmly | "I'm having a technical issue. Let me connect you." |
| Employee ID validation failure | Prompts re-entry once | Escalate with context |
| Direct Support outside Utility Assistance | Captures full intake | Escalate with all data |

---

## Data Architecture

```
┌───────────────────────────────────────────────────────────┐
│  Amazon Connect                                           │
│  ├── Chat Widget (web embed + kiosk fullscreen)           │
│  ├── Contact Flows (branching, routing, escalation)       │
│  ├── Q in Connect (AI agent orchestration)                │
│  └── Outbound Campaigns (automated follow-up)             │
└───────────────────────────────────────────────────────────┘
         │
         ▼
┌───────────────────────────────────────────────────────────┐
│  S3 Knowledge Base(s) — Q in Connect                      │
│  Multiple KBs supported (Nov 2025). Metadata filtering    │
│  via contentTagFilter for layer separation.                │
│                                                           │
│  KB 1: thriveatwork + program-rules                       │
│  │  Program descriptions, confidentiality rules,          │
│  │  approved language, routing logic, eligibility,         │
│  │  referral/direct support classification,                │
│  │  escalation thresholds, intake definitions.             │
│  │  Tagged by program for filtered retrieval.              │
│  │                                                        │
│  KB 2: 211-resources                                      │
│     Community resource directory. Provider names,          │
│     services, addresses, phone, hours, geography.          │
│     Used when 211 API not configured.                     │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│  MCP Tools / Lambda Functions                             │
│  (30-second timeout per invocation)                       │
│                                                           │
│  ├── Employee ID Lookup → DynamoDB                        │
│  ├── Data Resolver → API or KB fallback                   │
│  ├── CharityTracker Payload → SES email (or API)          │
│  ├── Scoring Calculator → Self-Sufficiency Matrix         │
│  └── Follow-up Scheduler → Tasks API / Outbound           │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│  DynamoDB: Stability360-ThriveAtWork-Employees            │
│  employee_id (PK) | employer_id | employer_name |         │
│  partnership_status | eligible_programs | date_enrolled    │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│  Knowledge Lake / Data Lake                               │
│  Interactions, referrals, intake, outcomes, escalation     │
│  records + reasons, trend data.                           │
└───────────────────────────────────────────────────────────┘
```

**Design decision — KB structure:** Using 2 Knowledge Bases instead of 3 S3 layers in one KB. Amazon Connect now supports multiple KBs per agent (Nov 2025). This gives cleaner separation between internal program data (KB 1) and external community resources (KB 2). Content tag filtering within each KB enables further granularity (e.g., tag `program:thriveatwork` vs `program:utility-assistance` within KB 1).

---

## KB Content Ingestion Rules

Per the **Stability360 Knowledge Base Document Protocol & Governance**, only **Class A (Authoritative)** content is eligible for S3 ingestion. The following rules govern what goes into the Knowledge Base and what does not.

### What Goes INTO S3 (KB 1 — Programs & Rules)

| Content Type | Source | Example |
|---|---|---|
| AI-Approved program descriptions | Governance doc — "Description (AI-Approved)" sections | "Thrive@Work is a confidential way to connect employees to support..." |
| "What the Assistant CAN Say" phrases | Governance doc — per program | "I can help start the process to see what support may be available." |
| Eligible population definitions | Governance doc — per program | "Households experiencing utility-related financial hardship" |
| Geographic scope rules | Governance doc — per program | "Defined service area (zip code-based)" |
| Intake requirements (field lists) | Governance doc — per program | Utility type, provider, amount past due, shutoff status |
| Routing logic (referral vs direct support) | Governance doc — per program + Appendix B | "Utility Assistance is always treated as Direct Support" |
| Escalation thresholds | Governance doc — per program | "Imminent shutoff (within 72 hours) → immediate human escalation" |
| Closed-loop expectations | Governance doc — per program | "Follow-up continues until utility stability is achieved" |
| Referral vs Direct Support classification | Appendix B — all subcategories | Housing → Direct Support, Food → Referral, etc. |
| Global language guardrails (approved tone) | Governance doc — Global section | "Use conditional language (may, could, might)" |

### What Goes INTO S3 (KB 2 — 211 Resources)

| Content Type | Source | Example |
|---|---|---|
| Provider names and service descriptions | 211 data export | "Lowcountry Food Bank — Emergency food assistance" |
| Addresses, phone numbers, hours | 211 data export | Physical location, contact, operating hours |
| Geographic coverage (county/ZIP) | 211 data export | Berkeley, Charleston, Dorchester |
| Eligibility notes (if public) | 211 data export | "Open to all residents" |

### What Does NOT Go Into S3

| Content Type | Where It Goes Instead | Reason |
|---|---|---|
| "What the Assistant MUST NOT Say" phrases | **Guardrail word filters** (M6) | These are prohibitions, not content. Guardrails block them at runtime |
| Internal decision logic / routing algorithms | **Agent prompts** (M4) + **Contact flows** (M5) | Internal orchestration, not client-facing knowledge |
| Scoring formulas (Self-Sufficiency Matrix) | **Lambda function** (M3) | Math must be computed, not retrieved. LLMs unreliable for arithmetic |
| Class B documents (SOPs, training manuals) | **docs/ folder** (human reference only) | Protocol explicitly prohibits AI ingestion of Class B |
| Class C documents (partner websites, flyers) | **Not ingested anywhere** | Protocol: contextual only, never ingested |
| KB governance docs, source tracking table | **docs/ folder** (governance artifact) | Administrative, not client-facing |
| Employee IDs / employer data | **DynamoDB** (M2) | Structured lookup, not document retrieval |
| CharityTracker payload structure | **Lambda function** (M3) | Runtime construction, not static content |
| PRD, roadmap, architecture docs | **docs/ folder** (build reference) | SoftwareONE internal, not AI content |

### Ingestion Validation Checklist

Before any document is placed in S3:

1. Is it classified as **Class A** in the Source Tracking Table? → If no, **do not ingest**
2. Does it have a **named content owner**? → If no, **do not ingest** (No-Orphan-Content Rule)
3. Is it **mapped to a KB entry**? → If no, **do not ingest**
4. Does it contain only **AI-approved content** (descriptions, CAN say, eligibility, routing, escalation)? → If no, **extract only approved portions**
5. Does it contain any **MUST NOT say phrases**? → If yes, **route those to guardrail word filters instead**
6. Is it under **1 MB**? → If no, **split into smaller documents**

---

## Milestone 1: Knowledge Base Content & Structure

**Goal:** Build 2 S3-backed Knowledge Bases

### KB 1 — Programs & Rules (internal)

*Feasibility: NATIVE — S3 KB with metadata tags*

- Thrive@Work: program description, confidentiality rules, approved/prohibited language, routing logic. Tagged: `program:thriveatwork`
- Utility Assistance: eligibility, extended intake fields, priority escalation rules, approved/prohibited language. Tagged: `program:utility-assistance`
- Referrals – Light Touch: description, escalation thresholds, approved/prohibited language. Tagged: `program:referrals`
- Referral vs Direct Support classification for all subcategories (Appendix B)
- Eligibility sub-routing: ZIP → county → agency, age, children, military, employer
- Global language guardrails, escalation language templates, FAQ content
- **Format:** HTML or plain text files, max 1 MB each, total under 5 GB
- **Metadata:** Each document tagged by program, content type, and version

### KB 2 — 211 Community Resources (external)

*Feasibility: NATIVE — separate S3 KB*

- Berkeley, Charleston, Dorchester county resources
- Per resource: provider, service, address, phone, hours, geography, eligibility
- Chunked into documents by county or service category (stay under 1 MB per doc)
- Tagged by county and service type for filtered retrieval
- Serves as fallback when 211 API not configured

**KB Source Tracking Table** — Class A metadata per governance protocol

**Depends on:** TUW sign-off on KB v1, 211 data export availability

---

## Milestone 2: DynamoDB — Thrive@Work Employee Validation

**Goal:** Structured employee ID verification via Lambda MCP tool

*Feasibility: SUPPORTED — Lambda + DynamoDB, proven pattern per [AWS sample](https://github.com/build-on-aws/bedrock-agent-appointment-manager-dynamodb)*

### DynamoDB Table

- `Stability360-ThriveAtWork-Employees` (per environment)
- Schema: `employee_id` (PK), `employer_id`, `employer_name`, `partnership_status`, `eligible_programs`, `date_enrolled`

### Lambda MCP Tool

- Registered as MCP tool via flow module or AgentCore Gateway
- Input: employee_id → DynamoDB query → return match result
- **Must complete within 30 seconds** (MCP tool timeout)
- Response: `{ matched, employer_name, partnership_status, eligible_programs }`

### Validation Logic

- Not provided → prompt once → escalate (Tier 2)
- No match → escalate: "Employee ID not recognized"
- Match + ACTIVE → route to eligible programs
- Match + INACTIVE → escalate: "Partnership no longer active"

---

## Milestone 3: Data Resolver & Integration Lambdas

**Goal:** Pluggable retrieval — API-first, KB-fallback

*Feasibility: SUPPORTED — Lambda action groups can call any external API per [docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-action-add.html)*

### Resolver Lambda (MCP tool)

- Data source + query → check config → API or KB → standardized response
- Each call must complete within **30 seconds**
- Logs source used (API/KB/escalation)

### CharityTracker Payload Lambda (MCP tool)

- Builds structured payload from conversation session attributes
- Fields: client name, employee ID, employer, need, ZIP/county, intake responses, extended intake, conversation summary, escalation tier + reason, solution already provided (if Tier 3), timestamp
- Phase 0: calls SES to send email. When API available: calls CharityTracker API
- **SES call well within 30-second timeout**

### 211 Resolver

- If 211 API configured → call API → KB fallback on failure
- If no API → query KB 2 (211 resources) directly
- Filter by need category + county/ZIP using metadata tags

### Follow-up Scheduler Lambda (MCP tool)

- Creates a scheduled Task via [Tasks API](https://docs.aws.amazon.com/connect/latest/adminguide/tasks.html) for follow-up
- Or triggers Outbound Campaign for automated SMS/email follow-up
- Links back to original contactId for context chain

---

## Milestone 4: Prompt Engineering & Agent Behavior

**Goal:** Configure AI agents with Stability360 logic

*Feasibility: NATIVE — agent prompts are customizable per [docs](https://docs.aws.amazon.com/connect/latest/adminguide/create-ai-agents.html)*

### Agent Configuration

| Agent Type | Role | Prompts |
|---|---|---|
| **SELF_SERVICE** | Client-facing front door. Handles intake, general inquiries, referral delivery | Self-service answer generation, self-service pre-processing |
| **ORCHESTRATION** | Multi-step workflow conductor. Chains tools (DynamoDB, resolver, payload, scoring) | Orchestration prompt |
| **ANSWER_RECOMMENDATION** | Assists live agents post-escalation with KB-grounded suggestions | Intent labeling, query reformulation, answer generation |
| **NOTE_TAKING** | Generates structured notes from conversation for escalation handoff | Note-taking prompt |
| **CASE_SUMMARIZATION** | Summarizes cases spanning multiple interactions | Case summarization prompt |

### Self-Service Agent Prompts

- Resolution-first: answer from KB before considering escalation
- Tier 3 handling: ask reason → answer first if possible → respect choice
- Tone: calm, warm, plain language, conditional ("may," "could")
- Built-in tools: QUESTION, ESCALATION, CONVERSATION, COMPLETE, FOLLOW_UP_QUESTION
- Custom MCP tools: employee ID lookup, data resolver, payload builder, scoring calculator

### Design Decisions

**Multi-select workaround:** Since web chat doesn't support native multi-select, the AI will present need categories using **Quick Reply buttons** (up to 10 per message) and use **FOLLOW_UP_QUESTION** tool to ask "Are there any other areas you need help with?" iteratively until the client says no. This simulates multi-select through conversation turns.

**"Talk to a person":** Since the hosted widget has no persistent button, every AI response that presents options will include a "Talk to a person" Quick Reply option. The ESCALATION tool handles the handoff with full context.

---

## Milestone 5: Decision Engine — Contact Flows & Conversation Logic

**Goal:** Implement full intake skeleton via contact flows + AI agent orchestration

*Feasibility: NATIVE — contact flows support branching, Lambda invocation, attribute checks per [docs](https://docs.aws.amazon.com/connect/latest/adminguide/connect-contact-flows.html)*

### Node 1: Entry & Session Init

- Client initiates via chat widget (web or kiosk)
- Contact flow creates session, sets initial attributes
- Kiosk: no persistence. Web: persistent chat via SourceContactId

### Node 2: Identity & Consent

- AI asks name (optional), explains purpose
- FOLLOW_UP_QUESTION for consent
- Decline → ESCALATION tool or COMPLETE

### Node 3: Need Identification

- Quick Reply buttons for categories (split across 2 messages if needed — 10 item limit)
- FOLLOW_UP_QUESTION: "Any other areas?" → iterates until done
- "Other" → free text → AI classifies from KB context

### Node 4: Thrive@Work Gate

- If employer access → FOLLOW_UP_QUESTION for employee ID
- MCP tool → Lambda → DynamoDB lookup
- Result drives routing

### Node 5: Path Classification

- AI applies Appendix B rules from KB 1
- Sets session attributes: `support_path=referral` or `support_path=direct_support`
- Contact flow branches on these attributes

### Node 6: Core Intake

- Sequential FOLLOW_UP_QUESTION for each field
- ZIP → county derivation (Lambda MCP tool or KB lookup)
- Responses stored in session attributes

### Node 7: General Inquiry (Tier 1 — any time)

- AI queries KB → answers directly → conversation continues
- No escalation for informational questions

### Node 8A: Referral Path (Tier 1)

- MCP tool → resolver Lambda → 211 data (API or KB 2)
- AI formats and delivers referral info
- MCP tool → follow-up scheduler (Task or Outbound Campaign)
- **Referral display:** Rich text (bold provider name, address, phone) or Interactive Message Panel. Stay under 1,024 char text limit by splitting across messages if needed

### Node 8B: Direct Support

- Utility Assistance: extended intake via FOLLOW_UP_QUESTION → MCP tool → payload Lambda → SES email → Task for live agent scheduling
- All other: intake captured → payload Lambda → SES email → ESCALATION tool with full context

### Node 9: Tier 2 Escalation

- ESCALATION tool packages conversation context to human queue
- Contact flow routes to appropriate queue based on session attributes
- NOTE_TAKING agent generates structured handoff notes

### Node 10: Tier 3 Escalation

- Client requests human → AI asks reason via FOLLOW_UP_QUESTION
- If AI can answer from KB → provides answer → Quick Reply: "Did that help?" / "Still want a person"
- If still wants human or AI can't answer → ESCALATION tool
- If declines reason → ESCALATION tool to general queue

### Node 11: Self-Sufficiency Matrix (post-handoff)

- Live agent collects responses
- **Scoring via Lambda MCP tool** — NOT LLM arithmetic (LLMs unreliable for math per [AWS docs](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html))
- Lambda calculates: housing ratio, employment score, financial resilience score, composite
- Returns scores to agent workspace via ANSWER_RECOMMENDATION agent

### Node 12: Closed-Loop Follow-Up

- Outbound Campaigns: scheduled SMS or email follow-up per [docs](https://aws.amazon.com/connect/outbound/)
- Tasks API: scheduled follow-up task assigned to agent per [docs](https://docs.aws.amazon.com/connect/latest/adminguide/tasks.html)
- Event-triggered: if no response → create re-engagement campaign

### Node 13: Error Handling

- Resolver fails → KB fallback → if both fail → ESCALATION
- Lambda timeout (30s) → graceful message → ESCALATION
- Contact flow disconnect flow handles cleanup

---

## Milestone 6: Guardrails

**Goal:** Content, PII, language boundaries

*Feasibility: NATIVE — max 3 guardrails per instance per [docs](https://docs.aws.amazon.com/connect/latest/adminguide/create-ai-guardrails.html)*

**Design decision — 3 guardrail limit:** Consolidate all rules into 2-3 guardrails:

| Guardrail | Policies |
|---|---|
| **Guardrail 1: Content Safety** | Content filtering (hate, violence, sexual, insults, misconduct, prompt attacks), denied topics (legal advice, medical advice, financial advice, payment processing, eligibility determinations), word filters (profanity, prohibited phrases) |
| **Guardrail 2: PII & Privacy** | PII detection (email → anonymize, credit card → block, SSN → block), custom regex for employee ID masking in logs, data minimization enforcement |
| **Guardrail 3: Grounding & Language** | Contextual grounding (dev: 0.7, prod: 0.8), conditional language enforcement, blocked internal system references |

### Data Isolation

- KB 1 metadata tags prevent cross-program data leakage
- KB 2 (211) is separate KB — no Thrive@Work data can surface
- DynamoDB accessed only via Thrive@Work tool — not queryable from general conversation
- Kiosk sessions: auto-disconnect timeout clears state

---

## Milestone 7: Amazon Connect Chat Widget

**Goal:** Single widget — web and kiosk

*Feasibility: NATIVE — widget supports fullscreen, auto-launch, custom styling, timeout per [docs](https://docs.aws.amazon.com/connect/latest/adminguide/add-chat-to-website.html)*

### Web Configuration

- Embedded via JS snippet on website
- Responsive (min 300px width)
- Persistent chat enabled: store contactId → resume via SourceContactId
- Custom branding: TUW/Stability360 logo, colors, messaging

### Kiosk Configuration

- Same widget with:
  - `fullscreen.fullscreenOnLoad: true`
  - `skipIconButtonAndAutoLaunch: true`
  - Customer idle timeout: configurable (e.g., 5 min)
  - Customer auto-disconnect timeout: configurable (e.g., 2 min after idle)
- No persistent chat — each session is fresh
- Disconnect flow: "Your session has ended and your information has been securely submitted."

### Shared Configuration

- Interactive messages enabled: `application/vnd.amazonaws.connect.message.interactive`
- Rich text enabled: `text/markdown`
- Quick Reply with "Talk to a person" in every AI response

---

## Milestone 8: Testing & Validation

### Tier 1 Resolution Tests

- General inquiry → KB answer, no escalation
- 211 lookup → resolver returns results → delivered
- Eligibility pre-screen → conditional answer from KB
- Full referral path end-to-end
- Full Utility Assistance end-to-end
- Thrive@Work → DynamoDB → routing
- Mid-intake question → answered inline

### Tier 2 Escalation Tests

- Payment, determination, safety, advice, system failure, employee ID, out-of-scope → correct escalation with NOTE_TAKING output
- AI does NOT escalate when KB can answer

### Tier 3 Escalation Tests

- Reason + AI can answer → answer provided → "Still want a person?"
  - Yes → escalated with solution noted
  - No → continues (deflection)
- Reason + AI can't answer → escalated
- No reason → escalated to general queue

### Platform-Specific Tests

- MCP tool calls complete under 30 seconds
- Messages stay under 1,024 char (text) or 12,000 char (JSON)
- List Picker / Quick Reply within 10 item limit
- Guardrails fire correctly (all 3)
- KB retrieval uses correct metadata filters
- Persistent chat works on web (resume session)
- Kiosk auto-disconnect fires → data saved → session cleared
- Kiosk next user gets fresh session

### Scoring Tests

- Self-Sufficiency Matrix: Lambda calculates correctly (not LLM)
- Housing ratio, employment, financial resilience validated against Appendix C

### Edge Cases

- Client disengagement → partial data saved → follow-up Task created
- Out-of-service-area ZIP
- Iterative need selection (simulated multi-select)
- Resolver API + KB both fail → escalation
- Multiple Tier 3 requests in one session

### Success Metrics Baseline

- Tier 1 resolution rate
- Tier 2 / Tier 3 escalation rate by trigger
- Tier 3 deflection rate
- Intake completion rate
- Referral closed-loop rate
- Web vs kiosk usage
- MCP tool latency (within 30s budget)

---

## Milestone 9: UAT & Iteration

- TUW staff walkthrough of all three programs
- Thrive@Work with real employee IDs
- Coalition partner review: escalation context, NOTE_TAKING output quality
- Kiosk testing on physical device: fullscreen, timeout, isolation
- Client persona testing across all tiers
- KB content accuracy
- 211 data spot-check
- Email payload review
- Prompt tuning based on escalation data
- Iterate

---

## Execution Order

```
M1 (KB Content — 2 S3 KBs) ────────┐
                                    ├──→ M4 (Prompts) ──→ M5 (Decision Engine)
M2 (DynamoDB + Lambda MCP tool) ───┤                          │
                                    │                          │
M3 (Resolver + Payload + Follow-up  │                          │
    Lambda MCP tools) ──────────────┘                          │
                                                               │
M6 (Guardrails — 3 max) ←── continuous ───────────────────────┘
                                                               │
M7 (Chat Widget — web + kiosk) ←── parallel ──────────────────┘
                                                               │
                                              M8 (Testing) ←───┘
                                                   │
                                              M9 (UAT) ←───────┘
```

- **M1 + M2 + M3** in parallel
- **M4** depends on M1, M2, M3
- **M5** depends on M4
- **M6, M7** parallel with M5
- **M8** after M5, M6, M7
- **M9** after M8

---

## Open Questions (Need TUW Decisions)

| # | Question | Impact |
|---|----------|--------|
| 1 | Individual employee IDs or employer-level validation? | DynamoDB schema (M2) |
| 2 | 211 data format, export source, and size? | KB 2 structure — must stay under 5 GB / 1 MB per doc (M1) |
| 3 | 211 API available now or expected during Phase 0? | Resolver config (M3) |
| 4 | Email address for CharityTracker payloads? Per environment? | Payload Lambda config (M3) |
| 5 | Scheduling failure — no live agent, what happens? | Contact flow design (M5) |
| 6 | ZIP → county unreliable — separate county question? | Intake flow (M5) |
| 7 | Mixed referral + direct support — process order? | Path classification (M5) |
| 8 | Self-employed, retired, student, unable to work — routing? | Employment routing (M5) |
| 9 | Self-Sufficiency Matrix Score 5 (Financial Resilience) = Score 1 — doc error? | Scoring Lambda (M5) |
| 10 | Who receives escalations? Single queue or by type/reason? | Contact flow routing (M5) |
| 11 | Kiosk inactivity timeout duration? | Widget config — 2-480 min range (M7) |
| 12 | Kiosk device specs (screen size, touch)? | Widget UX (M7) |
| 13 | Which domains need allowlisting? (max 5) | Widget deployment (M7) |

---

## What the Prototype Delivers

- **Single interface:** Amazon Connect chat widget (web + kiosk fullscreen)
- **AI agents:** SELF_SERVICE + ORCHESTRATION for client-facing; ANSWER_RECOMMENDATION + NOTE_TAKING + CASE_SUMMARIZATION for agent-assist
- **Tier 1:** AI resolves general inquiries, referrals, Utility Assistance, Thrive@Work routing
- **Tier 2:** AI escalates what it cannot do — with full context via NOTE_TAKING
- **Tier 3:** Client requests human → ask reason → answer first if AI can → respect choice
- **2 Knowledge Bases:** Programs/rules (KB 1, tagged by program) + 211 resources (KB 2, tagged by county)
- **5 Lambda MCP tools:** Employee ID lookup, data resolver, CharityTracker payload, scoring calculator, follow-up scheduler
- **DynamoDB** for employee ID validation
- **3 Guardrails:** Content safety, PII/privacy, grounding/language
- **Automated follow-up** via Tasks API + Outbound Campaigns
- **Closed-loop tracking** via custom Lambda + Data Lake
- **Scoring** via Lambda (not LLM) for Self-Sufficiency Matrix
- **English only** (platform constraint for self-service)
- **Simulated multi-select** via iterative Quick Replies (platform constraint)
- **"Talk to a person"** as Quick Reply in every response (no persistent button in hosted widget)
