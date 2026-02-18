# Step 2: Stability360 Actions — Roadmap

**What:** A single deployment step that delivers KB expansion, 211 community resources, and 3 new MCP action tools — following the same `deploy.py` pattern as `steps/thrive-at-work/`.

**Guardrails:** Deferred (not included in this step).

---

## Architecture

- **Single Lambda function** with a router (`index.py`) dispatching to 3 modular action files
- **Single API Gateway** with 3 POST endpoints, all backed by the same Lambda
- **Single MCP Gateway** with 1 target (OpenAPI spec defines all 3 operations)
- **New AI Agent** — created separately, NOT set as default. Has only the 3 action tools + Retrieve
- **No employee data** — this agent cannot query employee records
- **KB expansion** — public-facing documents seeded to the existing thrive-at-work KB bucket

---

## File Structure

```
steps/stability360-actions/
  deploy.py                          # Single deploy script (13 steps)
  stability360-actions-stack.yaml    # CloudFormation template
  openapi/actions-spec.yaml          # OpenAPI spec (3 endpoints, 1 API)
  prompts/orchestration-prompt.txt   # Orchestration prompt for actions agent
  lambda/
    actions/                         # Single Lambda — modular routing
      index.py                       #   Router: path + MCP tool dispatch
      scoring_calculator.py          #   MCP Tool: Self-Sufficiency Matrix
      charitytracker_payload.py      #   MCP Tool: Build payload + SES email
      followup_scheduler.py          #   MCP Tool: Follow-up scheduling
  seed-data/
    kb-documents/
      programs/                      # KB1 expansion — program details
        utility-assistance.txt
        referrals-overview.txt
        emergency-financial.txt
        eap-expanded.txt
      routing/                       # KB1 expansion — path classification
        appendix-b-classification.txt
        zip-county-agency.txt
      eligibility/                   # KB1 expansion — eligibility rules
        age-children-military.txt
        employment-routing.txt
        income-guidelines.txt
      faq/                           # KB1 expansion — public FAQ
        what-is-stability360.txt
        what-to-expect.txt
        document-requirements.txt
        hours-and-contact.txt
      211-resources/                 # 211 community resources by county
        berkeley-county.txt
        charleston-county.txt
        dorchester-county.txt
        tri-county-services.txt
        hotlines-and-crisis.txt
```

---

## CloudFormation Stack

| Resource | Purpose |
|----------|---------|
| `ActionsTable` (DynamoDB) | Stores scoring results, submissions, follow-ups |
| `ActionsFunction` (Lambda) | Single function routing to 3 action modules |
| `ActionsApi` (API Gateway) | 3 POST endpoints: /scoring/calculate, /charitytracker/submit, /followup/schedule |
| `ActionsApiKey` (API Key) | Auth for MCP Gateway |
| `SpecBucket` (S3) | Stores OpenAPI spec for MCP target |
| `AgentCoreGateway` (MCP) | MCP Gateway for 3 action tools |
| IAM roles | Scoped: DynamoDB write, SES send, Connect Tasks API |
| CloudWatch log groups | Lambda and API Gateway logging |

---

## MCP Tools (3)

### Scoring Calculator — `POST /scoring/calculate`
- Computes housing (1-5), employment (1-5), financial resilience (1-5) scores
- Composite score = average. ANY domain=1 → PRIORITY. <2.5 → direct_support. 2.5-3.5 → mixed. >3.5 → referral
- For case manager facilitated sessions ONLY (not regular chat)

### CharityTracker Payload — `POST /charitytracker/submit`
- Assembles structured HTML email from intake session data
- Sends via SES to configured CharityTracker inbox
- Always confirm with client before submitting
- Demo mode: sends to test email (SES sandbox)

### Follow-up Scheduler — `POST /followup/schedule`
- Referral path → automated follow-up (email or Connect Task)
- Direct Support → case manager task
- Demo mode: DynamoDB record only (no real tasks)

---

## Deploy Script

```bash
python deploy.py \
  --stack-name stability360-actions-prod \
  --region us-east-1 \
  --environment prod \
  --enable-mcp \
  --connect-instance-id <ID> \
  --thrive-stack-name stability360-thrive-at-work-prod
```

### Deployment Steps (13)

| Step | Action |
|------|--------|
| 1 | Deploy CloudFormation stack (DynamoDB + Lambda + API GW + MCP GW) |
| 2 | Retrieve stack outputs |
| 3 | Update Lambda code (single function, 4 Python files) |
| 4 | Seed KB expansion + 211 documents to thrive KB bucket |
| 5 | Upload OpenAPI spec to S3 |
| 6 | Register API key in AgentCore Identity |
| 7 | Create MCP REST API target (3 tools via OpenAPI) |
| 8 | Update gateway AllowedAudience |
| 9 | Register MCP server with Connect |
| 10 | Create security profile + MCP tool permissions |
| 11 | Create orchestration prompt |
| 12 | Create AI Agent (NOT default) with 3 MCP tools + Retrieve |
| 13 | Generate MCP tool config reference |

### Key Design Decisions

1. **Single Lambda + Single API** — one function handles all 3 actions via path-based routing. Separate Python modules keep code organized.

2. **New AI Agent (not default)** — a separate agent with only the 3 action tools and Retrieve. Does not replace or modify the thrive-at-work agent. Not set as default for self-service.

3. **No employee data** — this agent has no access to the employee lookup tool. KB documents are strictly public-facing content.

4. **Reuses existing KB bucket** — documents seeded to the thrive-at-work KB bucket under `stability360/` prefix. Q Connect knowledge base picks them up automatically.

5. **Separate MCP Gateway** — own gateway, own target, own security profile. Fully independent from thrive-at-work MCP.

6. **Demo-ready defaults** — CharityTracker sends to test email. Follow-up creates DynamoDB records only. Scoring uses Appendix C thresholds.

---

## Verification Checklist

- [ ] CloudFormation stack creates successfully
- [ ] Lambda function responds to all 3 endpoints
- [ ] API Gateway returns valid responses with API key
- [ ] MCP tools appear in Connect security profile
- [ ] KB expansion documents return in Q Connect searches
- [ ] 211 resources return correct providers by county
- [ ] AI Agent created (not default) with 3 tools
- [ ] Scoring Calculator returns correct scores for test inputs
- [ ] CharityTracker sends test email via SES
- [ ] Follow-up Scheduler creates DynamoDB record
- [ ] Existing thrive-at-work agent unaffected
