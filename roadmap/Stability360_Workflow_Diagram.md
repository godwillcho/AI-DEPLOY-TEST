# Stability360 Phase 0 — Conversation Workflow

---

## Complete Flow

```
CLIENT ENTERS
(Web Chat Widget or Kiosk Fullscreen)
    |
    v
+------------------------------------------+
|  NODE 1: Entry & Session Init            |
|  [Connect Contact Flow]                  |
|                                          |
|  - Create session                        |
|  - Set initial attributes                |
|  - Web: persistent chat enabled          |
|  - Kiosk: fresh session, no persistence  |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  NODE 2: Identity & Consent              |
|  [KB 1 + Agent Prompt]                   |
|                                          |
|  AI: "Hello! I'm here to help connect   |
|  you with support. Could you share your  |
|  first name? (This is optional.)"        |
|                                          |
|  AI explains role + data use from KB 1   |
+------------------------------------------+
    |
    +------ Client declines -------> ESCALATION or COMPLETE
    |
    v (Client continues)
+------------------------------------------+
|  NODE 3: Need Identification             |
|  [KB 1 + Quick Replies]                  |
|                                          |
|  AI: "How can I help you today?"         |
|                                          |
|  Quick Reply buttons (max 10 per msg):   |
|  [Housing] [Transportation] [Food]       |
|  [Health] [Child Care] [Disaster]        |
|  [Employment] [Legal Aid] [Financial]    |
|  [Hygiene] [Other]                       |
|                                          |
|  Client selects --> subcategories shown  |
|  AI: "Are there any other areas you      |
|       need help with?"                   |
|  (iterates until client says no)         |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  NODE 4: Thrive@Work Gate                |
|  [Agent Prompt]                          |
|                                          |
|  AI: "Are you connecting through an      |
|  employer partnership program?"          |
|                                          |
|  [Yes] [No] [Talk to a person]           |
+------------------------------------------+
    |                       |
    | Yes                   | No
    v                       |
+---------------------------+              |
|  EMPLOYEE ID VALIDATION   |              |
|  >>> MCP TOOL 1 <<<       |              |
|  [Lambda -> DynamoDB]     |              |
|                           |              |
|  AI: "Please enter your   |              |
|  employee ID."            |              |
|                           |              |
|  +---------------------+ |              |
|  | DynamoDB Lookup      | |              |
|  | employee_id -> match | |              |
|  +---------------------+ |              |
|       |          |        |              |
|    ACTIVE     NO MATCH/   |              |
|       |      INACTIVE     |              |
|       |          |        |              |
|       |     ESCALATE      |              |
|       |     (Tier 2)      |              |
|       v                   |              |
|  Session gets:            |              |
|  - employer_name          |              |
|  - eligible_programs      |              |
|  - employee_id            |              |
|  (carried through all     |              |
|   remaining nodes)        |              |
+---------------------------+              |
    |                                      |
    +<-------------------------------------+
    |
    | (Both paths merge — employee has full KB access)
    v
+------------------------------------------+
|  NODE 5: Path Classification             |
|  [KB 1 — Appendix B rules]              |
|                                          |
|  For EACH selected subcategory:          |
|                                          |
|  KB 1 lookup: subcategory --> path       |
|                                          |
|  Examples from Appendix B:               |
|  - Food Pantries --> REFERRAL            |
|  - SNAP Assistance --> DIRECT SUPPORT    |
|  - Shelter --> DIRECT SUPPORT            |
|  - Bus Tickets --> REFERRAL              |
|  - Rental Assistance --> DIRECT SUPPORT  |
|  - Dental Appointments --> REFERRAL      |
|                                          |
|  Session attribute set:                  |
|  support_path = referral | direct_support|
+------------------------------------------+
    |
    v
+------------------------------------------+
|  NODE 6: Core Intake                     |
|  [KB 1 + Session Attributes]             |
|                                          |
|  AI asks one question at a time:         |
|                                          |
|  1. "What ZIP code do you live in?"      |
|     --> derive county                    |
|     --> agency routing (KB 1):           |
|        Berkeley -> Santee Cooper/BRCC    |
|        Charleston -> NCRCC/CRCC          |
|        Dorchester -> DRCC                |
|                                          |
|  2. "How would you like to be            |
|      contacted?"                         |
|     [Call] [Text] [Email]                |
|                                          |
|  3. "Which days are you available?"      |
|                                          |
|  4. "What times work best?"             |
|                                          |
|  5. "What is your age?"                 |
|     --> 65+ = eligible for BCDCOG (KB 1)|
|                                          |
|  6. "Do you have children under 18?"    |
|     --> Yes = eligible Siemer (KB 1)     |
|                                          |
|  7. "Current employment status?"         |
|     --> Routing from KB 1                |
|                                          |
|  8. "Military or service affiliation?"   |
|     --> Veteran/Active = Mission United  |
|        (KB 1)                            |
|                                          |
|  9. "Current public assistance?"         |
|     [SNAP] [WIC] [TANF] [Medicaid]      |
|     [SSI/SSDI] [None] [Other]           |
|                                          |
|  All answers stored in session attributes|
+------------------------------------------+
    |
    |  +-----------------------------------------------+
    |  | NODE 7: General Inquiry (available ANY TIME)   |
    |  | [KB 1 — RAG retrieval]                         |
    |  |                                                |
    |  | Client can ask questions at any point:         |
    |  |                                                |
    |  | "What is Stability360?"     --> KB 1 answers   |
    |  | "Do you serve my county?"   --> KB 1 answers   |
    |  | "What do I need to bring?"  --> KB 1 answers   |
    |  | "What happens after this?"  --> KB 1 answers   |
    |  |                                                |
    |  | AI answers directly, then returns to flow.     |
    |  | No escalation. No MCP tool.                    |
    |  +-----------------------------------------------+
    |
    v
+------------------------------------------+
|  PATH SPLIT                              |
|  (Based on Node 5 classification)        |
+------------------------------------------+
    |                          |
    | REFERRAL                 | DIRECT SUPPORT
    v                          v
+---------------------+    +---------------------------+
| NODE 8A:            |    | NODE 8B:                  |
| Referral Path       |    | Direct Support Path       |
| [KB 2 + MCP Tool 4] |    | [KB 1 + MCP Tool 3]       |
+---------------------+    +---------------------------+
    |                          |
    v                          v
(see detail below)         (see detail below)


    +--------- At ANY point in the flow ---------+
    |                                             |
    v                                             v
+---------------------+    +---------------------+
| NODE 9:             |    | NODE 10:            |
| Tier 2 Escalation   |    | Tier 3 Escalation   |
| (AI cannot fulfill) |    | (Client requests    |
|                     |    |  a human)           |
| [KB 1 + ESCALATION] |    | [KB 1 + ESCALATION] |
+---------------------+    +---------------------+
```

