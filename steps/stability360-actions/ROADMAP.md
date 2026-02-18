# Step 2: Stability360 Actions

**What:** Complete deployment step delivering 6 MCP action tools, an intake bot for service routing, KB expansion with 211 community resources, and a dedicated AI agent (Aria) — following the same `deploy.py` pattern as `steps/thrive-at-work/`.

---

## Architecture

- **Single Lambda function** with a router (`index.py`) dispatching to 6 modular action files
- **Single API Gateway** with 6 POST endpoints, all backed by the same Lambda
- **Single MCP Gateway** with 1 target (OpenAPI spec defines all 6 operations)
- **Intake Bot** (Lex V2) — ListPicker menu routing customers to Community Resources or Thrive@Work
- **New AI Agent (Aria)** — created separately, NOT set as default. Has 6 action tools + Retrieve
- **No employee data** — this agent cannot query employee records
- **KB expansion** — public-facing documents seeded to the existing thrive-at-work KB bucket

---

## File Structure

```
steps/stability360-actions/
  deploy.py                          # Single deploy script (14 steps)
  stability360-actions-stack.yaml    # CloudFormation template
  openapi/actions-spec.yaml          # OpenAPI spec (6 endpoints, 1 API)
  prompts/orchestration-prompt.txt   # Orchestration prompt for Aria agent
  lambda/
    actions/                         # Single Lambda — modular routing
      index.py                       #   Router: path + MCP tool dispatch
      scoring_calculator.py          #   MCP Tool 1: Self-Sufficiency Matrix
      charitytracker_payload.py      #   MCP Tool 2: Build payload + SES email
      followup_scheduler.py          #   MCP Tool 3: Follow-up scheduling
      customer_profile.py            #   MCP Tool 4: Customer profile lookup/create
      case_status.py                 #   MCP Tool 5: Case status lookup
      case_creator.py                #   Amazon Connect Cases integration
      sophia_resource_lookup.py      #   MCP Tool 6: SC 211 resource search
    intake_bot/                      # Lex V2 Intake Bot Lambda
      lambda_function.py             #   ListPicker menu → route to AI agents
  seed-data/
    kb-documents/
      programs/                      # KB expansion — program details
      routing/                       # KB expansion — path classification
      eligibility/                   # KB expansion — eligibility rules
      faq/                           # KB expansion — public FAQ
      211-resources/                 # 211 community resources by county
  test_e2e.py                        # End-to-end API test suite
  ai-agent-tool-config.json          # Auto-generated tool config reference
```

---

## Prerequisites

1. **AWS CLI** configured with credentials that have admin-level access
2. **Python 3.10+** with `boto3` installed
3. **Thrive-at-work stack deployed** (for KB bucket — use `--thrive-stack-name`)
4. **Amazon Connect instance** with Q Connect (Amazon Q in Connect) enabled
5. **SES verified email** (for CharityTracker — sandbox mode works for dev)

---

## Deployment Instructions

### Dev Environment (us-west-2)

```bash
cd steps/stability360-actions

python deploy.py \
  --stack-name stability360-actions-dev \
  --region us-west-2 \
  --environment dev \
  --enable-mcp \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d \
  --thrive-stack-name stability360-thrive-at-work-dev
```

### Prod Environment (us-east-1)

```bash
cd steps/stability360-actions

python deploy.py \
  --stack-name stability360-actions-prod \
  --region us-east-1 \
  --environment prod \
  --enable-mcp \
  --connect-instance-id 9b50ddcc-8510-441e-a9c8-96e9e9281105 \
  --thrive-stack-name stability360-thrive-at-work-prod
```

### Deployment Steps (14)

| Step | Action |
|------|--------|
| 1 | Deploy CloudFormation stack (DynamoDB, Lambda, API GW, MCP GW, Intake Bot Lambda) |
| 2 | Retrieve stack outputs |
| 3 | Update Lambda code (actions function + intake bot function) |
| 4 | Seed KB expansion + 211 documents to thrive KB bucket |
| 5 | Upload OpenAPI spec to S3 (or use CFN custom resource output) |
| 6 | Register API key credential in AgentCore Identity |
| 7 | Create MCP REST API target (6 tools via OpenAPI) |
| 8 | Update MCP Gateway AllowedAudience to gateway ID |
| 9 | Register MCP server application with Connect |
| 10 | Create security profile + MCP tool permissions |
| 11 | Create orchestration prompt (Aria) |
| 12 | Create AI Agent (NOT default) with 6 MCP tools + Retrieve |
| 13 | Generate MCP tool config reference file |
| 14 | Create Intake Bot (Lex V2) — intents, slots, build, alias, Connect association |

### Quick Commands

**Update Lambda code only** (no CFN changes):
```bash
python deploy.py --update-code-only --stack-name stability360-actions-dev --region us-west-2
```

**Update orchestration prompt only**:
```bash
python deploy.py --update-prompt \
  --stack-name stability360-actions-dev \
  --region us-west-2 \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d
```

