# Stability360 Actions — System Inventory

## Overview

The Stability360 Actions stack is a serverless system deployed on AWS that powers the AI-driven community resource intake and referral workflow for Trident United Way's Stability360 program. It integrates Amazon Connect (contact center), Amazon Q Connect (AI agent), and external APIs to triage callers, search community resources, score eligibility, and manage case records.

**Service Area:** Berkeley, Charleston, and Dorchester counties, South Carolina.

---

## Architecture Diagram

```
Caller → Amazon Connect Contact Flow
             │
             ├─ Lex V2 Bot (QInConnectIntent)
             │       │
             │       └─ Amazon Q Connect AI Agent
             │               │
             │               ├─ Knowledge Base (Retrieve tool)
             │               │     └─ S3 seed data (classify-need, validate-zip, check-partner, thriveatwork)
             │               │
             │               ├─ MCP Tool: resourceLookup ──► API Gateway ──► Actions Lambda ──► Sophia API
             │               │                                                      │
             │               │                                                      ├─ DynamoDB (records)
             │               │                                                      ├─ S3 (HTML results pages)
             │               │                                                      ├─ Connect Cases (create/update)
             │               │                                                      ├─ Customer Profiles (upsert)
             │               │                                                      └─ Connect Tasks (create)
             │               │
             │               └─ MCP Tool: intakeHelper ────► API Gateway ──► Actions Lambda (same)
             │
             └─ Case Updater Lambda (post-call, invoked by contact flow)
                     └─ Connect Cases (UpdateCase)
```

---

## Deployed AWS Resources

### CloudFormation Stack

| Property | Value |
|----------|-------|
| Stack name | `stability360-actions` |
| Region | `us-east-1` |

### 1. Actions Lambda Function

| Property | Value |
|----------|-------|
| Function name | `stability360-actions-actions` |
| Runtime | Python 3.13 |
| Handler | `index.handler` |
| Timeout | 30s |
| Memory | 256 MB |
| Tracing | X-Ray Active |

**Environment Variables:**

| Variable | Purpose |
|----------|---------|
| `ACTIONS_TABLE_NAME` | DynamoDB table for records |
| `CONNECT_INSTANCE_ID` | Amazon Connect instance ID |
| `ENVIRONMENT` | Runtime environment identifier |
| `LOG_LEVEL` | `INFO` |
| `SOPHIA_API_URL` | `https://api-prod-0.sophia-app.com/api/services/search/keyword-search` |
| `SOPHIA_TENANT` | `sc-prod-0` |
| `SOPHIA_ORIGIN` | `https://www.sc211.org` |
| `SOPHIA_MAX_RESULTS` | `3` |
| `RESULTS_BUCKET_NAME` | S3 bucket for HTML result pages |

**Lambda Modules (12 files):**

| Module | Purpose |
|--------|---------|
| `index.py` | Main router — handles API Gateway, MCP, and direct invocations |
| `config.py` | Shared constants, environment variables, logger |
| `intake_helper.py` | 6 intake actions: classify need, validate ZIP, get fields, check partner, get next steps, record disposition |
| `sophia_resource_lookup.py` | Queries Sophia API, calculates distances, generates HTML results page, stores in S3 |
| `auto_scoring.py` | Wraps resource lookup with automatic scoring when housing/income/employment data is present |
| `scoring_calculator.py` | Scoring math (housing, employment, financial resilience, composite scores, eligibility flags) |
| `contact_attributes.py` | Persists all collected data as Amazon Connect contact attributes after every tool call |
| `task_manager.py` | Post-disposition automation: creates Customer Profile, Connect Task, and Connect Case |
| `queue_checker.py` | Checks agent availability in Connect queues |
| `partner_employers.py` | Thrive@Work partner employer list |
| `profile_lookup.py` | Customer Profile search/upsert |

**API Routes:**

| Route Type | Key | Handler |
|------------|-----|---------|
| API Gateway path | `/resources/search` | Resource lookup with auto-scoring |
| API Gateway path | `/intake/helper` | Intake helper actions |
| API Gateway path | `/scoring/calculate` | Scoring calculation |
| API Gateway GET | `/r/{pageId}` | Results page redirect (presigned S3 URL) |
| MCP tool name | `resourceLookup` | Resource lookup with auto-scoring |
| MCP tool name | `intakeHelper` | Intake helper actions |
| MCP tool name | `scoringCalculate` | Scoring calculation |

### 2. Case Updater Lambda Function

| Property | Value |
|----------|-------|
| Function name | `stability360-actions-case-updater` |
| Runtime | Python 3.13 |
| Handler | `index.handler` |
| Timeout | 15s |
| Memory | 128 MB |
| Invoked by | Amazon Connect contact flow (post-call) |

**Environment Variables:**

| Variable | Purpose |
|----------|---------|
| `CONNECT_CASES_DOMAIN_ID` | Cases domain UUID |
| `CASE_FIELD_MAP` | JSON mapping of attribute names to field UUIDs (37 fields) |
| `CONNECT_REGION` | AWS region |
| `LOG_LEVEL` | `INFO` |

