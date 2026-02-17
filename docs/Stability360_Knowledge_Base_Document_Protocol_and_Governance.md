# Stability360 Knowledge Base – Document Protocol & Governance

**Trident United Way**
**Date: January 22, 2026**

---

## Purpose

This protocol defines how documents are selected, governed, and used within the Stability360 Knowledge Base (KB). Its goal is to ensure the Agentic AI operates only on **accurate, approved, and current information**, while remaining lightweight enough to support rapid iteration during Phase 0.

This protocol applies to all content used to inform AI behavior, routing logic, and client-facing responses.

---

## 1. Knowledge Base Document Classes

All documents fall into one of the following three classes. Only **Class A** documents are eligible for ingestion into the Knowledge Base.

### Class A — Authoritative (KB-Eligible)

**Used directly by the Agentic AI**

Examples:

- Program descriptions and service definitions
- Eligibility rules and constraints
- Intake and screening logic
- Referral vs Direct Support rules
- Escalation thresholds
- Approved language guardrails

**Requirements:**

- Explicitly approved for AI use
- Versioned
- Has a named content owner
- Mapped to at least one KB entry

### Class B — Reference (Human-Only)

**Used by staff; not ingested by the AI**

Examples:

- Internal policies and procedures
- Staff training manuals
- Grant proposals and narratives
- Internal SOPs and playbooks

**Rules:**

- May inform Class A content
- Must not be ingested directly into the AI
- No requirement for version alignment with KB

### Class C — Informational / External

**Contextual only; never ingested**

Examples:

- Partner websites
- External PDFs and flyers
- Email communications
- Public web content

**Rules:**

- Used for validation or background only
- Never ingested into the Knowledge Base

---

## 2. Source Attribution & Traceability Rules

Every KB entry must have traceable source documentation.

**Required Metadata for Each KB Entry:**

- **KB Entry Name**
- **Source Document(s)** (Class A only)
- **Document Version**
- **Last Reviewed Date**
- **Content Owner**

This information is used for internal governance and auditability and is not exposed to clients.

---

## 3. Update Cadence & Change Management

**Standard Review Cycle**

- Knowledge Base reviewed every **60–90 days** during Phase 0

**Immediate Updates Required When:**

- Eligibility rules change
- Funding requirements change
- Partner availability materially shifts
- Language or compliance risks are identified

**Change Rules**

- Updates are proposed by Trident United Way
- Changes are reviewed for:
  - Client experience impact
  - Automation feasibility
  - Privacy and compliance alignment
- Approved updates are versioned before activation

---

## 4. Ownership & Accountability

Each KB entry must have a designated **Content Owner**, responsible for:

- Accuracy of information
- Timely updates when changes occur
- Coordinating approvals when required

Entries without an owner are considered **out of scope** and must not be ingested.

---

## 5. No-Orphan-Content Rule

Any document that:

- Is not mapped to a KB entry, or
- Does not have a named owner

is **not eligible** for Knowledge Base ingestion.

This rule prevents outdated, ambiguous, or unsupported content from influencing AI behavior.

---

## 6. SoftwareONE Integration Expectations

- SoftwareONE must ingest **only Class A documents** mapped to KB entries
- All AI responses, routing logic, and integrations must reference KB-defined fields
- Any proposed ingestion of new documents requires TUW approval and classification

This protocol is intentionally lightweight and designed to evolve as Stability360 scales beyond Phase 0.

---
---

# Stability360 Knowledge Base – Source Tracking Table (Template)

## Purpose

This table is used to track and govern all documents that inform the Stability360 Knowledge Base (KB). It ensures traceability, accountability, and alignment with the KB Document Protocol.

Only **Class A (Authoritative)** documents listed here are eligible for AI ingestion.

---

## KB Source Tracking Table (Template)

| KB Entry Name | Program / Area | Document Class | Source Document Title | Document Version | Last Reviewed | Content Owner | AI-Eligible (Y/N) | Notes |
|---|---|---|---|---|---|---|---|---|
| Thrive@Work – Access Model | Thrive@Work | Class A | Thrive@Work Program Overview | v1.0 | 01/2026 | Community Impact | Y | Employer-based access and direct support entry |
| Utility Assistance – Direct Support | Utilities | Class A | Utility Assistance Program Guidelines | v1.2 | 01/2026 | Community Impact | Y | Includes shutoff escalation rules |
| Referrals – Light Touch | Referrals | Class A | Referral & Partner Resource Rules | v1.0 | 01/2026 | 211 / Community Impact | Y | 211 API-driven referrals |
| Staff Intake SOP | Operations | Class B | Intake & Case Management SOP | v3.4 | 11/2025 | Operations | N | Reference only; not AI-ingested |
| Partner Website | External | Class C | Partner Public Website | N/A | N/A | External | N | Informational only |

---

