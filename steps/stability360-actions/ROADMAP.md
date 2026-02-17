# Step 2: Stability360 Actions — Roadmap

**What:** A single deployment step that delivers KB expansion, 211 community resources, and 3 new MCP action tools — following the same `deploy.py` pattern as `steps/thrive-at-work/`.

**Guardrails:** Deferred (not included in this step).

---

## What This Step Delivers

```
steps/stability360-actions/
  deploy.py                          # Single deploy script (same pattern as thrive-at-work)
  stability360-actions-stack.yaml    # CloudFormation template
  openapi/actions-spec.yaml          # OpenAPI spec (3 endpoints)
  prompts/orchestration-prompt.txt   # Updated prompt (adds 3 new tools + KB2 instructions)
  lambda/
    scoring_calculator/index.py      # MCP Tool 2 — Self-Sufficiency Matrix
    charitytracker_payload/index.py  # MCP Tool 3 — Build payload + SES email
    followup_scheduler/index.py      # MCP Tool 4 — Connect Tasks / Outbound
  seed-data/
    kb-documents/
      programs/                      # KB1 expansion — program details
        utility-assistance.txt       #   Utility assistance program (extended intake fields, priority rules)
        referrals-overview.txt       #   Referrals light-touch description
        emergency-financial.txt      #   Emergency financial assistance
        eap-expanded.txt             #   EAP services expanded
      routing/                       # KB1 expansion — path classification
        appendix-b-classification.txt#   All subcategories → referral vs direct support
        zip-county-agency.txt        #   ZIP → county → agency routing
      eligibility/                   # KB1 expansion — eligibility rules
        age-children-military.txt    #   Age 65+, children under 18, veteran routing
        employment-routing.txt       #   Employed/unemployed/retired/student routing
        income-guidelines.txt        #   Income thresholds for programs
      faq/                           # KB1 expansion — public FAQ
        what-is-stability360.txt     #   General "What is Stability360?" content
        what-to-expect.txt           #   What happens during and after intake
        document-requirements.txt    #   What to bring / what's needed
        hours-and-contact.txt        #   Operating hours, contact methods
      211-resources/                 # KB2 content — 211 community resources
        berkeley-county.txt          #   All Berkeley County providers
        charleston-county.txt        #   All Charleston County providers
        dorchester-county.txt        #   All Dorchester County providers
        tri-county-services.txt      #   Providers serving all 3 counties
        hotlines-and-crisis.txt      #   24/7 hotlines, crisis numbers
```

---

## CloudFormation Stack: `stability360-actions-stack.yaml`

| Resource | Purpose |
|----------|---------|
| `ScoringResultsTable` (DynamoDB) | Stores computed matrix scores for reporting |
| `ScoringCalculatorFunction` (Lambda) | MCP Tool 2 — housing ratio, employment score, financial resilience, composite |
| `CharityTrackerFunction` (Lambda) | MCP Tool 3 — assemble payload from session → send via SES |
| `FollowupSchedulerFunction` (Lambda) | MCP Tool 4 — create Connect Task or trigger outbound follow-up |
| `ActionsApi` (API Gateway) | 3 POST endpoints exposed for MCP |
| `ActionsApiKey` (API Key) | Auth for MCP Gateway |
| IAM roles | Scoped: SES send, DynamoDB write, Connect Tasks API |
| CloudWatch log groups | Per-function logging |

---

## MCP Tools (3 New)

### Tool 2: Scoring Calculator

**Endpoint:** `POST /scoring/calculate`

**Input:**
```json
{
  "housing_situation": "renting_stable|temporary|homeless|...",
  "monthly_income": 2800,
  "monthly_housing_cost": 950,
  "housing_challenges": ["past_due", "overcrowded"],
  "employment_status": "full_time_below_standard|part_time|...",
  "has_benefits": true,
  "monthly_expenses": 2600,
  "savings_rate": 0.03,
  "fico_range": "580-669"
}
```

**Output:**
```json
{
  "housing_score": 3,
  "employment_score": 2,
  "financial_resilience_score": 2,
  "composite_score": 2.33,
  "priority_flag": false,
  "recommended_path": "direct_support",
  "scoring_details": { ... }
}
```

**Logic (from Appendix C):**
- Housing: ratio-based (cost/income), situation category, challenges count → Score 1-5
- Employment: situation + income vs standard + benefits → Score 1-5
- Financial: expenses vs income + savings rate + FICO → Score 1-5
- Composite: average of 3. ANY domain=1 → PRIORITY. Avg < 2.5 → direct support. Avg 2.5-3.5 → mixed. Avg > 3.5 → referral
- Results stored in DynamoDB for reporting

### Tool 3: CharityTracker Payload + SES

**Endpoint:** `POST /charitytracker/submit`