**How it works:**
1. Connect contact flow invokes the Lambda with `event.Details.ContactData.Attributes`
2. Extracts `caseId` from attributes — if missing, no-op
3. Loops through `CASE_FIELD_MAP` — for each matching attribute, builds a field update
4. Calls `connectcases:UpdateCase` with matched fields

**Case Fields Mapped (37):**

| Category | Fields |
|----------|--------|
| Contact Info | `firstName`, `lastName`, `zipCode`, `phoneNumber`, `emailAddress`, `contactMethod` |
| Need & Intake | `needCategory`, `age`, `hasChildrenUnder18`, `employmentStatus`, `employer`, `monthlyIncome`, `housingSituation` |
| Background | `militaryAffiliation`, `publicAssistance`, `partnerEmployee`, `partnerEmployer` |
| Scoring | `housingScore`, `housingLabel`, `employmentScore`, `employmentLabel`, `financialResilienceScore`, `financialLabel`, `compositeScore`, `compositeLabel` |
| Priority & Path | `priorityFlag`, `priorityMeaning`, `recommendedPath`, `pathMeaning`, `scoringSummary` |
| Disposition | `callDisposition`, `preferredDays`, `preferredTimes` |
| Eligibility | `eligibleBCDCOG`, `eligibleSiemer`, `eligibleMissionUnited`, `eligibleBarriersToEmployment` |

### 3. API Gateway

| Property | Value |
|----------|-------|
| Name | `stability360-actions-actions-api` |
| Type | REST API (inline OpenAPI Body) |
| Auth | API Key (`X-API-Key` header) |
| Region | `us-east-1` |
| Throttle | 50 req/s rate, 25 burst |
| Quota | 10,000 req/day |
| Logging | CloudWatch access logs + method logs |
| Tracing | X-Ray enabled |

**Endpoints:**

| Method | Path | Operation | Auth |
|--------|------|-----------|------|
| POST | `/intake/helper` | `intakeHelper` | API Key |
| POST | `/resources/search` | `resourceLookup` | API Key |
| GET | `/r/{pageId}` | `viewResults` | None (public) |

### 4. DynamoDB Table

| Property | Value |
|----------|-------|
| Table name | `stability360-actions` |
| Partition key | `record_id` (String) |
| Global Secondary Index | `RecordTypeIndex` — PK: `record_type`, SK: `created_at` |
| Billing | PAY_PER_REQUEST (on-demand) |
| Encryption | SSE enabled |
| Point-in-Time Recovery | Enabled |

### 5. S3 Bucket

| Property | Value |
|----------|-------|
| Bucket name | `stability360-actions-specs-us-east-1-{account}` |
| Purpose | OpenAPI spec storage + temporary HTML result pages |
| Versioning | Enabled |
| Lifecycle | `results/` prefix expires after 1 day |
| Encryption | AES256 |
| Public access | Fully blocked |

### 6. MCP Gateway (AgentCore)

| Property | Value |
|----------|-------|
| Gateway name | `stability360-actions-mcp-gw` |
| Protocol | MCP (version 2025-03-26) |
| Auth | CUSTOM_JWT (Connect OIDC) |
| Exception level | DEBUG |
| OIDC Discovery URL | `https://connect-configuration.my.connect.aws/.well-known/openid-configuration` |

### 7. CloudWatch Log Groups

| Log Group | Retention |
|-----------|-----------|
| `/aws/apigateway/stability360-actions` | 7 days |
| `/aws/lambda/stability360-actions-actions` | 7 days |
| `/aws/lambda/stability360-actions-case-updater` | 7 days |

### 8. CloudFormation Custom Resources

| Resource | Purpose |
|----------|---------|
| `ApiKeyValueRetrieval` | Retrieves API key value at stack creation |
| `OpenApiSpecUpload` | Fetches OpenAPI spec and uploads to S3 |
| `SpecBucketCleanup` | Empties S3 bucket on stack deletion |

---

## Amazon Q Connect Resources

### AI Agent

| Property | Value |
|----------|-------|
| Agent name | `stability360-actions-orchestration` |
| Model | Anthropic Claude Sonnet 4.5 |
| Region | `us-east-1` |

**Tools attached:**

| Tool | Type | Description |
|------|------|-------------|
| `resourceLookup` | MCP | Search community resources via Sophia API with auto-scoring |
| `intakeHelper` | MCP | Get next steps after search + record call disposition |
| Knowledge Base | RETRIEVE | Classify needs, validate ZIP codes, check partner employers |

### Orchestration Prompt

| Property | Value |
|----------|-------|
| Prompt name | `stability360-actions-orchestration` |

The orchestration prompt defines the full conversational flow:
- Emergency detection and fast-path handling
- Consent and intake field collection rules
- Resource search and results presentation
- Scoring and eligibility determination
- Disposition recording (live transfer, callback, self-service, etc.)

