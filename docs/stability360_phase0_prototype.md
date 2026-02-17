Stability360 - Phase 0 Prototype
Trident United Way
Date: January 22, 2026

# Stability360 — Phase 0 Prototype

## Purpose of this Pre-Read

This document provides shared context and guardrails for the Phase 0 Stability360 prototype. It is intended to align Trident United Way, SoftwareONE, and AWS on scope, content, and decision boundaries before deep technical implementation discussions.

Phase 0 is intentionally designed to validate logic, automation, integrations, and closed-loop workflows using a limited set of programs, rather than representing full production scale.

## 1. What We Are Building in Phase 0

The Phase 0 prototype is a **client-facing, automation-first Agentic AI assistant** that:

- Serves as a front-door navigator for Stability360
- Automates intake, screening, routing, and referrals
- Preserves human staff time for complex, high-impact cases
- Enables closed-loop referral tracking across systems

The prototype is not intended to cover all programs or channels. It is a **representative vertical slice** to prove the model.

## 2. Programs in Scope (Authoritative)

For Phase 0, the assistant will operate on **three defined programs only**, governed by the Stability360 Knowledge Base v1.

### Program 1: Thrive@Work

- **Type:** Access model / direct support entry point
- **Purpose:** Employer-based access to Stability360 services
- **Behavior:** Routes employees into direct support workflows; light-touch referrals only when appropriate

### Program 2: Referrals — Light Touch (211 + Partner Network)

- **Type:** Self-directed referrals
- **Purpose:** Provide community resource information without case management
- **Behavior:** Uses 211 APIs for service discovery + KB for partner network; supports follow-up and escalation when needed

### Program 3: Utility Assistance

- **Type:** Direct Support
- **Purpose:** Case-managed support for households experiencing utility-related financial hardship
- **Behavior:** Extended intake, priority escalation, and closed-loop follow-up

Any program not explicitly defined above is **out of scope** for the Phase 0 prototype.

## 3. Knowledge Base as Source of Truth

The Stability360 Knowledge Base v1 is the **authoritative source of truth** for:

- What the assistant can say and recommend
- Routing and escalation logic
- Eligibility phrasing and language guardrails
- Integration field definitions

All prototype workflows, integrations, and agent behaviors must map directly to the Knowledge Base. Expansion of scope requires an approved KB update.

## 4. Role of 211 in Phase 0

211 remains a critical partner in the Stability360 ecosystem and is positioned in Phase 0 as:

- **A referral execution and service-discovery layer**
- Accessed via APIs
- Queried after intent and eligibility logic are applied

The Agentic AI and centralized Knowledge Lake retain responsibility for:

- Intake logic
- Orchestration
- Data persistence
- Closed-loop outcome tracking

## 5. What Is Intentionally Out of Scope

To maintain focus and velocity, the following are **not included** in Phase 0:

- Voice or telephony interactions
- Payment processing
- Final eligibility determinations
- Full program catalog coverage
- Advanced reporting dashboards
- Go-live or production readiness decisions

## 6. Decisions We Aim to Make in Phase 0

Phase 0 discussions should focus on:

- Validation of intake and routing logic
- Alignment on Knowledge Base structure and mappings
- Confirmation of integration touchpoints (CharityTracker, 211 APIs)
- Definition of success metrics for the prototype

Items such as UAT plans, go-live criteria, and production SLAs will be addressed in later phases.

## 7. Success Criteria for Phase 0

Phase 0 will be considered successful if the prototype demonstrates:

- End-to-end automated intake and routing for in-scope programs
- Correct use of referral vs direct support paths
- Effective escalation to humans when required
- Closed-loop referral tracking and follow-up
- A clear, dignified client experience