**Input:**
```json
{
  "client_name": "Jane",
  "need_category": "housing",
  "subcategories": ["rental_assistance"],
  "zip_code": "29401",
  "county": "Charleston",
  "contact_method": "email",
  "contact_info": "jane@example.com",
  "intake_answers": { ... },
  "extended_intake": { ... },
  "conversation_summary": "Client needs rental assistance...",
  "escalation_tier": "direct_support",
  "timestamp": "2026-02-17T12:00:00Z"
}
```

**Output:**
```json
{
  "sent": true,
  "message_id": "ses-message-id",
  "payload_summary": "Direct Support submission for housing/rental_assistance in Charleston County"
}
```

**Logic:**
- Assemble structured HTML email from all session fields
- Send via SES to configured CharityTracker inbox (env var)
- Demo mode: send to a test email address
- Store submission record in DynamoDB for audit

### Tool 4: Follow-up Scheduler

**Endpoint:** `POST /followup/schedule`

**Input:**
```json
{
  "contact_info": "jane@example.com",
  "contact_method": "email",
  "referral_type": "referral|direct_support",
  "need_category": "food",
  "follow_up_message": "Did you receive food assistance? Do you need additional help?",
  "scheduled_days_out": 7
}
```

**Output:**
```json
{
  "scheduled": true,
  "follow_up_id": "uuid",
  "scheduled_date": "2026-02-24T12:00:00Z",
  "method": "connect_task"
}
```

**Logic:**
- Referral path → schedule automated follow-up (Connect Task or SES)
- Direct Support path → create task for case manager queue
- Store in DynamoDB with status tracking
- Demo mode: log the scheduled follow-up, create DynamoDB record

---

## KB Expansion — Folder Structure

All documents uploaded to the **existing** KB bucket. No employee data — strictly public-facing content.

### `programs/` — Expanded Program Docs

| Document | Content |
|----------|---------|
| `utility-assistance.txt` | Full utility assistance program: LIHEAP, ShelterNet, Santee Cooper. Extended intake fields (utility type, provider, amount past due, shutoff date). 72-hour shutoff = PRIORITY escalation rule. |
| `referrals-overview.txt` | Referral path explained: what happens, who contacts you, typical timeline. Light-touch vs full referral. |
| `emergency-financial.txt` | Emergency financial assistance: rent, utilities, prescriptions. Eligibility, what to bring, process. |
| `eap-expanded.txt` | Employee Assistance Program expanded: counseling sessions, financial coaching, legal consultation, work-life balance. |

### `routing/` — Path Classification & Agency Routing

| Document | Content |
|----------|---------|
| `appendix-b-classification.txt` | Complete subcategory → path mapping. Every need subcategory classified as REFERRAL or DIRECT SUPPORT. Used by the AI to route automatically. |
| `zip-county-agency.txt` | ZIP code → county → agency routing. Berkeley → Santee Cooper/BRCC. Charleston → NCRCC/CRCC. Dorchester → DRCC. Out-of-area handling. |

### `eligibility/` — Eligibility Rules

| Document | Content |
|----------|---------|
| `age-children-military.txt` | Age 65+ → BCDCOG senior programs. Children under 18 → Siemer Institute. Veteran/Active → Mission United. |
| `employment-routing.txt` | Full-time, part-time, unemployed, self-employed, retired, student, unable to work → routing rules for each. |
| `income-guidelines.txt` | Federal Poverty Level thresholds, LIHEAP income limits, program-specific income requirements. |

### `faq/` — Public FAQ

| Document | Content |
|----------|---------|
| `what-is-stability360.txt` | "Stability360 is a program operated by Trident United Way..." Overview, mission, service area. |
| `what-to-expect.txt` | What happens during chat, after intake, referral timeline, follow-up process. |
| `document-requirements.txt` | What to bring to appointments: ID, proof of income, utility bills, lease, etc. |
| `hours-and-contact.txt` | Operating hours, phone numbers, walk-in vs appointment, after-hours message. |

### `211-resources/` — Community Resources by County

Chunked from `sc211_tricounty_resources.md`:

| Document | Content |
|----------|---------|
| `berkeley-county.txt` | All Berkeley-specific providers: TUW Berkeley Center, Wesley Food Pantry, Santee Cooper, Berkeley MHC, Habitat Berkeley, Berkeley VA, Berkeley Emergency Mgmt, etc. |
| `charleston-county.txt` | All Charleston-specific providers: ShelterNet, East Cooper Outreach, Neighbors Together, City of Charleston Rehab, Charleston Emergency Mgmt, Star Gospel, Bounce Back, etc. |
| `dorchester-county.txt` | All Dorchester-specific providers: TUW Dorchester Center, ShelterNet Dorchester, Dorchester GED, CIFC Dental, Dorchester Emergency Svcs, etc. |
| `tri-county-services.txt` | Providers serving all 3 counties: Palmetto CAP, One80 Place, Lowcountry Food Bank, SC Legal Services, CARTA, SC Works, Fetter, Able SC, Navigation Center, etc. |
| `hotlines-and-crisis.txt` | All 24/7 crisis lines: 211, My Sister's House, Tri-County SPEAKS, Charleston/Dorchester MHC Crisis, Navigation Center, etc. |