---

## Node 8A Detail: Referral Path

```
NODE 8A: REFERRAL PATH
    |
    v
+------------------------------------------+
|  AI queries KB 2 (211 Resources)         |
|  Filter: need category + county          |
|                                          |
|  KB 2 returns matching providers:        |
|  - Provider name                         |
|  - Service description                   |
|  - Address, phone, hours                 |
|  - Eligibility notes                     |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  AI delivers referral to client          |
|                                          |
|  "Based on what you've shared, here are  |
|  some resources that may help:"          |
|                                          |
|  **Lowcountry Food Bank**                |
|  Food distribution network               |
|  lowcountryfoodbank.org/find-food        |
|                                          |
|  **Community Resource Center**           |
|  3947 Whipper Barony Ln, N. Charleston   |
|  843-641-8366 | Wed at 2pm               |
|                                          |
|  (Split across messages if > 1024 chars) |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  AI: "Would you like help with           |
|  anything else, or would you like to     |
|  speak with someone?"                    |
|                                          |
|  [I'm all set] [More help] [Talk to a    |
|   person]                                |
+------------------------------------------+
    |              |              |
    v              v              v
 COMPLETE    Back to Node 3   ESCALATION
    |                          (Tier 3)
    v
+------------------------------------------+
|  SCHEDULE FOLLOW-UP                      |
|  >>> MCP TOOL 4 <<<                      |
|  [Lambda -> Connect Tasks / Outbound]    |
|                                          |
|  Creates automated follow-up:            |
|  "Did you receive assistance?            |
|   Do you need additional help?"          |
|                                          |
|  - Connect Task for agent queue, OR      |
|  - Outbound Campaign (SMS/email)         |
|  - Linked to original session            |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  NODE 12: CLOSED-LOOP TRACKING           |
|  >>> MCP TOOL 4 <<<                      |
|                                          |
|  Follow-up response:                     |
|  - Need resolved --> close loop          |
|  - Unresolved --> re-route or escalate   |
|  - No response --> re-engagement         |
+------------------------------------------+
```

---

## Node 8B Detail: Direct Support Path