## Instructions for Use

1. Every Knowledge Base entry must map to at least one **Class A** source document listed in this table.
2. Each row must have a named **Content Owner** responsible for accuracy and updates.
3. Update the **Last Reviewed** date whenever content is validated or revised.
4. Mark AI-Eligible = Y only for Class A documents approved for ingestion.
5. Documents without an entry in this table must not be ingested into the Knowledge Base.

## Governance Notes

- This table should be reviewed during each KB version update.
- Historical versions of this table should be retained for auditability.
- SoftwareONE may reference this table to confirm ingestion eligibility but may not add or modify entries without TUW approval.

This table is a governance artifact and is not client-facing.

---
---

# Stability360 Phase 0 – End-to-End Architecture & Content Flow

## Purpose

This description explains how documents, knowledge, AI, partners (including 211), and outcomes connect in the Stability360 Phase 0 prototype.

---

## High-Level Flow

### 1. Authoritative Documents (Inputs)

**Class A – Approved Source Documents**

- Thrive@Work Program Overview
- Utility Assistance Program Guidelines
- Referral & Partner Resource Rules

Governed by:

- KB Document Protocol
- Source Tracking Table

*(Structured extraction)*

### 2. Stability360 Knowledge Base (Source of Truth)

The Knowledge Base translates documents into **structured, machine-readable rules**:

- Program definitions
- Eligibility logic (soft / hard)
- Referral vs Direct Support flags
- Escalation thresholds
- Approved language guardrails

Only content defined here is visible to the AI.

*(Runtime orchestration)*

### 3. Agentic AI Assistant (Front Door)

Client-facing, text-based assistant that:

- Collects intake information
- Identifies needs
- Applies KB rules
- Automates routing and referrals
- Escalates to humans when required

The assistant does not make final decisions or guarantees.

*(Two primary paths)*

### 4A. Referral Path – Light Touch

**Self-Directed Support**

- AI invokes 211 APIs for service discovery
- Filters by geography and need
- Delivers referral information to client
- Records referral in Knowledge Lake

*(Follow-up)*

### 4B. Direct Support Path

**Case-Managed Support**

- Extended intake
- Case creation in CharityTracker
- Human specialist engagement
- Priority escalation when needed

*(Outcome tracking)*

### 5. Knowledge Lake & CRM Systems

Centralized data layer that:

- Stores intake and referral records
- Syncs with CharityTracker
- Receives outcome updates from humans and partners
- Supports closed-loop referrals

*(Feedback loop)*

### 6. Closed-Loop Outcomes & Learning

- Referral success or failure recorded
- Direct support outcomes tracked
- Data used for:
  - Follow-up automation
  - Trend analysis
  - Continuous improvement

---

## Key Design Principles

**Knowledge Base governs behavior (not raw documents)**

- 211 is a referral execution layer, not the front door
- Automation first, human where it matters
- Closed-loop outcomes are required
- Scope is intentionally limited for Phase 0

---
---

# Stability360 Knowledge Base v1 – Prototype Programs

**Purpose:** This document defines the **only programs the Agentic AI prototype is allowed to know, reference, and operate on** in Phase 0. These entries are authoritative and govern AI behavior, routing, escalation, and language.

**Programs in Scope (Prototype v1):**

1. Thrive@Work (Employer-based access)
2. Referrals – Light Touch (211 + Partner Network)
3. Utility Assistance (Direct Support)

---

## Program 1: Thrive@Work

**Program Type**

- **Access Model / Direct Support Entry Point**

**Support Path**

- **Direct Support (Primary)**
- May route to light-touch referrals only when appropriate

**Description (AI-Approved)**

Thrive@Work is an employer-based access model that connects employees to direct support when they are experiencing temporary challenges. Through Thrive@Work, individuals can confidentially engage with Stability360 to identify needs, complete intake, and be connected to appropriate direct support services.

**Eligible Population**

- Employees of participating Thrive@Work employers

**Geographic Scope**

- Defined by employer participation and underlying program service areas

**Intake Requirements**

- Confirmation of employer participation (self-reported)
- Identification of needs using standard intake categories
- Contact preferences and availability

**Routing Logic**

- Thrive@Work serves as an **entry point**, not a standalone service
- Identified needs are routed to:
  - **Utility Assistance (Direct Support)** when financial hardship is disclosed
  - **Referral – Light Touch** only when needs are informational or self-directed

**Escalation Rules**

- Employer participation unclear
- Financial hardship disclosed
- Multiple or complex needs identified
- Client requests human support

**Closed-Loop Expectations**

- All Thrive@Work interactions result in a tracked outcome
- Follow-up is required until the identified need is resolved or transitioned

**What the Assistant CAN Say**

- "Thrive@Work is a confidential way to connect employees to support."
- "I can help you get started and connect you with the right specialist."