---

## Deploy Script: `deploy.py`

Follows the exact same pattern as `steps/thrive-at-work/deploy.py`:

```
deploy.py \
  --stack-name stability360-actions \
  --region us-east-1 \
  --environment prod \
  --enable-mcp \
  --connect-instance-id <ID>
```

### Deployment Steps

| Step | Action |
|------|--------|
| 1 | Deploy CloudFormation stack (DynamoDB + 3 Lambdas + API Gateway) |
| 2 | Retrieve stack outputs |
| 3 | Update Lambda function code (scoring, charitytracker, followup) |
| 4 | Upload OpenAPI spec to S3 |
| 5 | Register API key in AgentCore Identity |
| 6 | Configure MCP REST API target (3 tools via OpenAPI) |
| 7 | Update gateway AllowedAudience |
| 8 | Register MCP server with Connect |
| 9 | Seed KB expansion documents to existing KB bucket |
| 10 | Seed 211 resource documents to existing KB bucket |
| 11 | Update AI Agent — add 3 new tools + update prompt with new tool instructions |
| 12 | Update security profile with new MCP tool permissions |
| 13 | Generate MCP tool config reference |

### Key Design Decisions

1. **Reuses existing KB bucket** — documents are uploaded to the same S3 bucket and Q Connect knowledge base from thrive-at-work. No separate KB2 needed since folder structure provides organization.

2. **Separate MCP Gateway target** — the 3 action tools are a separate API Gateway and a separate MCP target registration, keeping concerns separated from the employee lookup tool.

3. **Updates existing AI Agent** — adds 3 new tool configurations to the existing agent (doesn't create a new agent). The orchestration prompt is updated to include instructions for when to use each new tool.

4. **Demo-ready defaults** — CharityTracker email defaults to a test address. Follow-up scheduler creates DynamoDB records instead of real Connect Tasks in demo mode. Scoring uses demo thresholds from Appendix C.

5. **SES setup** — verifies sender identity in SES. Demo mode uses SES sandbox (verified recipient only). Production mode requires SES production access request.

---

## Updated Orchestration Prompt Additions

The existing prompt gets extended with instructions for 3 new tools:

```
## Tool: ScoringCalculator
Use this tool ONLY when a live agent requests a Self-Sufficiency Matrix score during
a facilitated session. Never invoke this during a regular client chat. The tool
performs exact mathematical scoring — do not attempt to calculate scores yourself.

## Tool: CharityTrackerPayload
Use this tool when a Direct Support intake is complete and all required fields have
been collected. Assembles the full session data into a structured payload and sends
it to the case management team. Always confirm with the client before submitting.

## Tool: FollowupScheduler
Use this tool after delivering a referral (schedule automated follow-up) or after
submitting a Direct Support payload (create task for case manager). The follow-up
ensures closed-loop tracking.
```

And KB retrieval instructions are expanded:

```
## 211 Community Resources
When a client needs a referral to community services, search the knowledge base with
the client's need category AND county. Results come from the 211 resource directory.
Always include: provider name, phone number, address, eligibility notes, and hours
when available. If no match found, direct client to dial 211.
```

---

## Verification Checklist

After deployment:

- [ ] CloudFormation stack creates successfully
- [ ] All 3 Lambda functions respond to test invocations
- [ ] API Gateway returns valid responses for all 3 endpoints
- [ ] MCP tools appear in Connect security profile
- [ ] KB expansion documents appear in Q Connect knowledge base (search test)
- [ ] 211 resource documents return correct providers by county (search test)
- [ ] AI Agent responds using new tools when prompted
- [ ] Scoring Calculator returns correct scores for known test inputs
- [ ] CharityTracker sends test email via SES
- [ ] Follow-up Scheduler creates DynamoDB record
- [ ] Existing thrive-at-work functionality still works (employee lookup, greeting, intake bot)
- [ ] Both environments (dev us-west-2, prod us-east-1) deploy successfully

---

## Execution Order

```
1. Write CloudFormation template (stack.yaml)
2. Write 3 Lambda functions
3. Write OpenAPI spec (3 endpoints)
4. Write KB expansion documents (programs, routing, eligibility, faq)
5. Chunk 211 resources into county documents
6. Write deploy.py (following thrive-at-work pattern)
7. Update orchestration prompt
8. Test deploy to dev (us-west-2)
9. Verify all tools + KB retrieval
10. Deploy to prod (us-east-1)
```

All done as a single `deploy.py` run — one command deploys everything.