```
NODE 8B: DIRECT SUPPORT PATH
    |
    v
+------------------------------------------+
|  EXTENDED INTAKE                         |
|  [KB 1 — program-specific fields]        |
|                                          |
|  AI reads KB 1 for what to collect       |
|  per program. Example for Utility        |
|  Assistance:                             |
|                                          |
|  AI: "What type of utility do you        |
|  need help with?"                        |
|  [Electric] [Gas] [Water] [Other]        |
|                                          |
|  AI: "Who is your utility provider?"     |
|                                          |
|  AI: "How much is past due?"            |
|                                          |
|  AI: "Is there an upcoming shutoff       |
|  date?"                                  |
|  --> Within 72 hours = PRIORITY          |
|     (immediate Tier 2 escalation)        |
|                                          |
|  All stored in session attributes        |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  BUILD & SEND CHARITYTRACKER PAYLOAD     |
|  >>> MCP TOOL 3 <<<                      |
|  [Lambda -> SES Email]                   |
|                                          |
|  Payload assembled from session:         |
|  - Client name                           |
|  - Employee ID + employer (if T@W)       |
|  - Need category + subcategories         |
|  - ZIP / county                          |
|  - All intake answers                    |
|  - Extended intake answers               |
|  - Conversation summary                  |
|  - Escalation tier + reason              |
|  - Timestamp                             |
|                                          |
|  --> Sent via SES to CharityTracker      |
|      inbox (Phase 0)                     |
|  --> Direct API call when CT API         |
|      available (future)                  |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  AI: "I've submitted your information.   |
|  A case manager will be in touch         |
|  within [timeframe]."                    |
|                                          |
|  "Is there anything else I can help      |
|  with while you're here?"               |
|                                          |
|  [I'm all set] [More help] [Talk to a    |
|   person]                                |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  SCHEDULE FOLLOW-UP                      |
|  >>> MCP TOOL 4 <<<                      |
|                                          |
|  Creates task for assigned case manager  |
|  linked to original session              |
+------------------------------------------+
```

---

## Escalation Detail: Tier 2 and Tier 3

```
NODE 9: TIER 2 ESCALATION
(AI genuinely cannot fulfill)

Triggers:
- Ambiguous eligibility
- Safety concern disclosed
- System/tool failure
- Payment request
- Legal/medical/financial advice
- Employee ID validation failure
- Imminent utility shutoff (within 72 hrs)

    |
    v
+------------------------------------------+
|  AI acknowledges calmly from KB 1:       |
|                                          |
|  "I want to make sure you get the best   |
|  help possible. Let me connect you with  |
|  someone who can assist further."        |
|                                          |
|  ESCALATION tool packages:              |
|  - Full conversation history             |
|  - All session attributes                |
|  - Need category + subcategories         |
|  - Intake answers collected so far       |
|  - Employee ID + employer (if T@W)       |
|  - Reason for escalation                 |
|                                          |
|  --> Routed to human agent queue         |
+------------------------------------------+


NODE 10: TIER 3 ESCALATION
(Client requests a human)

    |
    v
+------------------------------------------+
|  AI: "Of course. Could you share what    |
|  you're hoping they can help with?       |
|  That way I can make sure you're         |
|  connected with the right person."       |
+------------------------------------------+
    |                          |
    | Client gives reason      | Client declines
    v                          v
+------------------------+  +------------------------+
| AI checks KB 1:        |  | AI: "No problem at     |
| Can I answer this?     |  | all."                  |
+------------------------+  |                        |
    |            |          | ESCALATION to general  |
    | YES        | NO       | queue with all context  |
    v            v          +------------------------+
+----------+  ESCALATE
| AI gives |  with context
| answer   |
| from KB  |
+----------+
    |
    v
+------------------------------------------+
|  AI: "I hope that helps. Would you       |
|  still like me to connect you with       |
|  someone?"                               |
|                                          |
|  [That helped, thanks] [Yes, connect me] |
+------------------------------------------+
    |                          |
    v                          v
 Continue in               ESCALATION
 AI flow                   with context +
                           "solution already
                            provided" noted
```

---

## Self-Sufficiency Matrix (Post-Handoff)