**MCP + Connect steps only** (skip CFN/Lambda, redo steps 5-14):
```bash
python deploy.py --connect-only \
  --stack-name stability360-actions-dev \
  --region us-west-2 \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d
```

**Seed KB documents only**:
```bash
python deploy.py --seed-only \
  --thrive-stack-name stability360-thrive-at-work-dev \
  --region us-west-2
```

**Delete stack**:
```bash
python deploy.py --delete --stack-name stability360-actions-dev --region us-west-2
```

### Run E2E Tests

```bash
python test_e2e.py --env dev
python test_e2e.py --env prod
```

---

## CloudFormation Stack

| Resource | Purpose |
|----------|---------|
| `ActionsTable` (DynamoDB) | Stores scoring results, submissions, follow-ups, profiles |
| `ActionsFunction` (Lambda) | Single function routing to 6 action modules |
| `IntakeBotFunction` (Lambda) | Lex V2 intake bot code hook |
| `ActionsApi` (API Gateway) | 6 POST endpoints with API key auth |
| `ActionsApiKey` (API Key) | Auth for MCP Gateway |
| `SpecBucket` (S3) | Stores OpenAPI spec for MCP target |
| `AgentCoreGateway` (MCP) | MCP Gateway for 6 action tools |
| IAM roles | Scoped: DynamoDB, SES, Connect Cases, Connect Tasks |
| CloudWatch log groups | Lambda and API Gateway logging |

---

## MCP Tools (6)

### 1. Scoring Calculator — `POST /scoring/calculate`
- Computes housing (1-5), employment (1-5), financial resilience (1-5) scores
- Composite score = average. ANY domain=1 → PRIORITY
- Path: <2.5 → direct_support, 2.5-3.5 → mixed, >3.5 → referral
- Scores are internal only — never shared with the client

### 2. CharityTracker Payload — `POST /charitytracker/submit`
- Assembles structured HTML email from intake session data
- Creates an Amazon Connect Case with reference number
- Sends case details via SES to configured CharityTracker inbox
- Always confirm with client before submitting

### 3. Follow-up Scheduler — `POST /followup/schedule`
- Referral path → automated follow-up (email or Connect Task)
- Direct Support → case manager task
- Links to existing case via case_id/case_reference

### 4. Customer Profile — `POST /customer/profile`
- Searches for existing customer profile by name/email/phone
- Creates new profile if not found
- Called only when creating a case (NOT before scoring)

### 5. Case Status — `POST /case/status`
- Looks up case by reference number
- Returns status, description, and message for the client
- No consent required — just needs case reference

### 6. Resource Lookup — `POST /resources/search`
- Queries SC 211 directory (sophia-app.com) for community resources
- Filters by keyword, county, city, ZIP code
- Returns provider name, description, address, phone, URL, eligibility, fees

---

## Intake Bot (Lex V2)

The intake bot presents a ListPicker menu with two service options:

| Selection | Intent | Routes To |
|-----------|--------|-----------|
| Community Resources | `RouteToCommunityResources` | Stability360 Actions AI agent (Aria) |
| Thrive@Work | `RouteToThriveAtWork` | Thrive@Work AI agent |

### Contact Flow Integration

```
Start
  → Get customer input (Intake Bot: {stack-name}-intake-bot / live)
      ├─ Intent: RouteToCommunityResources
      │    → Get customer input (Stability360Bot + Aria AI agent ARN)
      │    → Disconnect
      ├─ Intent: RouteToThriveAtWork
      │    → Get customer input (Stability360Bot + Thrive@Work AI agent ARN)
      │    → Disconnect
      └─ Error / Default
           → Play prompt → Disconnect
```

---

## Agent Workflow — Scoring Flow

The orchestration prompt enforces a strict consent-first, scoring-first flow:

```
1. Customer asks for help
2. Aria asks for CONSENT → waits for "yes"
3. Collect ALL data (name, contact, housing, income, employment) — NO tool calls
4. Call scoringCalculate — FIRST and ONLY tool call
5. Present options based on recommended_path → WAIT for customer choice
6. Customer chooses → customerProfileLookup (one turn)
7. charityTrackerSubmit (next turn) → share case reference
8. Optional: followupSchedule, Escalate, or Complete
```

**Key rules:**
- Only ONE tool call per turn (prevents blank messages)
- No customerProfileLookup before scoring
- No auto-submitting cases — always wait for customer choice

---

## Verification Checklist

- [ ] CloudFormation stack creates/updates successfully
- [ ] Lambda function responds to all 6 endpoints (run `test_e2e.py`)
- [ ] API Gateway returns valid responses with API key
- [ ] MCP tools appear in Connect security profile
- [ ] KB expansion documents return in Q Connect searches
- [ ] 211 resources return correct providers by county/ZIP
- [ ] AI Agent (Aria) created with 6 tools + Retrieve
- [ ] Scoring Calculator returns correct scores for test inputs
- [ ] Consent flow works — asks before collecting data
- [ ] No blank messages during scoring flow
- [ ] Intake bot shows ListPicker menu and routes correctly
- [ ] Intake bot associated with Connect instance
- [ ] Existing thrive-at-work agent unaffected
