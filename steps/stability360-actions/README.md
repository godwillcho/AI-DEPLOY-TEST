# Stability360 Actions

AI-powered support agent (Aria) for Trident United Way, built on Amazon Connect Q with MCP Gateway tools.

## Architecture

```
Caller → Amazon Connect → Q Connect AI Agent (Aria)
                              ↓
                        MCP Gateway → API Gateway → Lambda
                              ↓
                   ┌──────────┴──────────┐
                   │                     │
             intakeHelper          resourceLookup
           (2 actions)           (Sophia API search +
                                  auto-scoring + partner
                                  detection)
                   │
     ┌─────────────┼─────────────┐
     │             │             │
  Customer      Task          Case
  Profile     (callback)    (callback/
                             transfer)
```

**Post-disposition automation** runs silently when a caller chooses callback or live transfer:
1. **Customer Profile** — find or create by phone (E.164), email, or name
2. **Task** (callback only) — routed to BasicQueue with all intake data
3. **Case** — linked to contact and customer profile

The task contact flow includes a `GetCustomerProfile` block so the profile auto-resolves in the agent workspace when a callback task is accepted.

## MCP Tools

| Tool | Endpoint | Description |
|------|----------|-------------|
| `intakeHelper` | `POST /intake/helper` | 2 actions: getNextSteps (conversational next step guidance), recordDisposition (callback/transfer/self-resolved) |
| `resourceLookup` | `POST /resources/search` | Queries Sophia community resource API by keyword, county, city, or ZIP. Auto-triggers stability scoring and partner employer detection. |

## Lambda Modules

| Module | Purpose |
|--------|---------|
| `index.py` | Main handler — routes requests to intakeHelper or resourceLookup |
| `config.py` | Shared config, constants, E.164 phone normalization (`normalize_phone`) |
| `intake_helper.py` | 2 actions: getNextSteps (next conversational step), recordDisposition |
| `auto_scoring.py` | Auto-triggers stability scoring + Thrive@Work partner detection after resource search |
| `scoring_calculator.py` | Housing/employment/financial stability scoring (1-5 scale) |
| `partner_employers.py` | Thrive@Work partner employer list + fuzzy matching + misspelling correction |
| `contact_attributes.py` | Contact attribute persistence after every tool call + eligibility flag derivation |
| `profile_lookup.py` | Returning caller profile lookup (read-only, searches by phone/email/name) |
| `queue_checker.py` | Real-time agent availability via GetCurrentMetricData |
| `sophia_resource_lookup.py` | Sophia API integration with proximity sorting |
| `task_manager.py` | Customer profile, task, and case creation (post-disposition) |

## KB Seed Data

Knowledge base documents are stored in `seed-data/kb-documents/` and uploaded to the Q Connect KB S3 bucket via `--update-kb`:

| Directory | Document | Purpose |
|-----------|----------|---------|
| `classify-need/` | `need-categories.txt` | 14 need categories with keywords + emergency detection |
| `validate-zip/` | `service-area-zips.txt` | Tri-county ZIP codes (Charleston, Berkeley, Dorchester) |
| `check-partner/` | `partner-employers.txt` | Thrive@Work partner employer list + matching rules |
| `thriveatwork/` | Program documents | Thrive@Work program reference material |

The AI agent uses KB Retrieve to look up ZIP validation, need classification, and partner matching at runtime.

**Intake field rules** (Route R vs Route D, consent, field ordering) are embedded directly in the orchestration prompt for reliability — not in the KB.

## Deployment

### Prerequisites

- AWS CLI configured with appropriate credentials
- Python 3.9+, boto3
- Amazon Connect instance with:
  - Q Connect assistant configured
  - Customer Profiles domain enabled
  - Cases domain enabled
  - BasicQueue created

### Full Deploy (new environment)

Deploys everything end-to-end: CFN stack, Lambda, API Gateway, MCP Gateway, AI Agent, Connect wiring, task resources.

```bash
cd steps/stability360-actions

# Dev environment (us-west-2)
python deploy.py \
  --stack-name stability360-actions-dev \
  --region us-west-2 \
  --environment dev \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d

# Prod environment (us-east-1)
python deploy.py \
  --stack-name stability360-actions-prod \
  --region us-east-1 \
  --environment prod \
  --connect-instance-id 9b50ddcc-8510-441e-a9c8-96e9e9281105
```

For a different AWS account, set `AWS_PROFILE` before running:

```bash
AWS_PROFILE=other-account python deploy.py \
  --stack-name stability360-actions-prod \
  --region us-east-1 \
  --environment prod \
  --connect-instance-id <INSTANCE_ID>
```

**Deployment steps (14 total):**

| Step | What | Description |
|------|------|-------------|
| 1 | CloudFormation Stack | Lambda, API Gateway, IAM roles, DynamoDB, S3, MCP Gateway, CloudWatch |
| 2 | Stack Outputs | Retrieve resource IDs and URLs |
| 3 | Lambda Code | Zip and upload all modules |
| 4 | API Gateway Redeploy | Activate inline OpenAPI Body changes |
| 5 | OpenAPI Spec | Upload `actions-spec.yaml` to S3 for MCP tool definitions |
| 6 | API Key Credential | Register API key with Bedrock AgentCore token vault |
| 7 | MCP Target | Create/update REST API target on MCP Gateway |
| 8 | Gateway Audience | Set OIDC discovery URL for Connect instance |
| 9 | Connect Registration | Register MCP app with Connect via App Integrations |
| 10 | Security Profile | Create/update profile with MCP tool permissions |
| 10b | KB Seed Data | Upload seed data documents to Q Connect KB S3 bucket |
| 11 | Orchestration Prompt | Create/update AI prompt from `orchestration-prompt.txt` |
| 12 | AI Agent | Create/update Q Connect agent with tools and prompt |
| 13 | Tool Config | Generate `ai-agent-tool-config.json` reference file |
| 14 | Task Resources | BasicQueue lookup, task flow, task template, profiles/cases domains, case template, Lambda env vars |

