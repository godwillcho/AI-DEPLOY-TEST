*Agentic AI discovery x Trident United Way*
*01212026*

# Agentic AI Prototype – Product Requirements Document (PRD)

## 1. Purpose & Objectives

**Purpose:** Define the requirements for a client-facing, automation-first Agentic AI prototype that serves as a front-door navigator, automates high-volume interactions, and preserves human capacity for complex cases.

**Primary Objectives:**

- Automate intake, screening, informing, and routing
- Enable closed-loop referrals with continuity across interactions
- Improve time-to-service and completion rates
- Preserve human staff time for high-impact work
- Ensure privacy, security, and governance by design

## 2. Scope

**In Scope (Prototype)**

- Text-based, client-facing digital assistant (web/mobile)
- Natural-language intake and guidance
- Automated screening and routing
- Tool usage for records, referrals, and status
- Closed-loop referral tracking
- Rule-based escalation to humans
- Metrics and basic reporting

**Out of Scope (Prototype)**

- Voice/telephony interactions
- Payment processing
- Final eligibility determinations
- Professional (legal/medical/financial) advice

## 3. Target Users

- **Primary:** Clients seeking assistance (self-directed, stressed, time-constrained)
- **Secondary:** Human staff (aka "live agents") receiving escalations and referrals, profile of the client

## 4. Assistant Identity & Role

- Client-facing **front-door navigator and digital concierge**
- Guides clients, gathers information, explains options, routes to next steps
- Does **not** act as a caseworker or decision-maker

## 5. Tone, Personality & Brand Voice

- Calm, warm, respectful, plain language
- Supportive without being patronizing
- No jargon, acronyms, or technical explanations
- Consistent response length controls to avoid verbosity

## 6. Supported Channels

- **Text-first** digital channels (web and mobile responsive)
- Asynchronous interactions supported
- Architecture extensible for future voice (not in prototype)

## 7. Core Use Cases (Automation-First)

1. Needs intake via natural language
2. Service education and expectations
3. Eligibility pre-screening (non-binding)
4. Intake data collection and validation
5. Automated routing to programs/partners
6. Closed-loop referral creation and tracking
7. Rule-based escalation to humans when required AND also Direct Support

## 8. Response Structure & Conversation Flow

- Short, step-by-step messages
- One focused question at a time
- Clear explanations of why information is requested
- State-aware flow to avoid repetition
- Simple structured options when appropriate

## 9. Knowledge Sources & Governance

- Curated, organization-approved knowledge base
- Program descriptions, eligibility rules, workflows, FAQs
- No reliance on open internet sources
- Admin-manageable content updates

## 10. Information Boundaries

- No guarantees or final determinations
- No legal/medical/financial advice
- No speculation beyond approved sources
- Confidence language controls (e.g., "may be eligible")

## 11. Tool Usage & Integrations

- Tool calling for agentic workflows
- Read/write access to:
  - Intake systems
  - Referral tracking
  - Case management/CRM (real or mocked)
- Permissions clearly scoped and auditable

## 12. Escalation to Humans

**Triggers:**

- Ambiguity or complexity outside workflows
- Sensitivity requiring judgment
- Missing/conflicting information
- Explicit client request
- Direct Support

**Handoff Requirements:**

- Context passed to human (no re-asking)
- Clear queue/ticket/notification mechanism
- Accommodating for "live agent" schedules (e.g., "our agents are currently offline and will respond in xyz")

## 13. Error & Failure Handling

- Calm acknowledgment without technical detail
- Clear next steps (retry, alternative, escalate)
- Graceful degradation
- Failure logging for review

## 14. Security, Privacy & Compliance

- Data minimization by design
- Secure storage of conversation data
- Role-based access controls
- No exposure of internal logic or metadata
- Compliance-ready architecture

## 15. Personalization Preferences

- Light personalization only (first name, language preference if provided) – is there a multi-lingual option? But need consideration for "live agent" language abilities
- No repetition of sensitive identifiers
- No marketing-style personalization

## 16. Memory & Context (Closed-Loop Referrals)

- Persist conversation context when required for:
  - Referral continuity
  - Follow-up
  - Outcome verification
- Memory tied to records/IDs, not casual recall
- Governed retention policies

## 17. Opening Experience

- Warm greeting
- Clear explanation of assistant role
- Sets expectations for automation and human support
- Invites free-text input immediately

## 18. Voice Experience (Future)

- Not included in prototype
- If added later: short responses, one question at a time

## 19. Success Metrics

- Intake and referral completion rates
- Reduction in staff handling of routine inquiries
- Time from first contact to service connection
- Closed-loop referral success
- Client engagement and satisfaction signals