### Knowledge Base Seed Data

| Data Set | Content |
|----------|---------|
| `classify-need` | Need category classification rules |
| `validate-zip` | Service area ZIP code validation (Berkeley, Charleston, Dorchester counties) |
| `check-partner` | Thrive@Work partner employer list |
| `thriveatwork` | Thrive@Work program information |

### MCP Gateway Target

| Property | Value |
|----------|-------|
| Target name | `stability360-actions-api` |
| Type | OPEN_API_SCHEMA |
| Spec location | S3 bucket (openapi/actions-spec.yaml) |
| Credential | API key stored as gateway credential |

### Security Profile

| Property | Value |
|----------|-------|
| Profile name | `stability360-actions-AI-Agent` |
| Permissions | MCP tool access for resourceLookup and intakeHelper |

---

## External Integrations

### Sophia API (SC 211)

| Property | Value |
|----------|-------|
| URL | `https://api-prod-0.sophia-app.com/api/services/search/keyword-search` |
| Tenant | `sc-prod-0` |
| Origin | `https://www.sc211.org` |
| Auth | None (public API, Origin header required) |
| Returns | Community resource listings with organization, phone, address, hours, eligibility, service areas |

### Amazon Connect Instance

| Property | Value |
|----------|-------|
| Instance ID | `9b50ddcc-8510-441e-a9c8-96e9e9281105` |
| Region | `us-east-1` |
| Alias | `connect-configuration` |

### Q Connect Assistant

| Property | Value |
|----------|-------|
| Assistant ID | `170bfe70-4ed2-4abe-abb8-1d9f5213128d` |
| Region | `us-east-1` |

---

## API Specification

OpenAPI version 3.0.3 — 2 operations exposed to the AI agent via MCP:

### `POST /resources/search` (resourceLookup)
Search community resources by keyword and location. Automatically calculates eligibility scores when housing, income, and employment data is included.

**Required fields:** `keyword`

**Optional fields:** `zipCode`, `instance_id`, `contact_id`, `firstName`, `lastName`, `contactMethod`, `contactInfo`, `employmentStatus`, `employer`, `age`, `childrenUnder18`, `monthlyIncome`, `housingSituation` (plus additional properties)

### `POST /intake/helper` (intakeHelper)
Get next steps after resource search and record call dispositions.

**Required fields:** `action` (values: `getNextSteps` or `recordDisposition`)

**Optional fields:** `disposition` (values: `live_transfer`, `callback`, `additional_search`, `self_service`, `out_of_area`, `declined`, `emergency`), `instance_id`, `contact_id`, `firstName`, `lastName`, `keyword`, `zipCode`, `contactMethod`, `contactInfo`, `employmentStatus`, `employer`, `preferredDays`, `preferredTimes`

---

## IAM Permissions Summary

### Actions Lambda Role

| Permission | Scope |
|------------|-------|
| CloudWatch Logs | Write to actions log group |
| DynamoDB | PutItem, GetItem, UpdateItem, Query on actions table |
| Amazon Connect | UpdateContactAttributes, StartTaskContact, ListQueues, GetCurrentMetricData |
| Customer Profiles | SearchProfiles, CreateProfile, UpdateProfile |
| Connect Cases | CreateCase, UpdateCase, SearchCases, ListFields, BatchGetField |
| S3 | PutObject, GetObject for results/ prefix |
| X-Ray | PutTraceSegments, PutTelemetryRecords |

### Case Updater Lambda Role

| Permission | Scope |
|------------|-------|
| CloudWatch Logs | Write to case-updater log group |
| Connect Cases | UpdateCase, GetCase |

### MCP Gateway Role

| Permission | Scope |
|------------|-------|
| S3 | GetObject for OpenAPI spec |
| Secrets Manager | GetSecretValue for bedrock-agentcore-identity |
| AgentCore | Token vault operations |
| API Gateway | Invoke actions API |

---

## Call Flow Summary

1. **Caller dials in** — Amazon Connect contact flow receives the call.
2. **Lex V2 bot** activates QInConnectIntent and hands off to the Q Connect AI agent.
3. **AI agent** (Claude Sonnet 4.5) follows the orchestration prompt:
   - Greets the caller and checks for emergency signals (disconnected utilities, eviction, homelessness, etc.).
   - Collects intake fields: name, ZIP code, contact info, employment, and category-specific fields.
   - Calls `resourceLookup` — queries the Sophia API for community resources, calculates proximity by distance, and auto-scores eligibility.
   - Calls `intakeHelper(getNextSteps)` — checks family coach availability in the Connect queue.
   - Calls `intakeHelper(recordDisposition)` — records the call outcome and triggers automation (creates Customer Profile, Connect Task, and Connect Case).
4. **Post-call** — The contact flow invokes the Case Updater Lambda, which writes all contact attributes (37 fields) into the Connect Case record.
5. **Results delivery** — The caller receives an SMS or email with a link to view their resource results on a temporary HTML page hosted in S3.