### Partial Deploys (faster iteration)

```bash
# Lambda code only
python deploy.py --update-code-only \
  --stack-name stability360-actions-dev --region us-west-2

# Orchestration prompt only
python deploy.py --update-prompt \
  --stack-name stability360-actions-dev --region us-west-2 \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d

# KB seed data only (uploads to S3 bucket backing the Q Connect KB)
python deploy.py --update-kb \
  --stack-name stability360-actions-dev --region us-west-2 \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d

# MCP + Connect + task resources (skip CFN/Lambda)
python deploy.py --connect-only \
  --stack-name stability360-actions-dev --region us-west-2 \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d
```

### Teardown

Full cleanup: AI agent, prompt, security profile, Connect integration, MCP gateway/target, API key credential, task template, task flow (archived), case template (deactivated), CFN stack.

```bash
python deploy.py --teardown \
  --stack-name stability360-actions-dev --region us-west-2 \
  --connect-instance-id e75a053a-60c7-45f3-83f7-a24df6d3b52d
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--stack-name` | CloudFormation stack name (default: `stability360-actions`) |
| `--region` | AWS region (default: `us-west-2`) |
| `--environment` | Environment tag: `dev`, `staging`, or `prod` |
| `--connect-instance-id` | Amazon Connect instance ID (enables all Connect steps) |
| `--enable-mcp` | Enable MCP Gateway (auto-enabled with `--connect-instance-id`) |
| `--update-code-only` | Only update Lambda function code |
| `--update-prompt` | Only update the orchestration prompt |
| `--update-kb` | Upload KB seed data documents to the Q Connect KB S3 bucket |
| `--connect-only` | Skip CFN/Lambda, do MCP (5-7) + Connect (8-14) steps |
| `--set-default` | Set the AI agent as default orchestration agent |
| `--model-id` | Override the AI model for orchestration |
| `--openapi-spec-url` | Override OpenAPI spec URL (auto-detected by default) |
| `--teardown` | Full teardown of all resources |
| `--delete` | Delete CFN stack only |
| `--delete-security-profile` | Also delete security profile during teardown |

## Session Attributes Reference

All attributes are stored as string key-value pairs on the Amazon Connect contact. Phone numbers are auto-normalized to E.164 format (`+1XXXXXXXXXX`).

### Core Intake Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| `firstName` | Client's first name | `Maria` |
| `lastName` | Client's last name | `Johnson` |
| `zipCode` | Client's ZIP code | `29401` |
| `phoneNumber` | Client's phone number (E.164) | `+18435551234` |
| `contactMethod` | Preferred contact method | `phone`, `email` |
| `contactInfo` | Phone (E.164) or email | `+18435551234`, `maria@email.com` |
| `employmentStatus` | Employment status | `part_time`, `unemployed`, `full_time` |
| `employer` | Employer name | `Boeing` |
| `preferredDays` | Days available for callback | `Monday through Wednesday` |
| `preferredTimes` | Time of day preference | `Mornings` |

### Disposition Automation Attributes

| Attribute | Description | Set When |
|-----------|-------------|----------|
| `customerProfileId` | Customer Profiles profile ID | callback, live_transfer |
| `taskCreated` | Whether callback task was created | callback (`true`/`false`) |
| `taskContactId` | Task contact ID in Connect | callback (if created) |
| `caseId` | Cases case ID | callback, live_transfer |

### Scoring Attributes (Direct Support path)

| Attribute | Description | Example |
|-----------|-------------|---------|
| `housingScore` | Housing stability score (1-5) | `2` |
| `employmentScore` | Employment stability score (1-5) | `3` |
| `financialResilienceScore` | Financial resilience score (1-5) | `2` |
| `compositeScore` | Average of 3 domain scores | `2.33` |
| `priorityFlag` | Urgent priority indicator | `true`, `false` |
| `scoringSummary` | Human-readable summary | `Housing: 2, Employment: 3, Financial: 2` |

### Partner Attributes

| Attribute | Description | Example |
|-----------|-------------|---------|
| `partnerEmployee` | Works for a Thrive@Work partner | `true` |

## Testing

### Test resourceLookup (API Gateway)

```bash
curl -X POST https://<API_URL>/resources/search \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY>" \
  -d '{"keyword": "food", "county": "Charleston", "zip_code": "29401"}'
```

Keywords: `food`, `rent`, `utilities`, `shelter`, `dental`, `transportation`, `legal`, `childcare`, `jobs`

### Test ZIP Codes (service area validation)

| ZIP | County | In Area? |
|-----|--------|----------|
| `29401` | Charleston | Yes |
| `29464` | Mt. Pleasant | Yes |
| `29485` | Summerville | Yes |
| `29445` | Goose Creek | Yes |
| `29910` | Beaufort | No |
| `29201` | Columbia | No |

### Test via AI Agent (Connect Console)

Open Amazon Connect console → Q in Connect → Test chat:

- **Resource search:** "What food banks are in Charleston?"
- **Callback flow:** "I need help with my electric bill" → complete intake → choose callback
- **Direct-to-agent:** "I'd like to speak with someone" → minimal intake → transfer/callback
- **Emergency:** "I'm going to hurt myself" → emergency protocol

Full test journeys: [test_customer_journeys.md](test_customer_journeys.md)