```
NODE 11: SELF-SUFFICIENCY MATRIX
(Facilitated by live agent, NOT the AI chatbot)

Live agent collects screening answers
from client during appointment:
    |
    v
+------------------------------------------+
|  SCORING                                 |
|  >>> MCP TOOL 2 <<<                      |
|  [Lambda — pure math, no LLM]           |
|                                          |
|  Housing:                                |
|  - housing situation answer              |
|  - monthly housing cost / income = ratio |
|  - housing challenges count              |
|  --> Score 1-5                           |
|                                          |
|  Employment:                             |
|  - employment situation answer           |
|  - income vs self-sufficiency standard   |
|  - benefits access                       |
|  --> Score 1-5                           |
|                                          |
|  Financial Resilience:                   |
|  - expenses vs income                    |
|  - savings rate                          |
|  - FICO score                            |
|  --> Score 1-5                           |
|                                          |
|  Composite:                              |
|  - ANY domain = 1 --> PRIORITY flag      |
|  - Average < 2.5 --> full Direct Support |
|  - Average 2.5-3.5 --> mixed path        |
|  - Average > 3.5 --> Referral default    |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  Results returned to live agent          |
|  for goal-setting and service planning   |
+------------------------------------------+
```

---

## Mixed Path: Referral + Direct Support

```
When a client selects MULTIPLE needs that span both paths:

Example: Client selects "Food Pantries" (REFERRAL)
         AND "Rental Assistance" (DIRECT SUPPORT)

    |
    v
+------------------------------------------+
|  NODE 5 classifies EACH subcategory:     |
|                                          |
|  Food Pantries --> REFERRAL              |
|  Rental Assistance --> DIRECT SUPPORT    |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  AI handles REFERRAL needs first         |
|  (lighter touch, can resolve in-session) |
|                                          |
|  --> KB 2 lookup for food pantries       |
|  --> Deliver referral info               |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  AI transitions to DIRECT SUPPORT needs  |
|                                          |
|  "Now let's look at help with your       |
|  rental situation. I'll need to gather   |
|  a bit more information."               |
|                                          |
|  --> Extended intake for housing         |
|  --> CharityTracker payload (MCP Tool 3) |
|  --> Follow-up scheduled (MCP Tool 4)    |
+------------------------------------------+
    |
    v
+------------------------------------------+
|  Both paths get follow-up:               |
|  - Referral: "Did you get food help?"    |
|  - Direct Support: case manager assigned |
+------------------------------------------+
```

---

## Session Attribute Flow

```
Attributes accumulated throughout the conversation:

NODE 2:  client_name (optional)
NODE 3:  need_categories[], subcategories[]
NODE 4:  employee_id, employer_name, eligible_programs (if Thrive@Work)
NODE 5:  support_path (referral | direct_support | mixed)
NODE 6:  zip_code, county, contact_method, contact_info,
         available_days[], available_times[], age, has_children,
         employment_status, employer (if employed), military_status,
         public_assistance[]
NODE 8A: referral_ids[], resources_delivered[]
NODE 8B: extended_intake (utility_type, provider, amount_past_due,
         shutoff_date, etc.)

All attributes:
- Persist within the session
- Passed to ESCALATION tool if handoff occurs
- Included in CharityTracker payload (MCP Tool 3)
- Available to Follow-up Scheduler (MCP Tool 4)
- Cleared on kiosk session end (auto-disconnect)
```

---

## Summary View

```
+===========+     +===========+     +=============+
|  KB 1     |     |  KB 2     |     | MCP Tools   |
|  Programs |     |  211      |     | (4 total)   |
|  & Rules  |     |  Resources|     |             |
+===========+     +===========+     +=============+
     |                 |                   |
     v                 v                   v
+--------------------------------------------------+
|                                                  |
|  SELF_SERVICE Agent (client-facing front door)   |
|  ORCHESTRATION Agent (multi-step workflows)      |
|                                                  |
|  Built-in tools:                                 |
|  QUESTION | FOLLOW_UP_QUESTION | ESCALATION      |
|  COMPLETE | CONVERSATION                         |
|                                                  |
+--------------------------------------------------+
     |
     v
+--------------------------------------------------+
|  CONVERSATION FLOW                               |
|                                                  |
|  Entry --> Identity --> Needs --> [Thrive@Work?]  |
|    --> Path Classification --> Intake             |
|      --> Referral (KB 2) OR Direct Support        |
|        --> Follow-up --> Closed Loop              |
|                                                  |
|  Escalation available at ANY point               |
|  General inquiry available at ANY point           |
+--------------------------------------------------+
     |
     v
+--------------------------------------------------+
|  END STATES                                      |
|                                                  |
|  - Referral delivered + follow-up scheduled       |
|  - Direct Support submitted + case manager notified|
|  - Human escalation completed (Tier 2 or 3)      |
|  - Client disengaged (partial data saved +        |
|    follow-up scheduled)                           |
|  - Session complete (client needs met)            |
+--------------------------------------------------+
```
