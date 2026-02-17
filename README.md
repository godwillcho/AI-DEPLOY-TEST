# Stability360 — Amazon Connect AI Deployment

Automated deployment of the Stability360 Thrive@Work AI-powered self-service chat system using Amazon Connect, Q Connect, Lex V2, and MCP.

## Prerequisites

- Python 3.10+
- AWS CLI configured with credentials (`aws configure`)
- An Amazon Connect instance with Q Connect enabled
- `boto3` installed (`pip install boto3`)

## Project Structure

```
steps/thrive-at-work/
  deploy.py                    # Main deployment script (all 19 steps)
  thrive-at-work-stack.yaml    # CloudFormation template
  prompts/orchestration-prompt.txt
  openapi/employee-lookup-spec.yaml
  lambda/
    employee_lookup/index.py   # Employee lookup Lambda
    intake_bot/lambda_function.py  # Intake bot Lambda
    chat_widget/lambda_function.py # Chat widget test page
  seed-data/
    employees.json             # Sample employee records
    kb-documents/              # Knowledge base documents
docs/                          # Architecture & PRD docs
roadmap/                       # Implementation roadmap
```

## Deployment Commands

### Full Deployment (all 19 steps)

```bash
cd steps/thrive-at-work

# Dev environment (us-west-2)
python deploy.py \
  --stack-name stability360-thrive-at-work \
  --region us-west-2 \
  --environment dev \
  --enable-mcp \
  --connect-instance-id <CONNECT_INSTANCE_ID>

# Prod environment (us-east-1)
python deploy.py \
  --stack-name stability360-thrive-at-work-prod \
  --region us-east-1 \
  --environment prod \
  --enable-mcp \
  --connect-instance-id <CONNECT_INSTANCE_ID>
```

### Partial / Targeted Deployments

```bash
# Deploy stack only (no MCP gateway)
python deploy.py --stack-name <STACK> --region <REGION>

# Deploy stack + MCP gateway (no Connect)
python deploy.py --stack-name <STACK> --region <REGION> --enable-mcp

# Seed DynamoDB + KB data only
python deploy.py --stack-name <STACK> --region <REGION> --seed-only

# Update Lambda function code only
python deploy.py --stack-name <STACK> --region <REGION> --update-code-only

# Register MCP with Connect only
python deploy.py --stack-name <STACK> --region <REGION> \
  --connect-only --connect-instance-id <ID>

# Update AI agent orchestration prompt only
python deploy.py --stack-name <STACK> --region <REGION> --update-prompt

# Create/update Lex bot only
python deploy.py --stack-name <STACK> --region <REGION> \
  --create-bot --connect-instance-id <ID>

# Link S3 KB bucket to Q Connect only
python deploy.py --stack-name <STACK> --region <REGION> \
  --integrate-kb --connect-instance-id <ID>
```

### Teardown

```bash
# Delete CloudFormation stack only
python deploy.py --stack-name <STACK> --region <REGION> --delete

# Full teardown — removes ALL resources (bots, flows, AI agent, KB, MCP, CFN stack)
python deploy.py --stack-name <STACK> --region <REGION> \
  --destroy-all --connect-instance-id <ID>
```

## Deployment Steps (full run)

| Step | Description |
|------|-------------|
| 1 | Deploy CloudFormation stack |
| 2 | Retrieve stack outputs |
| 3 | Update Lambda code (employee-lookup + intake-bot) |
| 4 | Seed DynamoDB with employee data |
| 5 | Setup KB bucket + seed documents |
| 6 | Upload OpenAPI spec to S3 |
| 7 | Register API key in AgentCore Identity |
| 8 | Configure MCP REST API target |
| 9 | Update gateway AllowedAudience |
| 10 | Register MCP server with Connect |
| 11 | Enable Customer Profiles |
| 12 | Create security profile |
| 13 | Create orchestration prompt |
| 14 | Link S3 KB bucket to Q Connect |
| 15 | Create AI Agent |
| 16 | Generate MCP tool config |
| 17 | Create Lex bot (Stability360Bot) |
| 18 | Create Intake bot (IntakeBot) |
| 19 | Create contact flow |

## Multi-Environment Support

Resources are namespaced by `--stack-name` to allow side-by-side deployments:

| Resource | Dev | Prod |
|----------|-----|------|
| CFN Stack | `stability360-thrive-at-work` | `stability360-thrive-at-work-prod` |
| DynamoDB | `...-employees` | `...-prod-employees` |
| AI Agent | `...-agent` | `...-prod-agent` |
| Lex Bot | `...-bot` | `...-prod-bot` |
| Intake Bot | `...-intake-bot` | `...-prod-intake-bot` |
| Contact Flow | `...-self-service` | `...-prod-self-service` |
| Security Profile | `...-AI-Agent` | `...-prod-AI-Agent` |

## Current Deployments

| Environment | Region | Stack Name | Connect Instance |
|-------------|--------|------------|------------------|
| Dev | us-west-2 | `stability360-thrive-at-work` | `e75a053a-60c7-45f3-83f7-a24df6d3b52d` |
| Prod | us-east-1 | `stability360-thrive-at-work-prod` | `9b50ddcc-8510-441e-a9c8-96e9e9281105` |