**What the Assistant MUST NOT Say**

- "Your employer will be notified."
- "This is an employee assistance program (EAP)."
- "You are guaranteed assistance."

---

## Program 2: Referrals – Light Touch (211 + Partner Network)

**Program Type**

- **Referral / Self-Directed Support**

**Support Path**

- **Referral Only (Light Touch)**

**Description (AI-Approved)**

Referrals – Light Touch connects individuals to community resources they can access directly without case management. This pathway is designed for informational needs or services that clients are able to pursue independently, while still enabling follow-up and outcome tracking.

**Eligible Population**

- Open to all individuals seeking information or self-directed support

**Geographic Scope**

- Derived from ZIP code

**Intake Requirements**

- ZIP code
- Primary need category
- Optional context provided by the client

**Routing Logic**

- Match client needs and geography using the Knowledge Lake
- **Invoke 211 APIs** to retrieve eligible services and partner resources
- Filter results based on service type and location
- Deliver referral information directly to the client
- Persist referral data to the Knowledge Lake

**Escalation Thresholds**

- Client requests help navigating the referral
- Multiple unmet needs detected
- Referral information unavailable, outdated, or unclear
- Client expresses confusion, distress, or inability to self-navigate

**Closed-Loop Expectations**

- Automated follow-up message sent to confirm whether the referral was helpful
- Client response (or lack thereof) recorded as an outcome signal
- If referral is unsuccessful or need persists → offer Direct Support

**What the Assistant CAN Say**

- "Here are some resources you can contact directly."
- "These organizations may be able to help with this type of need."
- "If you'd like more help, I can connect you with a specialist."

**What the Assistant MUST NOT Say**

- "This provider will help you."
- "This service has confirmed availability."
- "You do not qualify for other support."

---

## Program 3: Utility Assistance

**Program Type**

- **Direct Support Program**

**Support Path**

- **Direct Support (Live Agent Involvement Required)**

**Description (AI-Approved)**

Utility Assistance provides direct, case-managed support to households experiencing difficulty paying essential utility bills. The program helps stabilize households by coordinating financial assistance, negotiating timelines when appropriate, and connecting clients to longer-term solutions.

**Eligible Population**

- Households experiencing utility-related financial hardship

**Geographic Scope**

- Defined service area (zip code-based)

**Intake Requirements**

- Utility type (electric, gas, water)
- Utility provider
- Amount past due
- Shutoff status (current, pending, disconnected)
- Household income (self-reported)
- Household size

**Routing Logic**

- Utility Assistance is always treated as **Direct Support**
- Trigger extended intake and case creation
- Schedule appointment with a live agent
- Persist intake data to CRM and Knowledge Lake

**Escalation Rules (Priority)**

- **Imminent shutoff (within 72 hours)** → immediate human escalation
- Utility already disconnected → priority routing
- Conflicting or missing information → human review
- Client distress or safety concerns → immediate escalation

**Closed-Loop Expectations**

- Case manager confirms assistance outcome
- Status updates recorded (paid, deferred, denied, referred)
- Follow-up continues until utility stability is achieved or next step is defined

**What the Assistant CAN Say**

- "I can help start the process to see what support may be available."
- "A specialist will review this with you and follow up."
- "If your service is at risk of being shut off soon, I can flag this for urgent review."

**What the Assistant MUST NOT Say**

- "Your bill will be paid."
- "You qualify for assistance."
- "We can guarantee service will be restored."

---

## Global Language Guardrails (Applies to All Programs)

- Use conditional language ("may," "could," "might")
- Avoid guarantees or promises
- Do not reference internal systems or decision logic
- Maintain calm, respectful tone

---
---

# Stability360: Knowledge Base Governance, Versioning & Control

## Purpose

The Stability360 Knowledge Base (KB) is the **authoritative source of truth** for what the Agentic AI can say, recommend, and do. All assistant behavior, routing logic, escalation rules, and integrations must align to the KB.

## Scope Control (Phase 0)

- Only programs explicitly defined in this document are in scope for the prototype
- The assistant must not reference services, programs, or rules outside the KB
- Any expansion of scope requires an approved KB update

## Versioning

- KB versions will be clearly labeled (e.g., v1.0, v1.1)
- Changes between versions must be documented (additions, removals, logic changes)
- Prototype builds must reference a specific KB version

## Update & Approval Process

- KB updates are proposed by Trident United Way
- Updates are reviewed for:
  - Client experience impact
  - Automation feasibility
  - Privacy and compliance alignment
- Approved updates are published before being enabled in the assistant

## Integration Alignment

- All system integrations (e.g., CharityTracker, 211 APIs) must map to KB-defined fields and rules
- The KB remains the system of record for program definitions and routing logic

## Auditability & Governance

- KB changes must be traceable and auditable
- Historical versions must be retained for reference and reporting