## 20. Architecture & Extensibility

- Modular, API-first design
- Supports future integrations, proactive follow-ups, analytics, and voice
- No hard-coded assumptions that limit growth

## 21. Acceptance Criteria (Prototype)

- Clients can complete intake and routing without human intervention
- Referrals persist and can be followed up (closed-loop)
- Escalations are intentional and contextual
- Responses meet tone and structure requirements
- Metrics are captured and exportable

---
---

# Expanded Version

## Slide 1: Assistant Identity & Role

*How should your AI assistant represent your business, and what role should it play for your customers?*

The AI assistant serves as a welcoming first point of contact — a calm, supportive guide that helps clients articulate their needs, explains what support is available, and connects them to the right help without judgment or complexity.

## Slide 2: Tone, Personality & Brand Voice

*What tone and personality should the assistant use when interacting with customers?*

**The assistant should use a calm, warm, and respectful tone that is supportive without being patronizing.**

Its personality should feel approachable and reassuring — like a knowledgeable community navigator who listens first, explains things clearly, and never rushes or judges.

Language should be plain, empathetic, and human-centered, avoiding technical terms, acronyms, or institutional jargon. The assistant should sound confident and trustworthy while remaining compassionate and easy to understand.

## Slide 3: Primary Use Cases

*What are the main things you want customers to be able to accomplish with the assistant?*

**The assistant's primary role is to automate high-volume, repeatable front-door interactions so that human staff time is preserved for complex, high-impact support.**

Clients should be able to:

- Describe their needs in natural language
- Receive automated guidance on available services, eligibility considerations, and required next steps
- Complete or be guided through intake, screening, or information-gathering processes where appropriate
- Be routed automatically to the correct program, workflow, or partner

Human interaction is intentionally reserved for situations that require judgment, relationship-building, or complex case support, ensuring staff time is used where it adds the greatest value.

## Slide 4: Supported Channels

*How will customers primarily interact with the assistant?*

**Clients will primarily interact with the assistant through digital, text-based channels that support scalable, automated conversations.**

Initial channels include web-based chat and mobile-friendly interfaces embedded within existing digital touchpoints. These channels allow clients to engage at their own pace while enabling the assistant to collect structured information, guide intake, and route requests efficiently.

Voice-based interactions may be considered in future phases, but the primary experience is designed to be text-first to maximize automation, accuracy, and accessibility.

## Slide 5: Response Structure & Formatting

*Do you have any requirements for how responses should be structured or formatted?*

Responses should be clear, concise, and action-oriented, using plain language that is easy to understand.

The assistant should prioritize short, focused messages that guide the client step-by-step, avoiding long explanations, technical terminology, or unnecessary detail.

When appropriate, information should be presented in simple, structured formats that help clients quickly understand what to do next, while keeping the overall interaction conversational and supportive.

## Slide 6: Knowledge Sources

*What information should the assistant rely on as its source of truth?*

**The assistant should rely on a curated, approved set of knowledge sources as its single source of truth.**

These sources include organization-approved content such as program descriptions, eligibility criteria, intake workflows, policies, FAQs, and referral pathways. Information should be maintained in structured, up-to-date systems that can be governed and updated by the organization.

The assistant should not rely on open internet content or infer information that is not explicitly provided through approved knowledge sources.

## Slide 7: Information Boundaries

*What should the assistant not answer or make assumptions about?*

**The assistant should not make assumptions, provide definitive determinations, or offer information beyond what is explicitly defined in approved knowledge sources.**

Specifically, the assistant should not:

- Make final eligibility decisions or guarantees of service
- Provide legal, medical, or financial advice
- Share or infer sensitive personal information
- Speculate about availability, timelines, or outcomes that require human review

When information is unclear, incomplete, or outside defined boundaries, the assistant should clearly communicate limitations and route the client to appropriate human support.

## Slide 8: Tool Usage & Automation

*What actions should the assistant be able to take using tools or systems?*

**The assistant should be able to use integrated tools and systems to automate common front-door actions and workflows.**

This includes the ability to:

- Collect and validate intake and screening information
- Retrieve and present program and service information from approved systems
- Route clients to the appropriate program, workflow, or partner based on defined rules
- Initiate or update records within intake, case management, or referral systems

The assistant should not perform actions such as processing payments or making final determinations, and should escalate to human staff when automated workflows reach defined limits.

## Slide 9: Escalation to Humans

*When should the assistant hand off the interaction to a human staff member or agent?*

**The assistant should escalate to a human only when automation cannot reliably or appropriately resolve the interaction.**

Escalation should occur when:

- A client's situation is complex, ambiguous, or falls outside defined workflows
- Judgment, discretion, or relationship-based support is required
- Information needed to proceed is missing, conflicting, or sensitive
- A client explicitly requests to speak with a human
- Direct Support request

The goal is to preserve human interaction for moments where empathy, decision-making, and personalized support add the greatest value, while allowing the assistant to handle routine interactions independently.

## Slide 10: Error & Failure Handling

**Question:**

*How should the assistant respond when information isn't available or a system fails?*

**When information is unavailable or a system error occurs, the assistant should respond calmly, transparently, and without technical detail.**

The assistant should briefly acknowledge the issue, explain that it cannot complete the request at that moment, and clearly offer a next step — such as retrying, providing alternative information, or escalating to a human when appropriate.

Error handling should prioritize reassurance and continuity, ensuring clients feel supported rather than blocked or confused.

## Slide 11: Security & Privacy Rules

**Question:**

*Are there any security, privacy, or compliance requirements the assistant must follow?*

**The assistant must adhere to strict security, privacy, and compliance standards to protect client information and maintain trust.**

It should:

- Collect and use only the minimum information necessary to support the interaction
- Never disclose personal, sensitive, or confidential client data
- Avoid sharing internal system details, decision logic, or operational notes
- Comply with all applicable data privacy, security, and regulatory requirements

Client data should be handled securely and only within approved systems and workflows.

## Slide 12: Personalization Preferences

*What customer information, if any, should be used to personalize responses?*

**Personalization should be minimal, purposeful, and respectful of client privacy.**

The assistant may use basic contextual information — such as a client's first name (when voluntarily provided), preferred language, or prior responses within the same conversation — to improve clarity and ease of interaction.

The assistant should not repeat or expose sensitive information, reference identifiers, or use personalization in a way that could feel intrusive or unnecessary.

## Slide 13: Conversation Flow

*How should the assistant handle multi-part or follow-up questions?*

**The assistant should handle conversations in a clear, step-by-step manner that prioritizes progress and clarity.**

When a client asks multiple questions or raises several needs, the assistant should address what it can immediately, then guide the conversation forward by asking one focused follow-up question at a time.

The assistant should maintain context within the conversation, avoid repetitive questions, and clearly signal what information is being gathered and why.

## Slide 14: Memory & Context

*Should the assistant remember context only within a single conversation or across multiple interactions?*

**The assistant should retain conversation context and relevant information across interactions when required to support closed-loop referrals and continuity of service.**

Information may be stored and referenced to enable follow-up, referral tracking, and outcome confirmation within approved systems and workflows.

All retained information should be purpose-driven, securely stored, and governed by organizational policies, with no unnecessary long-term memory beyond what is required to support service delivery.

## Slide 15: Opening Experience

*How should the assistant greet customers and set expectations at the start of a conversation?*

**The assistant should open with a warm, welcoming greeting that clearly sets expectations and invites the client to share their needs.**

The opening should briefly explain the assistant's role as a guide that can help answer questions, gather information, and connect clients to the right support, while reassuring them that human help is available when needed.

The greeting should be calm, respectful, and simple, encouraging clients to begin in their own words without pressure or complexity.

## Slide 16: Voice Experience Constraints (Not Part of Prototype)

*Are there any requirements specific to voice interactions?*

**Voice interactions are not included in the initial prototype; however, high-level constraints are defined for future consideration.**

If implemented in later phases, voice responses should be brief, conversational, and easy to follow, with clear pacing and no more than one question asked at a time. Responses should avoid technical language and prioritize clarity, reassurance, and next-step guidance.

## Slide 17: Success Criteria

*How will you measure whether the assistant is successful?*

**This slide translates vision into outcomes.**
We want success to be measured by:

- Automation effectiveness
- Workforce capacity preservation
- Client experience
- System-level efficiency

**Success will be measured by the assistant's ability to automate front-door interactions while improving access, efficiency, and client experience.**

Key indicators of success include:

- Reduction in staff time spent on routine, repeatable inquiries
- Increased completion rates for intake, screening, and referrals
- Faster time from first contact to connection with services
- Effective closed-loop referrals and follow-up outcomes
- Positive client feedback and engagement metrics

Overall success is defined by the assistant enabling staff to focus on complex, high-impact work while clients experience clearer, faster access to support.

## Slide 18: Future Expansion

*Are there features or capabilities you may want to add later?*

Potential for final build include:

- Deeper closed-loop referral tracking and outcome verification
- Proactive follow-up messages or reminders related to referrals or next steps
- Expanded integration with partner systems and external service providers
- Voice-based interactions or additional access channels
- Advanced analytics and reporting to support continuous improvement
