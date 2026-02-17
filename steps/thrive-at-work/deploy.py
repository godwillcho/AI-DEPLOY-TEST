#!/usr/bin/env python3
"""
Stability360 — Thrive@Work Stack Deployment Script

Deploys the CloudFormation stack, configures the MCP server (REST API target
with OpenAPI schema + API key auth), and optionally integrates with Amazon Connect.

Deployment steps:
  No MCP:  1-5  (CFN, outputs, Lambda, DynamoDB, KB bucket)
  MCP:     1-8  (+ OpenAPI upload, API key credential, REST API target)
  Connect: 1-20 (+ audience, registration, profiles, security profile, prompt,
                  KB integration, AI agent, tool config, Lex bot, intake bot,
                  contact flow)

Usage:
    python deploy.py                                            # Deploy stack (no MCP gateway)
    python deploy.py --enable-mcp                               # Deploy + MCP gateway (AWS_IAM)
    python deploy.py --enable-mcp --connect-instance-id <ID>    # Deploy + MCP + Connect (CUSTOM_JWT)
    python deploy.py --seed-only                                # Only seed data
    python deploy.py --update-code-only                         # Only update Lambda code
    python deploy.py --connect-only --connect-instance-id <ID>  # Only register MCP with Connect
    python deploy.py --update-prompt                            # Only update orchestration prompt on AI agent
    python deploy.py --create-bot --connect-instance-id <ID>    # Only create Lex V2 bot
    python deploy.py --integrate-kb --connect-instance-id <ID>  # Only link S3 KB bucket to Q Connect
    python deploy.py --delete                                   # Delete CFN stack only
    python deploy.py --destroy-all --connect-instance-id <ID>   # Full teardown (all resources)
    python deploy.py --stack-name MY_STACK                      # Custom stack name
    python deploy.py --region us-west-2                         # Custom region
"""

import argparse
import boto3
from botocore.exceptions import ClientError
import io
import json
import logging
import os
import sys
import time
import zipfile

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt='%H:%M:%S')
logger = logging.getLogger('deploy')

# Quieten noisy boto/urllib3 loggers
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(SCRIPT_DIR, 'thrive-at-work-stack.yaml')
LAMBDA_CODE_DIR = os.path.join(SCRIPT_DIR, 'lambda', 'employee_lookup')
INTAKE_LAMBDA_CODE_DIR = os.path.join(SCRIPT_DIR, 'lambda', 'intake_bot')
SEED_DATA_FILE = os.path.join(SCRIPT_DIR, 'seed-data', 'employees.json')
KB_DOCUMENTS_DIR = os.path.join(SCRIPT_DIR, 'seed-data', 'kb-documents')
OPENAPI_SPEC_TEMPLATE = os.path.join(SCRIPT_DIR, 'openapi', 'employee-lookup-spec.yaml')

DEFAULT_STACK_NAME = 'stability360-thrive-at-work'
DEFAULT_REGION = 'us-west-2'
DEFAULT_ENVIRONMENT = 'dev'

POLL_INTERVAL = 10  # seconds between CloudFormation status checks

OPENAPI_S3_KEY = 'openapi/employee-lookup-spec.yaml'

# MCP tool constants (operation ID is fixed by the OpenAPI spec)
MCP_TOOL_OPERATION = 'employeeLookup'
MCP_TOOL_CONFIG_FILE = os.path.join(SCRIPT_DIR, 'ai-agent-tool-config.json')

# Custom orchestration prompt
ORCHESTRATION_PROMPT_FILE = os.path.join(SCRIPT_DIR, 'prompts', 'orchestration-prompt.txt')
ORCHESTRATION_PROMPT_MODEL = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'

# Lex V2 Bot constants (not derived from stack name)
LEX_BOT_LOCALE = 'en_US'
LEX_BOT_NLU_THRESHOLD = 0.40
LEX_BOT_IDLE_SESSION_TTL = 300  # 5 minutes
LEX_BOT_ALIAS_NAME = 'live'
LEX_BOT_BUILD_POLL_INTERVAL = 5   # seconds between build status checks
LEX_BOT_BUILD_TIMEOUT = 120       # max seconds to wait for build
INTAKE_BOT_ALIAS_NAME = 'live'

# Q Connect Knowledge Base constants (not derived from stack name)
KB_S3_PRINCIPALS = [
    'app-integrations.amazonaws.com',
    'wisdom.amazonaws.com',
]

# ---------------------------------------------------------------------------
# Resource names — derived from stack name for multi-environment portability.
# These globals are set by init_resource_names() which MUST be called before
# any deployment function.  Every name is prefixed with the stack name so
# multiple stacks can coexist in the same account/region without collision.
# ---------------------------------------------------------------------------

API_KEY_CREDENTIAL_NAME = None
MCP_TARGET_NAME = None
AI_AGENT_NAME = None
AI_AGENT_DESCRIPTION = None
MCP_TOOL_NAME = None
MCP_TOOL_NAME_SAFE = None
ORCHESTRATION_PROMPT_NAME = None
LEX_BOT_NAME = None
LEX_BOT_DESCRIPTION = None
LEX_BOT_ROLE_NAME = None
INTAKE_BOT_NAME = None
INTAKE_BOT_DESCRIPTION = None
CONTACT_FLOW_NAME = None
CONTACT_FLOW_DESCRIPTION = None
# IMPORTANT: DataIntegration and KB MUST share the same name — the Amazon
# Connect console resolves integration details by looking up a DataIntegration
# whose name matches the KB name.
KB_INTEGRATION_NAME = None
KB_DATA_INTEGRATION_NAME = None
KB_INTEGRATION_DESCRIPTION = None
SECURITY_PROFILE_NAME = None


def init_resource_names(stack_name):
    """Derive all resource names from the stack name.

    Must be called once after CLI arg parsing, before any deployment
    function.  This allows multiple stacks to coexist in the same
    account/region without name collisions.
    """
    # pylint: disable=global-statement
    global API_KEY_CREDENTIAL_NAME, MCP_TARGET_NAME
    global AI_AGENT_NAME, AI_AGENT_DESCRIPTION
    global MCP_TOOL_NAME, MCP_TOOL_NAME_SAFE
    global ORCHESTRATION_PROMPT_NAME
    global LEX_BOT_NAME, LEX_BOT_DESCRIPTION, LEX_BOT_ROLE_NAME
    global INTAKE_BOT_NAME, INTAKE_BOT_DESCRIPTION
    global CONTACT_FLOW_NAME, CONTACT_FLOW_DESCRIPTION
    global KB_INTEGRATION_NAME, KB_DATA_INTEGRATION_NAME, KB_INTEGRATION_DESCRIPTION
    global SECURITY_PROFILE_NAME

    API_KEY_CREDENTIAL_NAME = f'{stack_name}-api-key'
    MCP_TARGET_NAME = f'{stack_name}-api'

    AI_AGENT_NAME = f'{stack_name}-agent'
    AI_AGENT_DESCRIPTION = f'AI agent for {stack_name} employee services'

    MCP_TOOL_NAME = f'{MCP_TARGET_NAME}___employeeLookup'
    MCP_TOOL_NAME_SAFE = MCP_TOOL_NAME.replace('-', '_')

    ORCHESTRATION_PROMPT_NAME = f'{stack_name}-orchestration'

    LEX_BOT_NAME = f'{stack_name}-bot'
    LEX_BOT_DESCRIPTION = (
        f'Lex V2 bot for {stack_name} — routes voice/chat to '
        'Q Connect AI agent via AMAZON.QinConnectIntent'
    )
    LEX_BOT_ROLE_NAME = f'{stack_name}-lex-role'

    INTAKE_BOT_NAME = f'{stack_name}-intake-bot'
    INTAKE_BOT_DESCRIPTION = (
        f'Intake router for {stack_name} — presents service menu and '
        'routes customers to the appropriate AI agent'
    )

    CONTACT_FLOW_NAME = f'{stack_name}-self-service'
    CONTACT_FLOW_DESCRIPTION = (
        f'{stack_name} self-service chat flow — intake routing + '
        'CreateWisdomSession + ConnectParticipantWithLexBot'
    )

    KB_INTEGRATION_NAME = f'{stack_name}-kb'
    KB_DATA_INTEGRATION_NAME = KB_INTEGRATION_NAME  # Must equal KB name
    KB_INTEGRATION_DESCRIPTION = (
        f'{stack_name} knowledge base — S3-backed document repository '
        'for programs, eligibility, routing, guardrails, and FAQ content'
    )

    SECURITY_PROFILE_NAME = f'{stack_name}-AI-Agent'

# ---------------------------------------------------------------------------
# CloudFormation helpers
# ---------------------------------------------------------------------------


def stack_exists(cf_client, stack_name):
    """Check if a CloudFormation stack exists (and is not deleted)."""
    try:
        resp = cf_client.describe_stacks(StackName=stack_name)
        status = resp['Stacks'][0]['StackStatus']
        if status == 'DELETE_COMPLETE':
            return False
        return True
    except cf_client.exceptions.ClientError:
        return False


def get_stack_status(cf_client, stack_name):
    """Return current stack status string."""
    resp = cf_client.describe_stacks(StackName=stack_name)
    return resp['Stacks'][0]['StackStatus']


def deploy_stack(cf_client, stack_name, template_body, environment,
                 enable_mcp=False, enable_connect=False,
                 connect_instance_id='', connect_instance_url=''):
    """Create or update CloudFormation stack."""
    params = [
        {'ParameterKey': 'Environment', 'ParameterValue': environment},
        {'ParameterKey': 'EnableMcpGateway', 'ParameterValue': 'true' if enable_mcp else 'false'},
        {'ParameterKey': 'EnableConnectIntegration', 'ParameterValue': 'true' if enable_connect else 'false'},
        {'ParameterKey': 'ConnectInstanceId', 'ParameterValue': connect_instance_id},
        {'ParameterKey': 'ConnectInstanceUrl', 'ParameterValue': connect_instance_url},
    ]
    kwargs = {
        'StackName': stack_name,
        'TemplateBody': template_body,
        'Parameters': params,
        'Capabilities': ['CAPABILITY_NAMED_IAM'],
    }

    if stack_exists(cf_client, stack_name):
        status = get_stack_status(cf_client, stack_name)

        if status == 'ROLLBACK_COMPLETE':
            logger.warning('Stack is in ROLLBACK_COMPLETE — deleting before recreating...')
            cf_client.delete_stack(StackName=stack_name)
            wait_for_stack(cf_client, stack_name, target='DELETE_COMPLETE')
            logger.info('Deleted. Creating stack...')
            cf_client.create_stack(**kwargs)
            return 'CREATE'

        logger.info('Stack exists (status: %s) — updating...', status)
        try:
            cf_client.update_stack(**kwargs)
            return 'UPDATE'
        except cf_client.exceptions.ClientError as e:
            if 'No updates are to be performed' in str(e):
                logger.info('No changes detected — stack is up to date.')
                return 'NOOP'
            raise
    else:
        logger.info('Stack does not exist — creating...')
        cf_client.create_stack(**kwargs)
        return 'CREATE'


def wait_for_stack(cf_client, stack_name, target=None):
    """Poll CloudFormation until stack reaches a terminal state."""
    logger.info('Waiting for stack operation to complete...')
    while True:
        try:
            status = get_stack_status(cf_client, stack_name)
        except cf_client.exceptions.ClientError:
            if target == 'DELETE_COMPLETE':
                logger.info('Stack deleted.')
                return 'DELETE_COMPLETE'
            raise

        logger.info('  Status: %s', status)

        if status == target:
            return status

        if status.endswith('_COMPLETE') or status.endswith('_FAILED'):
            return status

        time.sleep(POLL_INTERVAL)


def get_stack_outputs(cf_client, stack_name):
    """Return stack outputs as a dict."""
    resp = cf_client.describe_stacks(StackName=stack_name)
    outputs = resp['Stacks'][0].get('Outputs', [])
    return {o['OutputKey']: o['OutputValue'] for o in outputs}


# ---------------------------------------------------------------------------
# Lambda code update
# ---------------------------------------------------------------------------


def package_lambda(code_dir):
    """Zip the contents of a directory into a bytes buffer."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(code_dir):
            # Skip __pycache__ directories
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for f in files:
                if f.endswith('.pyc'):
                    continue
                full_path = os.path.join(root, f)
                arc_name = os.path.relpath(full_path, code_dir)
                zf.write(full_path, arc_name)
    buf.seek(0)
    return buf.read()


def update_lambda_code(lambda_client, function_name, code_dir):
    """Package and deploy Lambda function code."""
    logger.info('Packaging Lambda code from %s...', code_dir)
    zip_bytes = package_lambda(code_dir)
    logger.info('Zip size: %s bytes', f'{len(zip_bytes):,}')

    logger.info('Updating function: %s...', function_name)
    resp = lambda_client.update_function_code(
        FunctionName=function_name,
        ZipFile=zip_bytes,
    )
    logger.info('Updated. Version: %s', resp.get('Version', 'N/A'))


# ---------------------------------------------------------------------------
# DynamoDB seeding
# ---------------------------------------------------------------------------


def seed_dynamodb(dynamodb_resource, table_name, seed_file):
    """Load seed data JSON into DynamoDB table using batch writer."""
    logger.info('Reading seed data from %s...', seed_file)
    with open(seed_file, 'r') as f:
        employees = json.load(f)

    logger.info('Seeding %d employees into %s...', len(employees), table_name)
    table = dynamodb_resource.Table(table_name)

    with table.batch_writer() as batch:
        for emp in employees:
            batch.put_item(Item=emp)

    logger.info('Seeded %d employees successfully.', len(employees))


# ---------------------------------------------------------------------------
# API Key retrieval
# ---------------------------------------------------------------------------


def get_api_key_value(apigw_client, api_key_id):
    """Retrieve the actual API key value (for testing)."""
    resp = apigw_client.get_api_key(apiKey=api_key_id, includeValue=True)
    return resp['value']


# ---------------------------------------------------------------------------
# S3 KB bucket initialization
# ---------------------------------------------------------------------------


KB_FOLDER_STRUCTURE = [
    'thriveatwork/programs/',
    'thriveatwork/eligibility/',
    'thriveatwork/routing/',
    'thriveatwork/guardrails/',
    'thriveatwork/faq/',
]


def init_kb_bucket(s3_client, bucket_name):
    """Create the KB folder structure in S3 (empty marker objects)."""
    for folder in KB_FOLDER_STRUCTURE:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=folder,
            Body=b'',
        )
        logger.info('Created: s3://%s/%s', bucket_name, folder)


# Mapping from local document subdirectory → S3 key prefix
KB_DOCUMENT_FOLDER_MAP = {
    'programs': 'thriveatwork/programs/',
    'eligibility': 'thriveatwork/eligibility/',
    'routing': 'thriveatwork/routing/',
    'guardrails': 'thriveatwork/guardrails/',
    'faq': 'thriveatwork/faq/',
}


def seed_kb_documents(s3_client, bucket_name):
    """Upload sample KB documents from seed-data/kb-documents/ to S3.

    Walks the KB_DOCUMENTS_DIR directory, maps each subfolder to the
    corresponding S3 prefix, and uploads all files. Supported file types
    are .txt, .html, .pdf, and .docx.

    Overwrites existing files with the same key on every run.
    """
    if not os.path.isdir(KB_DOCUMENTS_DIR):
        logger.warning('KB documents directory not found: %s', KB_DOCUMENTS_DIR)
        return 0

    allowed_extensions = {'.txt', '.html', '.htm', '.pdf', '.docx'}
    uploaded = 0

    for subfolder, s3_prefix in KB_DOCUMENT_FOLDER_MAP.items():
        local_dir = os.path.join(KB_DOCUMENTS_DIR, subfolder)
        if not os.path.isdir(local_dir):
            continue

        for filename in sorted(os.listdir(local_dir)):
            _, ext = os.path.splitext(filename)
            if ext.lower() not in allowed_extensions:
                continue

            local_path = os.path.join(local_dir, filename)
            s3_key = f'{s3_prefix}{filename}'

            # Determine content type
            content_types = {
                '.txt': 'text/plain',
                '.html': 'text/html',
                '.htm': 'text/html',
                '.pdf': 'application/pdf',
                '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            }
            content_type = content_types.get(ext.lower(), 'application/octet-stream')

            with open(local_path, 'rb') as f:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=f.read(),
                    ContentType=content_type,
                )
            logger.info('Uploaded: s3://%s/%s', bucket_name, s3_key)
            uploaded += 1

    return uploaded


# ---------------------------------------------------------------------------
# OpenAPI spec upload
# ---------------------------------------------------------------------------


def upload_openapi_spec(s3_client, bucket_name, api_base_url):
    """Read OpenAPI spec template, fill in the API server URL, upload to S3."""
    with open(OPENAPI_SPEC_TEMPLATE, 'r') as f:
        spec_content = f.read()

    # Replace the server URL placeholder
    spec_content = spec_content.replace('${SERVER_URL}', api_base_url)

    s3_uri = f's3://{bucket_name}/{OPENAPI_S3_KEY}'
    logger.info('Uploading OpenAPI spec to %s...', s3_uri)
    s3_client.put_object(
        Bucket=bucket_name,
        Key=OPENAPI_S3_KEY,
        Body=spec_content.encode('utf-8'),
        ContentType='application/x-yaml',
    )
    logger.info('OpenAPI spec uploaded.')
    return s3_uri


# ---------------------------------------------------------------------------
# AgentCore — API Key Credential Provider
# ---------------------------------------------------------------------------


def register_api_key_credential(agentcore_client, credential_name, api_key_value):
    """Register an API key in AgentCore Identity so the gateway can use it for outbound auth.

    Idempotent: if a credential with the same name already exists, updates it.
    Returns the credential provider ARN.
    """
    # Check if already exists
    try:
        resp = agentcore_client.list_api_key_credential_providers()
        for cred in resp.get('credentialProviders', []):
            if cred.get('name') == credential_name:
                cred_arn = cred['credentialProviderArn']
                logger.info('API key credential already exists: %s', cred_arn)
                # Update the key value in case it changed
                agentcore_client.update_api_key_credential_provider(
                    name=credential_name,
                    apiKey=api_key_value,
                )
                logger.info('API key credential updated.')
                return cred_arn
    except ClientError:
        logger.debug('Could not list API key credentials', exc_info=True)

    # Create new
    logger.info('Registering API key credential: %s', credential_name)
    resp = agentcore_client.create_api_key_credential_provider(
        name=credential_name,
        apiKey=api_key_value,
    )
    cred_arn = resp['credentialProviderArn']
    logger.info('Registered. ARN: %s', cred_arn)
    return cred_arn


# ---------------------------------------------------------------------------
# AgentCore — MCP Gateway Target (REST API with OpenAPI schema)
# ---------------------------------------------------------------------------


def find_existing_target(agentcore_client, gateway_id, target_name):
    """Find an existing gateway target by name.

    NOTE: list_gateway_targets has a known issue where it may return empty
    results even when targets exist. We also check targets from the 'items'
    key and handle pagination.
    """
    try:
        resp = agentcore_client.list_gateway_targets(gatewayIdentifier=gateway_id)
        # The API may return targets under 'targets' or 'items' key
        targets = resp.get('targets', []) or resp.get('items', [])
        for t in targets:
            if t.get('name') == target_name:
                return t.get('targetId')
    except ClientError:
        logger.debug('Could not list gateway targets', exc_info=True)
    return None


def create_or_update_mcp_target(agentcore_client, gateway_id, target_name,
                                openapi_s3_uri, api_key_credential_arn):
    """Create (or update) the MCP gateway target as a REST API with OpenAPI schema.

    This configures the gateway to route MCP tool calls through the API Gateway
    using the OpenAPI spec and API key for auth (matching the AWS workshop pattern).
    Handles the case where the target already exists (create-or-update pattern).
    """
    target_config = {
        'mcp': {
            'openApiSchema': {
                's3': {
                    'uri': openapi_s3_uri,
                }
            }
        }
    }

    cred_config = [
        {
            'credentialProviderType': 'API_KEY',
            'credentialProvider': {
                'apiKeyCredentialProvider': {
                    'providerArn': api_key_credential_arn,
                    'credentialParameterName': 'x-api-key',
                    'credentialLocation': 'HEADER',
                }
            }
        }
    ]

    target_description = (
        'Stability360 Thrive@Work Employee Lookup API — '
        'REST API target with OpenAPI schema and API key authentication'
    )

    # Check if target already exists via list
    existing_target_id = find_existing_target(agentcore_client, gateway_id, target_name)

    if existing_target_id:
        logger.info('Target %s already exists (ID: %s) — updating...', target_name, existing_target_id)
        agentcore_client.update_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=existing_target_id,
            name=target_name,
            description=target_description,
            targetConfiguration=target_config,
            credentialProviderConfigurations=cred_config,
        )
        logger.info('Target updated.')
        return existing_target_id

    # Try creating — handle "already exists" gracefully (list_gateway_targets can be unreliable)
    try:
        logger.info('Creating REST API target: %s', target_name)
        resp = agentcore_client.create_gateway_target(
            gatewayIdentifier=gateway_id,
            name=target_name,
            description=target_description,
            targetConfiguration=target_config,
            credentialProviderConfigurations=cred_config,
        )
        target_id = resp.get('targetId', 'N/A')
        logger.info('Target created. ID: %s', target_id)
        return target_id
    except Exception as e:
        err_str = str(e).lower()
        if 'already exists' in err_str or 'conflict' in err_str or 'duplicate' in err_str:
            logger.info('Target already exists (list was empty due to API quirk).')
            logger.info('Target configuration is already in place.')
            return None
        raise


# ---------------------------------------------------------------------------
# Amazon Connect — MCP Server Registration
# ---------------------------------------------------------------------------


def get_connect_instance_url(connect_client, instance_id):
    """Look up the Amazon Connect instance URL from its ID."""
    resp = connect_client.describe_instance(InstanceId=instance_id)
    return resp['Instance']['InstanceAccessUrl']


def update_gateway_audience(session, gateway_id, connect_instance_url):
    """Update the MCP Gateway inbound AllowedAudience to the Gateway ID.

    CFN creates the gateway with ConnectInstanceUrl as a placeholder audience
    because the Gateway ID isn't known until after creation. This function
    corrects it to use the actual Gateway ID (per the AWS workshop pattern).
    """
    agentcore_client = session.client('bedrock-agentcore-control')

    # Verify current config
    gw = agentcore_client.get_gateway(gatewayIdentifier=gateway_id)
    current_auth_type = gw.get('authorizerType', '')
    if current_auth_type != 'CUSTOM_JWT':
        logger.info('Gateway auth is %s — no audience update needed.', current_auth_type)
        return

    current_config = gw.get('authorizerConfiguration', {})
    jwt_config = current_config.get('customJWTAuthorizer', {})
    current_audiences = jwt_config.get('allowedAudience', [])

    if current_audiences == [gateway_id]:
        logger.info('AllowedAudience already set to Gateway ID.')
        return

    logger.info('Updating AllowedAudience from %s to [%s]...', current_audiences, gateway_id)
    update_kwargs = {
        'gatewayIdentifier': gateway_id,
        'name': gw['name'],
        'roleArn': gw['roleArn'],
        'protocolType': gw['protocolType'],
        'authorizerType': gw['authorizerType'],
        'authorizerConfiguration': {
            'customJWTAuthorizer': {
                'discoveryUrl': jwt_config['discoveryUrl'],
                'allowedAudience': [gateway_id],
            }
        },
    }
    # Preserve exceptionLevel if set
    if gw.get('exceptionLevel'):
        update_kwargs['exceptionLevel'] = gw['exceptionLevel']
    agentcore_client.update_gateway(**update_kwargs)
    logger.info('AllowedAudience updated to Gateway ID.')


def find_existing_mcp_app(appintegrations_client, namespace, app_name):
    """Check if an MCP_SERVER application already exists (by namespace or name)."""
    try:
        paginator = appintegrations_client.get_paginator('list_applications')
        for page in paginator.paginate():
            for app in page.get('Applications', []):
                if app.get('Namespace') == namespace or app.get('Name') == app_name:
                    return app.get('Arn'), app.get('Id')
    except ClientError:
        logger.debug('Could not list existing applications', exc_info=True)
    return None, None


def find_existing_connect_association(connect_client, instance_id, app_arn):
    """Check if the application is already associated with the Connect instance."""
    try:
        paginator = connect_client.get_paginator('list_integration_associations')
        for page in paginator.paginate(
            InstanceId=instance_id,
            IntegrationType='APPLICATION',
        ):
            for assoc in page.get('IntegrationAssociationSummaryList', []):
                if assoc.get('IntegrationArn') == app_arn:
                    return assoc.get('IntegrationAssociationId')
    except ClientError:
        logger.debug('Could not list integration associations', exc_info=True)
    return None


def register_mcp_with_connect(session, connect_instance_id, gateway_url, gateway_id, stack_name):
    """Register the MCP Gateway as a third-party app in Amazon Connect."""
    appintegrations_client = session.client('appintegrations')
    connect_client = session.client('connect')

    namespace = gateway_id
    app_name = f'{stack_name} MCP Server'

    # Check if already registered
    existing_arn, existing_id = find_existing_mcp_app(appintegrations_client, namespace, app_name)
    if existing_arn:
        logger.info('MCP app already exists: %s', existing_arn)
        app_arn = existing_arn
    else:
        logger.info('Creating MCP_SERVER application...')
        logger.info('  Name:      %s', app_name)
        logger.info('  Namespace: %s', namespace)
        logger.info('  AccessUrl: %s', gateway_url)
        resp = appintegrations_client.create_application(
            Name=app_name,
            Namespace=namespace,
            ApplicationType='MCP_SERVER',
            Description='Stability360 Thrive@Work MCP tool server via Bedrock AgentCore Gateway',
            ApplicationSourceConfig={
                'ExternalUrlConfig': {
                    'AccessUrl': gateway_url,
                }
            },
            Permissions=[],
        )
        app_arn = resp['Arn']
        app_id = resp['Id']
        logger.info('Created. ARN: %s', app_arn)
        logger.info('App ID: %s', app_id)

    # Associate with Connect instance
    existing_assoc = find_existing_connect_association(
        connect_client, connect_instance_id, app_arn,
    )
    if existing_assoc:
        logger.info('Already associated with Connect: %s', existing_assoc)
    else:
        logger.info('Associating with Connect instance %s...', connect_instance_id)
        assoc_resp = connect_client.create_integration_association(
            InstanceId=connect_instance_id,
            IntegrationType='APPLICATION',
            IntegrationArn=app_arn,
        )
        logger.info('Associated. ID: %s', assoc_resp['IntegrationAssociationId'])

    return app_arn


# ---------------------------------------------------------------------------
# Amazon Connect — Customer Profiles
# ---------------------------------------------------------------------------


def enable_customer_profiles(session, connect_instance_id, stack_name):
    """Enable Customer Profiles on the Connect instance if not already enabled.

    Creates a Customer Profiles domain and integrates it with the Connect instance
    using the 'Auto-associate profiles only' template (CTR-AutoAssociateOnly).
    Never fails — logs warnings and continues if any step encounters issues.
    """
    profiles_client = session.client('customer-profiles')
    domain_name = f'{stack_name}-profiles'

    # Step 1: Create or verify Customer Profiles domain
    try:
        profiles_client.get_domain(DomainName=domain_name)
        logger.info('Customer Profiles domain already exists: %s', domain_name)
    except Exception as e:
        if 'ResourceNotFoundException' in type(e).__name__ or 'not found' in str(e).lower():
            try:
                logger.info('Creating Customer Profiles domain: %s', domain_name)
                profiles_client.create_domain(
                    DomainName=domain_name,
                    DefaultExpirationDays=365,
                )
                logger.info('Domain created.')
            except Exception as create_err:
                logger.warning('Could not create Customer Profiles domain: %s', create_err)
                logger.info('You may need to enable Customer Profiles manually in the Connect console.')
                return
        else:
            logger.warning('Could not check Customer Profiles domain: %s', e)
            logger.info('You may need to enable Customer Profiles manually in the Connect console.')
            return

    # Step 2: Associate the Connect instance with the domain via put_integration
    # Uses CTR-AutoAssociateOnly template (auto-associates contacts with existing profiles only)
    connect_instance_arn = (
        f'arn:aws:connect:{session.region_name}:'
        f'{session.client("sts").get_caller_identity()["Account"]}:'
        f'instance/{connect_instance_id}'
    )
    try:
        # Check if integration already exists
        existing = profiles_client.list_integrations(DomainName=domain_name)
        for item in existing.get('Items', []):
            if item.get('Uri') == connect_instance_arn:
                logger.info('Connect integration already exists for domain %s.', domain_name)
                return

        logger.info('Associating Connect instance with Customer Profiles domain...')
        profiles_client.put_integration(
            DomainName=domain_name,
            Uri=connect_instance_arn,
            ObjectTypeName='CTR-AutoAssociateOnly',
        )
        logger.info('Customer Profiles integration enabled (Auto-associate only).')
    except Exception as e:
        err_str = str(e).lower()
        if 'duplicate' in err_str or 'already' in err_str or 'conflict' in err_str:
            logger.info('Customer Profiles integration already exists.')
        else:
            logger.warning('Could not associate Connect with Customer Profiles: %s', e)
            logger.info('You may need to enable Customer Profiles manually in the Connect console.')


# ---------------------------------------------------------------------------
# Amazon Connect — AI Agent Security Profile (MCP tool permissions)
# ---------------------------------------------------------------------------


def find_or_create_security_profile(connect_client, instance_id,
                                     profile_name=None):
    """Find or create a security profile for the AI agent.

    Returns the security_profile_id, or None on failure.
    """
    profile_name = profile_name or SECURITY_PROFILE_NAME
    # Search existing profiles
    try:
        paginator = connect_client.get_paginator('list_security_profiles')
        for page in paginator.paginate(InstanceId=instance_id):
            for sp in page.get('SecurityProfileSummaryList', []):
                if sp.get('Name') == profile_name:
                    logger.info('Security profile found: %s (ID: %s)',
                                profile_name, sp['Id'])
                    return sp['Id']
    except ClientError:
        logger.debug('Could not list security profiles', exc_info=True)

    # Create if not found
    logger.info('Creating security profile: %s', profile_name)
    try:
        resp = connect_client.create_security_profile(
            SecurityProfileName=profile_name,
            Description='Security profile for Stability360 AI Agent with MCP tool access',
            InstanceId=instance_id,
        )
        sp_id = resp.get('SecurityProfileId')
        logger.info('Security profile created: %s', sp_id)
        return sp_id
    except Exception as e:
        logger.warning('Could not create security profile: %s', e)
        return None


def update_security_profile_tools(connect_client, instance_id, security_profile_id,
                                   gateway_namespace, tool_names):
    """Update a security profile to grant access to MCP tools.

    Adds the MCP tool permissions that are required for the AI agent to
    invoke tools from the gateway.
    """
    logger.info('Updating security profile with MCP tool access...')
    logger.info('  Security profile ID: %s', security_profile_id)
    logger.info('  Gateway namespace:   %s', gateway_namespace)
    logger.info('  Tools: %s', tool_names)

    try:
        connect_client.update_security_profile(
            SecurityProfileId=security_profile_id,
            InstanceId=instance_id,
            Applications=[
                {
                    'Namespace': gateway_namespace,
                    'ApplicationPermissions': tool_names,
                    'Type': 'MCP',
                }
            ],
        )
        logger.info('Security profile updated with MCP tool permissions.')
    except Exception as e:
        logger.warning('Could not update security profile tools: %s', e)
        logger.info('You may need to add MCP tool access manually in the Connect console:')
        logger.info('  Users → Security profiles → %s → Tools', SECURITY_PROFILE_NAME)


def associate_security_profile_with_agent(connect_client, instance_id,
                                            security_profile_id, agent_arn):
    """Associate a security profile with an AI agent entity.

    The security profile must be explicitly associated with the AI agent
    for the agent to use the MCP tools granted by the profile.
    Idempotent: re-associating an already-associated profile is a no-op.
    """
    try:
        connect_client.associate_security_profiles(
            InstanceId=instance_id,
            SecurityProfiles=[{'Id': security_profile_id}],
            EntityType='AI_AGENT',
            EntityArn=agent_arn,
        )
        logger.info('Security profile %s associated with AI agent.', security_profile_id)
    except Exception as e:
        logger.warning('Could not associate security profile with agent: %s', e)


def ensure_security_profile_with_tools(connect_client, instance_id, gateway_id,
                                        agent_arn=None):
    """Find/create the security profile, add MCP tool permissions, and
    associate it with the AI agent.

    Combines profile discovery, tool permission update, and agent
    association into one call. Returns the security_profile_id or None.
    """
    sp_id = find_or_create_security_profile(connect_client, instance_id)
    if sp_id and gateway_id:
        update_security_profile_tools(
            connect_client, instance_id, sp_id,
            gateway_namespace=gateway_id,
            tool_names=[MCP_TOOL_NAME],
        )
    if sp_id and agent_arn:
        associate_security_profile_with_agent(
            connect_client, instance_id, sp_id, agent_arn,
        )
    return sp_id


# ---------------------------------------------------------------------------
# Amazon Connect — Custom Orchestration Prompt (via Amazon Q Connect / qconnect)
# ---------------------------------------------------------------------------


def find_existing_prompt(qconnect_client, assistant_id, prompt_name):
    """Check if a custom prompt with the given name already exists.

    Returns (prompt_id, prompt_arn) or (None, None) if not found.
    """
    try:
        resp = qconnect_client.list_ai_prompts(assistantId=assistant_id)
        for p in resp.get('aiPromptSummaries', []):
            if p.get('name') == prompt_name:
                return p.get('aiPromptId'), p.get('aiPromptArn')
    except ClientError:
        logger.debug('Could not list AI prompts', exc_info=True)
    return None, None


def create_or_update_orchestration_prompt(session, assistant_id, prompt_name,
                                           prompt_file, model_id):
    """Create or update a custom ORCHESTRATION prompt for the AI agent.

    Reads the prompt content from the file, creates or updates the prompt
    in Q Connect, and returns the prompt ID (with :$LATEST suffix).
    """
    qconnect_client = session.client('qconnect')

    # Read prompt content
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt_text = f.read()

    logger.info('Prompt content loaded (%d chars) from %s', len(prompt_text), prompt_file)

    # Check for existing prompt
    existing_id, _ = find_existing_prompt(qconnect_client, assistant_id, prompt_name)

    template_config = {
        'textFullAIPromptEditTemplateConfiguration': {
            'text': prompt_text,
        }
    }

    if existing_id:
        logger.info('Prompt already exists: %s (ID: %s) — updating...', prompt_name, existing_id)
        try:
            qconnect_client.update_ai_prompt(
                assistantId=assistant_id,
                aiPromptId=existing_id,
                templateConfiguration=template_config,
                visibilityStatus='PUBLISHED',
            )
            logger.info('Prompt updated.')
        except Exception as e:
            logger.warning('Could not update prompt: %s', e)
        return f'{existing_id}:$LATEST'

    # Create new prompt
    logger.info('Creating custom orchestration prompt: %s', prompt_name)
    logger.info('  Model: %s', model_id)
    try:
        resp = qconnect_client.create_ai_prompt(
            assistantId=assistant_id,
            name=prompt_name,
            type='ORCHESTRATION',
            modelId=model_id,
            apiFormat='MESSAGES',
            templateType='TEXT',
            templateConfiguration=template_config,
            visibilityStatus='PUBLISHED',
        )
        prompt_id = resp.get('aiPrompt', {}).get('aiPromptId', 'N/A')
        logger.info('Prompt created. ID: %s', prompt_id)

        # Create version
        try:
            qconnect_client.create_ai_prompt_version(
                assistantId=assistant_id, aiPromptId=prompt_id,
            )
            logger.info('Prompt version 1 created.')
        except ClientError:
            logger.warning('Could not create prompt version', exc_info=True)

        return f'{prompt_id}:$LATEST'
    except Exception as e:
        err_str = str(e).lower()
        if 'already exists' in err_str or 'conflict' in err_str:
            logger.info('Prompt already exists (caught on create).')
            existing_id, _ = find_existing_prompt(
                qconnect_client, assistant_id, prompt_name,
            )
            return f'{existing_id}:$LATEST' if existing_id else None
        logger.warning('Could not create orchestration prompt: %s', e)
        return None


# ---------------------------------------------------------------------------
# Amazon Connect — AI Agent (via Amazon Q Connect / qconnect)
# ---------------------------------------------------------------------------


def find_qconnect_assistant(session, connect_instance_id):
    """Find the Amazon Q Connect assistant associated with a Connect instance.

    Returns (assistant_id, assistant_arn) or (None, None) if not found.
    When connect_instance_id is provided, only returns the assistant actually
    associated with that instance (via WISDOM_ASSISTANT integration).
    """
    if connect_instance_id:
        # Only look for assistants associated with the specific instance
        connect_client = session.client('connect')
        try:
            paginator = connect_client.get_paginator('list_integration_associations')
            for page in paginator.paginate(
                InstanceId=connect_instance_id,
                IntegrationType='WISDOM_ASSISTANT',
            ):
                for assoc in page.get('IntegrationAssociationSummaryList', []):
                    arn = assoc.get('IntegrationArn', '')
                    if arn:
                        # ARN format: arn:aws:wisdom:region:account:assistant/assistant-id
                        assistant_id = arn.split('/')[-1] if '/' in arn else None
                        logger.info('Found Q Connect assistant via Connect: %s', assistant_id)
                        return assistant_id, arn
        except ClientError:
            logger.debug('Could not list WISDOM_ASSISTANT associations', exc_info=True)
    else:
        # No instance ID — list all Q Connect assistants in this region
        try:
            qconnect_client = session.client('qconnect')
            resp = qconnect_client.list_assistants()
            assistants = resp.get('assistantSummaries', [])
            if assistants:
                assistant = assistants[0]
                assistant_id = assistant['assistantId']
                assistant_arn = assistant['assistantArn']
                logger.info('Found Q Connect assistant: %s', assistant_id)
                return assistant_id, assistant_arn
        except ClientError:
            logger.debug('Could not list Q Connect assistants', exc_info=True)

    return None, None


def discover_qconnect_assistant(primary_region, connect_instance_id=None):
    """Discover the Q Connect assistant by scanning across AWS regions.

    Searches the primary region first, then dynamically discovers all
    available Connect regions and tries each one.

    Returns (session, assistant_id, assistant_arn) where session is a
    boto3.Session in the region where the assistant was found.
    Returns (None, None, None) if no assistant is found in any region.
    """
    # Dynamically get all regions where Connect is available
    all_regions = boto3.Session().get_available_regions('connect')

    # Build deduplicated ordered list: primary first, then the rest
    seen = set()
    regions = []
    for r in [primary_region] + list(all_regions):
        if r and r not in seen:
            seen.add(r)
            regions.append(r)

    for region_candidate in regions:
        candidate_session = boto3.Session(region_name=region_candidate)
        if connect_instance_id:
            aid, aarn = find_qconnect_assistant(
                candidate_session, connect_instance_id,
            )
        else:
            aid, aarn = None, None
            try:
                qc = candidate_session.client('qconnect')
                resp = qc.list_assistants()
                for a in resp.get('assistantSummaries', []):
                    aid = a['assistantId']
                    aarn = a['assistantArn']
                    break
            except ClientError:
                logger.debug('Could not list Q Connect assistants in %s', region, exc_info=True)
        if aid and aarn:
            logger.info('Found Q Connect assistant in %s: %s',
                         region_candidate, aid)
            return candidate_session, aid, aarn

    logger.warning('No Q Connect assistant found in any region.')
    return None, None, None


def find_existing_ai_agent(qconnect_client, assistant_id, agent_name):
    """Check if an AI agent with the given name already exists.

    Returns (agent_id, agent_arn) or (None, None) if not found.
    """
    try:
        resp = qconnect_client.list_ai_agents(assistantId=assistant_id)
        for agent in resp.get('aiAgentSummaries', []):
            if agent.get('name') == agent_name:
                return agent.get('aiAgentId'), agent.get('aiAgentArn')
    except ClientError:
        logger.debug('Could not list AI agents', exc_info=True)
    return None, None


def find_system_orchestration_prompt(qconnect_client, assistant_id):
    """Find the system SelfServiceOrchestration prompt ID.

    Returns the prompt ID string (e.g. 'abc123:$LATEST') or None.
    """
    try:
        resp = qconnect_client.list_ai_prompts(assistantId=assistant_id, origin='SYSTEM')
        for prompt in resp.get('aiPromptSummaries', []):
            if prompt.get('name') == 'SelfServiceOrchestration' and prompt.get('type') == 'ORCHESTRATION':
                prompt_id = prompt['aiPromptId']
                logger.info('Found system SelfServiceOrchestration prompt: %s', prompt_id)
                return f'{prompt_id}:$LATEST'
    except ClientError:
        logger.debug('Could not list system AI prompts', exc_info=True)
    return None


def update_ai_agent_config(qconnect_client, assistant_id, agent_id,
                            connect_instance_id, session,
                            prompt_id=None, gateway_id=None):
    """Update an existing AI agent's prompt and/or tool configuration.

    When prompt_id is provided, updates the orchestration prompt.
    When gateway_id is provided, ensures the MCP employee lookup tool is
    present in the tool list (adds it if missing).
    Preserves existing tool configurations and locale.
    """
    # Get current config
    agent = qconnect_client.get_ai_agent(
        assistantId=assistant_id, aiAgentId=agent_id,
    )
    current_config = agent['aiAgent']['configuration']
    orch = current_config.get('orchestrationAIAgentConfiguration', {})

    region = session.region_name
    account = session.client('sts').get_caller_identity()['Account']
    connect_instance_arn = f'arn:aws:connect:{region}:{account}:instance/{connect_instance_id}'

    # Clean tool configs — MCP tools don't allow overriding certain fields.
    # Strip Retrieve and employee lookup tools so we can re-add them with
    # full instruction/examples. Other MCP tools keep only safe fields.
    RETRIEVE_TOOL_ID = 'aws_service__qconnect_Retrieve'
    mcp_tool_id = f'gateway_{gateway_id}__{MCP_TOOL_NAME}' if gateway_id else None
    clean_tools = []
    for tool in orch.get('toolConfigurations', []):
        # Drop old RETURN_TO_CONTROL employee_lookup when adding MCP version
        if (gateway_id
                and tool.get('toolType') == 'RETURN_TO_CONTROL'
                and tool.get('toolName') == 'employee_lookup'):
            logger.info('Removing old RETURN_TO_CONTROL employee_lookup tool.')
            continue
        # Drop existing MCP employee lookup — will be re-added with instructions
        if (mcp_tool_id
                and tool.get('toolId') == mcp_tool_id):
            continue
        # Drop existing Retrieve — will be re-added with instructions
        if tool.get('toolId') == RETRIEVE_TOOL_ID:
            continue
        if tool.get('toolType') == 'MODEL_CONTEXT_PROTOCOL':
            clean = {
                'toolName': tool['toolName'],
                'toolType': tool['toolType'],
            }
            if tool.get('toolId'):
                clean['toolId'] = tool['toolId']
            clean_tools.append(clean)
        else:
            clean_tools.append(tool)

    # Re-add Retrieve tool with instruction, examples, and KB association
    retrieve_tool = {
        'toolName': 'Retrieve',
        'toolType': 'MODEL_CONTEXT_PROTOCOL',
        'toolId': RETRIEVE_TOOL_ID,
        'instruction': {
            'instruction': RETRIEVE_TOOL_INSTRUCTION,
            'examples': RETRIEVE_TOOL_EXAMPLES,
        },
    }
    # Discover KB association and pre-fill as override input values
    kb_assoc_id, _ = find_existing_kb_association(qconnect_client, assistant_id)
    if kb_assoc_id:
        retrieve_tool['overrideInputValues'] = _build_retrieve_override_values(
            assistant_id, kb_assoc_id,
        )
        logger.info('Retrieve tool linked to KB association: %s', kb_assoc_id)
    else:
        logger.warning('No KB association found — Retrieve tool has no knowledge source.')
    clean_tools.append(retrieve_tool)
    logger.info('Configured Retrieve tool with instruction and examples.')

    # Add MCP employee lookup tool with instruction and examples
    # NOTE: MCP tools don't allow overriding 'description' — it comes from the gateway
    if gateway_id:
        clean_tools.append({
            'toolName': MCP_TOOL_NAME_SAFE,
            'toolType': 'MODEL_CONTEXT_PROTOCOL',
            'toolId': mcp_tool_id,
            'instruction': {
                'instruction': MCP_TOOL_INSTRUCTION,
                'examples': MCP_TOOL_EXAMPLES,
            },
        })
        logger.info('Configured MCP tool: %s', MCP_TOOL_NAME_SAFE)

    # Use new prompt or preserve existing
    effective_prompt = prompt_id or orch.get('orchestrationAIPromptId')

    new_config = {
        'orchestrationAIAgentConfiguration': {
            'orchestrationAIPromptId': effective_prompt,
            'locale': orch.get('locale', 'en_US'),
            'connectInstanceArn': connect_instance_arn,
            'toolConfigurations': clean_tools,
        }
    }

    qconnect_client.update_ai_agent(
        assistantId=assistant_id,
        aiAgentId=agent_id,
        configuration=new_config,
        visibilityStatus='PUBLISHED',
    )
    if prompt_id:
        logger.info('Agent prompt updated to: %s', prompt_id)
    logger.info('Agent configuration updated.')

    # Create new version
    try:
        qconnect_client.create_ai_agent_version(
            assistantId=assistant_id, aiAgentId=agent_id,
        )
        logger.info('New agent version created.')
    except ClientError:
        logger.warning('Could not create agent version', exc_info=True)


# MCP employee lookup tool instruction and examples
MCP_TOOL_INSTRUCTION = (
    'Use this tool when a customer provides their Thrive@Work employee ID '
    '(format: TW-XXXXX) to verify their enrollment and check what programs '
    'they can access. Always ask the customer for their employee ID before '
    'calling this tool. After a successful lookup, share the results '
    'conversationally and offer to help with any of their eligible programs.'
)

MCP_TOOL_EXAMPLES = [
    (
        'Customer: My employee ID is TW-10001, can you check what '
        'programs I can access?\n'
        'Agent: I\'ll look up your employee information right away.\n'
        'Tool call: employee_lookup_api___employeeLookup with '
        'employee_id=TW-10001\n'
        'Result: Active employee at Lowcountry Manufacturing Co., '
        'Premium tier, eligible for EAP, Financial Wellness, '
        'Wellness Programs, Emergency Assistance.\n'
        'Agent: Great news! I found your information. You\'re enrolled '
        'through Lowcountry Manufacturing with their Premium partnership. '
        'You have access to counseling services, financial wellness '
        'coaching, wellness programs, and emergency assistance. '
        'Which of these would you like to know more about?'
    ),
    (
        'Customer: I want to know what programs I can access.\n'
        'Agent: I\'d be happy to help you find out about your eligible '
        'programs. Could you please share your employee ID? It usually '
        'starts with TW followed by a dash and numbers, like TW-10001.\n'
        'Customer: It\'s TW-20045.\n'
        'Agent: Let me look that up for you now.\n'
        'Tool call: employee_lookup_api___employeeLookup with '
        'employee_id=TW-20045'
    ),
    (
        'Customer: Can you check my ID? It\'s TW-99999.\n'
        'Agent: Let me look that up for you.\n'
        'Tool call: employee_lookup_api___employeeLookup with '
        'employee_id=TW-99999\n'
        'Result: Employee not found.\n'
        'Agent: I wasn\'t able to find that employee ID in our system. '
        'Could you double-check the ID with your HR department? '
        'In the meantime, I can still help you with general information '
        'about our programs and community resources.'
    ),
]


# Q Connect Retrieve tool (KB search) instruction and examples
RETRIEVE_TOOL_INSTRUCTION = (
    'Use this tool to search the Stability360 knowledge base whenever a '
    'customer asks about programs, services, eligibility criteria, community '
    'resources, or anything related to Stability360 and Trident United Way. '
    'This is your primary tool for answering questions — always try Retrieve '
    'before telling a customer you don\'t have information. You can search '
    'with natural language queries. Provide answers conversationally without '
    'mentioning the knowledge base, tools, or retrieval process.'
)

RETRIEVE_TOOL_EXAMPLES = [
    (
        'Customer: What programs does Stability360 offer?\n'
        'Agent: Let me find that information for you.\n'
        'Tool call: Retrieve with query="Stability360 programs and services"\n'
        'Result: Stability360 offers five core programs: Emergency Financial '
        'Assistance, Employee Assistance Program (EAP), Financial Wellness '
        'Coaching, Wellness Programs, and Community Resource Navigation.\n'
        'Agent: Stability360 offers several programs to support you! These '
        'include emergency financial help, counseling through our Employee '
        'Assistance Program, financial wellness coaching, wellness programs, '
        'and help connecting with community resources. Would you like to '
        'learn more about any of these?'
    ),
    (
        'Customer: I need help with my rent this month. What resources '
        'are available?\n'
        'Agent: I\'ll look into what assistance is available for you.\n'
        'Tool call: Retrieve with query="rent assistance emergency '
        'financial help housing"\n'
        'Result: Emergency Financial Assistance can help with rent, '
        'utilities, and other critical expenses...\n'
        'Agent: We may be able to help! Our Emergency Financial Assistance '
        'program supports people with rent, utilities, and other urgent '
        'expenses. Would you like me to walk you through how to access '
        'this assistance?'
    ),
    (
        'Customer: My employee ID is TW-10001. What Thrive@Work benefits '
        'do I have?\n'
        'Agent: [After employee lookup shows eligible programs] Let me '
        'get you more details on those programs.\n'
        'Tool call: Retrieve with query="Thrive@Work employer programs '
        'EAP Financial Wellness"\n'
        'Result: Thrive@Work employer-based programs include...\n'
        'Agent: Based on your enrollment, here\'s what\'s available to '
        'you through your employer\'s partnership...'
    ),
]


def _build_retrieve_override_values(assistant_id, kb_association_id):
    """Build overrideInputValues for the Retrieve tool.

    Pre-fills assistantId and the KB association so the agent knows which
    knowledge base to search (the "Assistant Association" required field
    in the Connect console).
    """
    import json as _json
    return [
        {
            'jsonPath': '$.assistantId',
            'value': {'constant': {'type': 'STRING', 'value': assistant_id}},
        },
        {
            'jsonPath': '$.retrievalConfiguration.knowledgeSource.assistantAssociationIds',
            'value': {
                'constant': {
                    'type': 'JSON_STRING',
                    'value': _json.dumps([kb_association_id]),
                },
            },
        },
    ]


def _build_agent_tool_configurations(gateway_id=None, assistant_id=None,
                                      kb_association_id=None):
    """Build the tool configurations list for the AI agent.

    Always includes: Complete, Escalate, Retrieve (Q Connect KB search).
    When assistant_id and kb_association_id are provided, the Retrieve tool
    is configured with overrideInputValues pointing to the KB association.
    When a gateway_id is provided, adds the employee lookup MCP tool from
    the gateway automatically (no manual console step needed).
    """
    retrieve_tool = {
        'toolName': 'Retrieve',
        'toolType': 'MODEL_CONTEXT_PROTOCOL',
        'toolId': 'aws_service__qconnect_Retrieve',
        'instruction': {
            'instruction': RETRIEVE_TOOL_INSTRUCTION,
            'examples': RETRIEVE_TOOL_EXAMPLES,
        },
    }
    if assistant_id and kb_association_id:
        retrieve_tool['overrideInputValues'] = _build_retrieve_override_values(
            assistant_id, kb_association_id,
        )

    tools = [
        {
            'toolName': 'Complete',
            'toolType': 'RETURN_TO_CONTROL',
            'description': 'Close conversation when customer has no more questions',
            'instruction': {
                'instruction': (
                    'Mark the conversation as complete ONLY after confirming '
                    'the customer has no additional questions or needs. Always '
                    'ask if there is anything else you can help with before '
                    'using this tool.'
                ),
            },
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'reason': {
                        'type': 'string',
                        'description': 'Reason of completion',
                    },
                },
                'required': ['reason'],
            },
        },
        {
            'toolName': 'Escalate',
            'toolType': 'RETURN_TO_CONTROL',
            'description': 'Escalate to human agent when the issue cannot be resolved by AI',
            'instruction': {
                'instruction': (
                    'Escalate the conversation to a human agent when the '
                    'customer explicitly requests it, when you cannot resolve '
                    'their issue, or when the situation requires human judgment. '
                    'Always inform the customer that you are transferring them.'
                ),
            },
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'reason': {
                        'type': 'string',
                        'description': 'Reason for escalation',
                    },
                },
                'required': ['reason'],
            },
        },
        retrieve_tool,
    ]

    if gateway_id:
        # MCP tool ID format: gateway_{gateway_id}__{target_name}___{operationId}
        mcp_tool_id = f'gateway_{gateway_id}__{MCP_TOOL_NAME}'
        tools.append({
            'toolName': MCP_TOOL_NAME_SAFE,
            'toolType': 'MODEL_CONTEXT_PROTOCOL',
            'toolId': mcp_tool_id,
            'instruction': {
                'instruction': MCP_TOOL_INSTRUCTION,
                'examples': MCP_TOOL_EXAMPLES,
            },
        })

    return tools


def create_ai_agent(session, assistant_id, agent_name, description,
                     connect_instance_id, custom_prompt_id=None,
                     gateway_id=None):
    """Create an ORCHESTRATION AI agent (per workshop Task 6/7 pattern).

    Uses the custom prompt if provided, otherwise falls back to the system
    SelfServiceOrchestration prompt. When gateway_id is provided, the MCP
    employee lookup tool is added automatically.

    Idempotent: returns existing agent ID if one with the same name exists.
    Returns agent_id or None if creation fails.
    """
    qconnect_client = session.client('qconnect')

    # Check for existing agent
    existing_id, _ = find_existing_ai_agent(qconnect_client, assistant_id, agent_name)
    if existing_id:
        logger.info('AI Agent already exists: %s (ID: %s)', agent_name, existing_id)
        # Update the agent with custom prompt and/or MCP tool
        if custom_prompt_id or gateway_id:
            logger.info('Updating agent configuration...')
            try:
                update_ai_agent_config(
                    qconnect_client, assistant_id, existing_id,
                    connect_instance_id, session,
                    prompt_id=custom_prompt_id,
                    gateway_id=gateway_id,
                )
            except Exception as e:
                logger.warning('Could not update agent: %s', e)
        # Set as default self-service orchestration agent
        set_default_ai_agent(qconnect_client, assistant_id, existing_id)
        return existing_id

    # Use custom prompt or fall back to system prompt
    prompt_id = custom_prompt_id
    if not prompt_id:
        prompt_id = find_system_orchestration_prompt(qconnect_client, assistant_id)
    if not prompt_id:
        logger.warning('No orchestration prompt available.')
        logger.info('You may need to create the AI Agent manually in the Connect console.')
        return None

    # Build Connect instance ARN
    region = session.region_name
    account = session.client('sts').get_caller_identity()['Account']
    connect_instance_arn = f'arn:aws:connect:{region}:{account}:instance/{connect_instance_id}'

    # Discover KB association for Retrieve tool's knowledge source
    kb_assoc_id, _ = find_existing_kb_association(qconnect_client, assistant_id)
    if kb_assoc_id:
        logger.info('KB association found for Retrieve tool: %s', kb_assoc_id)

    baseline_tools = _build_agent_tool_configurations(
        gateway_id=gateway_id, assistant_id=assistant_id,
        kb_association_id=kb_assoc_id,
    )
    tool_names = [t['toolName'] for t in baseline_tools]

    config = {
        'orchestrationAIAgentConfiguration': {
            'orchestrationAIPromptId': prompt_id,
            'locale': 'en_US',
            'connectInstanceArn': connect_instance_arn,
            'toolConfigurations': baseline_tools,
        }
    }

    logger.info('Creating AI Agent: %s (type: ORCHESTRATION)', agent_name)
    logger.info('  Prompt: %s', prompt_id)
    logger.info('  Locale: en_US')
    logger.info('  Tools: %s', ', '.join(tool_names))
    try:
        resp = qconnect_client.create_ai_agent(
            assistantId=assistant_id,
            name=agent_name,
            type='ORCHESTRATION',
            description=description,
            configuration=config,
            visibilityStatus='PUBLISHED',
        )
        agent_id = resp.get('aiAgent', {}).get('aiAgentId', 'N/A')
        logger.info('AI Agent created. ID: %s', agent_id)

        # Create version 1 (required for use in contact flows)
        try:
            qconnect_client.create_ai_agent_version(
                assistantId=assistant_id, aiAgentId=agent_id,
            )
            logger.info('AI Agent version 1 created.')
        except ClientError:
            logger.warning('Could not create agent version', exc_info=True)

        # Set as default self-service orchestration agent
        set_default_ai_agent(qconnect_client, assistant_id, agent_id)
        return agent_id
    except Exception as e:
        err_str = str(e).lower()
        if 'already exists' in err_str or 'conflict' in err_str:
            logger.info('AI Agent already exists (caught on create).')
            existing_id, _ = find_existing_ai_agent(
                qconnect_client, assistant_id, agent_name,
            )
            set_default_ai_agent(qconnect_client, assistant_id, existing_id)
            return existing_id
        logger.warning('Could not create AI Agent: %s', e)
        logger.info('You may need to create the AI Agent manually in the Connect console:')
        logger.info('  AI agent designer → AI agents → Create AI agent')
        return None


def discover_gateway_id(stack_outputs=None, config_file=None):
    """Discover the MCP gateway ID from available sources.

    Checks (in order):
      1. Stack outputs (McpGatewayId)
      2. Tool config JSON file (gateway.gatewayId)
    Returns the gateway_id or None.
    """
    # Source 1: Stack outputs
    if stack_outputs:
        gw_id = stack_outputs.get('McpGatewayId', '')
        if gw_id:
            return gw_id

    # Source 2: Tool config file
    config_path = config_file or MCP_TOOL_CONFIG_FILE
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        gw_id = config.get('gateway', {}).get('gatewayId', '')
        if gw_id:
            logger.info('Gateway ID from config file: %s', gw_id)
            return gw_id
    except (OSError, json.JSONDecodeError):
        logger.debug('Could not read gateway config from %s', config_path)

    return None


def set_default_ai_agent(qconnect_client, assistant_id, agent_id,
                          use_case='Connect.SelfService'):
    """Set the AI agent as the default for the given orchestrator use case.

    The orchestratorUseCase determines when the agent is invoked:
      - Connect.SelfService — customer-facing self-service (chatbot, IVR)
      - Connect.AgentAssistance — real-time agent assist

    Idempotent: if the agent is already the default for the use case, this
    is a no-op (the API call succeeds silently).
    """
    try:
        qconnect_client.update_assistant_ai_agent(
            assistantId=assistant_id,
            aiAgentType='ORCHESTRATION',
            configuration={'aiAgentId': agent_id},
            orchestratorUseCase=use_case,
        )
        logger.info('AI Agent %s set as default for %s', agent_id, use_case)
    except Exception as e:
        logger.warning('Could not set agent as default: %s', e)


# ---------------------------------------------------------------------------
# AI Agent — MCP Tool Configuration Reference
# ---------------------------------------------------------------------------


def generate_tool_config_file(gateway_id, target_name, operation_id, agent_name,
                               agent_id, assistant_id, output_path):
    """Generate a JSON reference file documenting the MCP tool configuration.

    The MCP gateway tool is automatically added to the AI agent during
    deployment. This file serves as a reference for the tool configuration.
    """
    tool_id = f'gateway_{gateway_id}__{target_name}___{operation_id}'

    config = {
        '_note_1': '=== MCP TOOL REFERENCE: Auto-configured during deployment ===',
        '_info': {
            'summary': (
                'The MCP employee lookup tool is automatically added to the AI '
                'agent during deployment. No manual console steps are needed.'
            ),
            'workshop_reference': 'Task 6, Step 4: Add MCP tools from gateway',
        },
        '_note_2': '=== AGENT: Target AI agent ===',
        'agent': {
            'name': agent_name,
            'agentId': agent_id,
            'assistantId': assistant_id,
            'type': 'ORCHESTRATION',
        },
        '_note_3': '=== TOOL PROPERTIES: Configuration to enter in the Connect console ===',
        'tool_properties': {
            'toolName': 'employee_lookup',
            'toolType': 'RETURN_TO_CONTROL',
            'description': (
                'Look up an employee by their employee ID to verify eligibility '
                'for Stability360 Thrive@Work employer-based programs. Returns '
                'employer name, partnership status, eligible programs, and '
                'enrollment date.'
            ),
            'user_confirmation': False,
            'input_schema': {
                'type': 'object',
                'properties': {
                    'employee_id': {
                        'type': 'string',
                        'description': (
                            'The employee ID to look up (e.g. TW-10001). '
                            'Alphanumeric characters and hyphens only.'
                        ),
                    },
                },
                'required': ['employee_id'],
            },
            'instruction': {
                'text': (
                    'Use this tool when a customer provides their employee ID to '
                    'verify their enrollment in a Thrive@Work program. Always ask '
                    'for the employee ID before calling this tool. Format: '
                    'alphanumeric with hyphens (e.g., TW-10001).'
                ),
                'examples': [
                    {
                        'input': 'My employee ID is TW-10001, can you check my eligibility?',
                        'output': (
                            "I'll look up your employee ID TW-10001 now to verify "
                            'your Thrive@Work program eligibility.'
                        ),
                        'tool_use': {'employee_id': 'TW-10001'},
                    },
                    {
                        'input': 'I want to know what programs I can access.',
                        'output': (
                            "I'd be happy to help you check your eligible programs. "
                            'Could you please provide me with your employee ID? It '
                            'typically starts with TW- followed by numbers, for '
                            'example TW-10001.'
                        ),
                        'tool_use': None,
                    },
                ],
            },
        },
        '_note_4': '=== MCP TOOL: Internal tool ID for Q Connect API reference ===',
        'mcp_tool': {
            'toolName': operation_id,
            'toolType': 'MODEL_CONTEXT_PROTOCOL',
            'toolId': tool_id,
        },
        '_note_5': '=== GATEWAY: Bedrock AgentCore MCP gateway details ===',
        'gateway': {
            'gatewayId': gateway_id,
            'targetName': target_name,
            'operationId': operation_id,
            'securityProfileNamespace': gateway_id,
            'securityProfileToolPermission': f'{target_name}___{operation_id}',
        },
    }

    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)

    logger.info('MCP tool reference file written: %s', output_path)
    logger.info('  Tool ID:   %s', tool_id)
    logger.info('  Tool Name: %s', f'{target_name}___{operation_id}')
    return tool_id


# ---------------------------------------------------------------------------
# Lex V2 Bot — Create bot with AMAZON.QinConnectIntent (Task 8)
# ---------------------------------------------------------------------------


def ensure_lex_bot_role(iam_client, role_name, account_id):
    """Create (or retrieve) an IAM role for the Lex V2 bot.

    Grants lexv2.amazonaws.com trust + wisdom, qconnect, and polly permissions.
    Idempotent: creates the role if missing, always ensures the permissions
    policy is up-to-date (adds qconnect:* which newer Q Connect requires).
    """
    trust_policy = json.dumps({
        'Version': '2012-10-17',
        'Statement': [
            {
                'Effect': 'Allow',
                'Principal': {'Service': 'lexv2.amazonaws.com'},
                'Action': 'sts:AssumeRole',
            }
        ]
    })

    # Q Connect now uses qconnect:* actions in addition to the legacy wisdom:*
    # actions.  Both wildcards are required — the exact set of actions that Lex
    # needs for QInConnectIntent changes across service updates.
    permissions_policy = json.dumps({
        'Version': '2012-10-17',
        'Statement': [
            {
                'Sid': 'QConnectLegacyWisdom',
                'Effect': 'Allow',
                'Action': 'wisdom:*',
                'Resource': f'arn:aws:wisdom:*:{account_id}:*',
            },
            {
                'Sid': 'QConnectNewActions',
                'Effect': 'Allow',
                'Action': 'qconnect:*',
                'Resource': f'arn:aws:qconnect:*:{account_id}:*',
            },
            {
                'Sid': 'Polly',
                'Effect': 'Allow',
                'Action': ['polly:SynthesizeSpeech'],
                'Resource': '*',
            },
        ]
    })

    # Check if role already exists
    role_exists = False
    try:
        resp = iam_client.get_role(RoleName=role_name)
        role_arn = resp['Role']['Arn']
        role_exists = True
        logger.info('Lex bot IAM role already exists: %s', role_arn)
    except iam_client.exceptions.NoSuchEntityException:
        pass

    if not role_exists:
        logger.info('Creating IAM role for Lex bot: %s', role_name)
        resp = iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=trust_policy,
            Description='IAM role for Stability360 Lex V2 bot (QinConnect intent)',
        )
        role_arn = resp['Role']['Arn']
        logger.info('IAM role created: %s', role_arn)

    # Always update the permissions policy to ensure qconnect:* is present
    iam_client.put_role_policy(
        RoleName=role_name,
        PolicyName='QConnectAndPollyAccess',
        PolicyDocument=permissions_policy,
    )
    logger.info('Lex bot IAM policy updated (wisdom + qconnect + polly).')

    if not role_exists:
        # Wait for IAM propagation on new role
        logger.info('Waiting for IAM role propagation...')
        time.sleep(10)
    return role_arn


def find_existing_lex_bot(lex_client, bot_name):
    """Find an existing Lex V2 bot by name.

    Returns (bot_id, bot_status) or (None, None) if not found.
    """
    try:
        resp = lex_client.list_bots(
            filters=[{
                'name': 'BotName',
                'values': [bot_name],
                'operator': 'EQ',
            }]
        )
        for summary in resp.get('botSummaries', []):
            return summary['botId'], summary.get('botStatus', 'Unknown')
    except ClientError:
        logger.debug('Could not list Lex bots', exc_info=True)
    return None, None


def find_existing_bot_alias(lex_client, bot_id, alias_name):
    """Find an existing bot alias by name.

    Returns (alias_id, alias_arn) or (None, None) if not found.
    """
    try:
        resp = lex_client.list_bot_aliases(botId=bot_id)
        for summary in resp.get('botAliasSummaries', []):
            if summary.get('botAliasName', '').lower() == alias_name.lower():
                return summary['botAliasId'], None
    except ClientError:
        logger.debug('Could not list bot aliases', exc_info=True)
    return None, None


def wait_for_bot_locale_build(lex_client, bot_id, bot_version, locale_id,
                               timeout=LEX_BOT_BUILD_TIMEOUT,
                               poll_interval=LEX_BOT_BUILD_POLL_INTERVAL):
    """Poll until the bot locale build completes.

    Returns the final botLocaleStatus string ('Built' or 'Failed').
    """
    start = time.time()
    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            logger.error('Bot locale build timed out after %ds.', timeout)
            return 'Timeout'

        try:
            resp = lex_client.describe_bot_locale(
                botId=bot_id, botVersion=bot_version, localeId=locale_id,
            )
            status = resp.get('botLocaleStatus', 'Unknown')
        except Exception as e:
            logger.warning('Could not check build status: %s', e)
            status = 'Unknown'

        if status in ('Built', 'ReadyExpressTesting'):
            return 'Built'
        if status == 'Failed':
            reasons = resp.get('failureReasons', [])
            logger.error('Bot locale build failed: %s', reasons)
            return 'Failed'

        logger.info('  Build status: %s (%.0fs elapsed)', status, elapsed)
        time.sleep(poll_interval)


def create_lex_bot(session, bot_name, bot_description, role_arn,
                    locale_id, nlu_threshold, idle_session_ttl,
                    alias_name, assistant_arn, connect_instance_id):
    """Create a Lex V2 bot with AMAZON.QinConnectIntent and associate with Connect.

    Full workflow:
      1. Create bot (or find existing)
      2. Create bot locale (en_US)
      3. Create AMAZON.QinConnectIntent with Q Connect assistant ARN
      4. Build bot locale (wait for completion)
      5. Create bot version (immutable snapshot)
      6. Create bot alias pointing to the version
      7. Associate bot with Amazon Connect instance

    Idempotent: checks for existing resources at each step.
    Returns dict with botId, botVersion, botAliasId, botAliasArn — or None on failure.
    """
    lex_client = session.client('lexv2-models')
    region = session.region_name
    account_id = session.client('sts').get_caller_identity()['Account']

    # --- Sub-step 1: Create bot ---
    bot_id, bot_status = find_existing_lex_bot(lex_client, bot_name)
    if bot_id:
        logger.info('Lex bot already exists: %s (ID: %s, status: %s)',
                     bot_name, bot_id, bot_status)
        # Wait for bot to leave transitional states before proceeding
        _bot_start = time.time()
        while bot_status not in ('Available', 'Failed', 'Inactive'):
            if time.time() - _bot_start > LEX_BOT_BUILD_TIMEOUT:
                raise TimeoutError(f'Bot did not become Available within {LEX_BOT_BUILD_TIMEOUT}s (stuck in {bot_status})')
            elapsed = int(time.time() - _bot_start)
            logger.info('  Waiting for bot to become Available (status: %s, %ds elapsed)...', bot_status, elapsed)
            time.sleep(LEX_BOT_BUILD_POLL_INTERVAL)
            _, bot_status = find_existing_lex_bot(lex_client, bot_name)
    else:
        logger.info('Creating Lex V2 bot: %s', bot_name)
        resp = lex_client.create_bot(
            botName=bot_name,
            description=bot_description,
            roleArn=role_arn,
            dataPrivacy={'childDirected': False},
            idleSessionTTLInSeconds=idle_session_ttl,
        )
        bot_id = resp['botId']
        logger.info('Bot created. ID: %s', bot_id)
        time.sleep(3)

    # --- Sub-step 2: Create bot locale ---
    try:
        lex_client.describe_bot_locale(
            botId=bot_id, botVersion='DRAFT', localeId=locale_id,
        )
        logger.info('Bot locale %s already exists.', locale_id)
    except lex_client.exceptions.ResourceNotFoundException:
        logger.info('Creating bot locale: %s', locale_id)
        lex_client.create_bot_locale(
            botId=bot_id,
            botVersion='DRAFT',
            localeId=locale_id,
            nluIntentConfidenceThreshold=nlu_threshold,
        )
        logger.info('Bot locale created.')
        time.sleep(2)

    # --- Sub-step 3: Create AMAZON.QinConnectIntent ---
    qin_intent_id = None
    try:
        intents = lex_client.list_intents(
            botId=bot_id, botVersion='DRAFT', localeId=locale_id,
        )
        for i in intents.get('intentSummaries', []):
            sig = i.get('parentIntentSignature', '')
            if 'QInConnect' in sig or 'QinConnect' in sig:
                qin_intent_id = i['intentId']
                break
    except ClientError:
        logger.debug('Could not list intents for QInConnect lookup', exc_info=True)

    if qin_intent_id:
        logger.info('QInConnect intent already exists (ID: %s).', qin_intent_id)
    else:
        logger.info('Creating QInConnect intent...')
        logger.info('  Assistant ARN: %s', assistant_arn)
        try:
            # Built-in intents use parentIntentSignature; intentName must be valid
            create_kwargs = {
                'intentName': 'QInConnectIntent',
                'botId': bot_id,
                'botVersion': 'DRAFT',
                'localeId': locale_id,
                'parentIntentSignature': 'AMAZON.QInConnectIntent',
            }
            # Try adding qInConnect configuration if the API supports it
            create_resp = None
            try:
                create_resp = lex_client.create_intent(
                    **create_kwargs,
                    qInConnectIntentConfiguration={
                        'qInConnectAssistantConfiguration': {
                            'assistantArn': assistant_arn,
                        }
                    },
                )
            except (TypeError, Exception) as e:
                if 'unexpected keyword' in str(e).lower() or 'Unknown parameter' in str(e):
                    # Older boto3 — create without the config param
                    logger.info('qInConnectIntentConfiguration not supported — using parentIntentSignature only.')
                    create_resp = lex_client.create_intent(**create_kwargs)
                else:
                    raise
            if create_resp:
                qin_intent_id = create_resp.get('intentId')
            logger.info('QInConnect intent created (ID: %s).', qin_intent_id)
        except Exception as e:
            err_str = str(e).lower()
            if 'already exists' in err_str or 'conflict' in err_str:
                logger.info('Intent already exists (caught on create).')
            else:
                logger.warning('Could not create QInConnect intent: %s', e)
                logger.info('You may need to create the intent manually in the Connect console.')
                return None

    # --- Sub-step 3b: Set ElicitIntent for multi-turn conversation ---
    # Override successNextStep and failureNextStep to ElicitIntent so the
    # bot keeps the conversation open for follow-up questions.
    # timeoutNextStep stays as EndConversation (the default).
    #
    # IMPORTANT:
    #  - qInConnectIntentConfiguration is REQUIRED in every update_intent
    #    call for AMAZON.QInConnectIntent.
    #  - fulfillmentCodeHook.enabled must be False — Q Connect handles
    #    fulfillment internally, not via Lambda.
    #  - fulfillmentCodeHook.active must be True so the
    #    postFulfillmentStatusSpecification takes effect.
    if qin_intent_id:
        try:
            elicit_step = {'dialogAction': {'type': 'ElicitIntent'}}
            end_step = {'dialogAction': {'type': 'EndConversation'}}
            lex_client.update_intent(
                intentId=qin_intent_id,
                intentName='QInConnectIntent',
                botId=bot_id,
                botVersion='DRAFT',
                localeId=locale_id,
                parentIntentSignature='AMAZON.QInConnectIntent',
                qInConnectIntentConfiguration={
                    'qInConnectAssistantConfiguration': {
                        'assistantArn': assistant_arn,
                    }
                },
                fulfillmentCodeHook={
                    'enabled': False,
                    'active': True,
                    'postFulfillmentStatusSpecification': {
                        'successNextStep': elicit_step,
                        'failureNextStep': elicit_step,
                        'timeoutNextStep': end_step,
                    },
                },
            )
            logger.info('QInConnectIntent updated: success/failureNextStep=ElicitIntent, timeoutNextStep=EndConversation.')
        except Exception as e:
            logger.warning('Could not set ElicitIntent on QInConnectIntent: %s', e)
            logger.info('You may need to set this manually in the Lex console to enable multi-turn chat.')

    # --- Sub-step 4: Build bot locale ---
    logger.info('Building bot locale...')
    lex_client.build_bot_locale(
        botId=bot_id, botVersion='DRAFT', localeId=locale_id,
    )
    build_status = wait_for_bot_locale_build(
        lex_client, bot_id, 'DRAFT', locale_id,
    )
    if build_status != 'Built':
        logger.error('Bot locale build did not succeed: %s', build_status)
        return None
    logger.info('Bot locale built successfully.')

    # --- Sub-step 5: Create bot version ---
    logger.info('Creating bot version...')
    resp = lex_client.create_bot_version(
        botId=bot_id,
        botVersionLocaleSpecification={
            locale_id: {'sourceBotVersion': 'DRAFT'}
        },
        description='Auto-created by deploy.py',
    )
    bot_version = resp['botVersion']
    ver_status = resp.get('botStatus', 'Creating')
    logger.info('Bot version created: %s (status: %s)', bot_version, ver_status)

    # Wait for the bot version to become Available
    if ver_status != 'Available':
        _ver_start = time.time()
        time.sleep(2)  # Brief initial wait for version to become describable
        while time.time() - _ver_start < LEX_BOT_BUILD_TIMEOUT:
            try:
                desc = lex_client.describe_bot_version(botId=bot_id, botVersion=bot_version)
                ver_status = desc.get('botStatus', 'Unknown')
            except lex_client.exceptions.ResourceNotFoundException:
                # Version not yet propagated — retry
                elapsed = int(time.time() - _ver_start)
                logger.info('  Bot version not yet available (%ds elapsed)', elapsed)
                time.sleep(LEX_BOT_BUILD_POLL_INTERVAL)
                continue
            if ver_status == 'Available':
                logger.info('Bot version %s is Available.', bot_version)
                break
            if ver_status in ('Failed', 'Deleting'):
                raise RuntimeError(f'Bot version {bot_version} entered {ver_status} state.')
            elapsed = int(time.time() - _ver_start)
            logger.info('  Bot version status: %s (%ds elapsed)', ver_status, elapsed)
            time.sleep(LEX_BOT_BUILD_POLL_INTERVAL)
        else:
            raise TimeoutError(f'Bot version did not become Available within {LEX_BOT_BUILD_TIMEOUT}s')

    # --- Sub-step 6: Create or update bot alias ---
    alias_id, _ = find_existing_bot_alias(lex_client, bot_id, alias_name)
    if alias_id:
        logger.info('Bot alias already exists: %s (ID: %s) — updating to version %s...',
                     alias_name, alias_id, bot_version)
        lex_client.update_bot_alias(
            botAliasId=alias_id,
            botAliasName=alias_name,
            botId=bot_id,
            botVersion=bot_version,
            botAliasLocaleSettings={
                locale_id: {'enabled': True}
            },
        )
        logger.info('Bot alias updated.')
    else:
        logger.info('Creating bot alias: %s → version %s', alias_name, bot_version)
        resp = lex_client.create_bot_alias(
            botAliasName=alias_name,
            botId=bot_id,
            botVersion=bot_version,
            botAliasLocaleSettings={
                locale_id: {'enabled': True}
            },
            description='Live alias for Connect integration',
        )
        alias_id = resp['botAliasId']
        logger.info('Bot alias created. ID: %s', alias_id)

    bot_alias_arn = f'arn:aws:lex:{region}:{account_id}:bot-alias/{bot_id}/{alias_id}'
    logger.info('Bot alias ARN: %s', bot_alias_arn)

    # --- Sub-step 7: Associate with Connect ---
    connect_client = session.client('connect')
    try:
        connect_client.associate_bot(
            InstanceId=connect_instance_id,
            LexV2Bot={'AliasArn': bot_alias_arn},
        )
        logger.info('Bot associated with Connect instance %s.', connect_instance_id)
    except Exception as e:
        err_str = str(e).lower()
        if 'already' in err_str or 'duplicate' in err_str or 'conflict' in err_str:
            logger.info('Bot already associated with Connect instance.')
        else:
            logger.warning('Could not associate bot with Connect: %s', e)
            logger.info('Associate the bot manually: Connect console → Routing → Flows → Bots')

    return {
        'botId': bot_id,
        'botVersion': bot_version,
        'botAliasId': alias_id,
        'botAliasArn': bot_alias_arn,
    }


# ---------------------------------------------------------------------------
# Intake Bot — ListPicker-driven routing bot
# ---------------------------------------------------------------------------


def create_intake_lex_bot(session, bot_name, bot_description, role_arn,
                          intake_lambda_arn, connect_instance_id,
                          locale_id=LEX_BOT_LOCALE,
                          nlu_threshold=LEX_BOT_NLU_THRESHOLD,
                          idle_session_ttl=LEX_BOT_IDLE_SESSION_TTL,
                          alias_name=INTAKE_BOT_ALIAS_NAME):
    """Create the Stability360 Intake Lex V2 bot.

    The intake bot uses a single-slot loop pattern:
      - IntakeIntent with one FreeFormInput slot (IntakeResponse)
      - Dialog + elicitation + fulfillment code hooks → Lambda sends ListPicker
      - RouteToThriveAtWork intent (programmatic — no utterances)
      - RouteToGeneral intent (programmatic — no utterances)

    The Lambda switches the active intent to RouteToThriveAtWork or
    RouteToGeneral based on the user's ListPicker selection.  The contact
    flow then conditions on the returned intent name to route the customer.

    Returns a dict with botId, botVersion, botAliasId, botAliasArn or None.
    """
    lex_client = session.client('lexv2-models')
    region = session.region_name
    account_id = session.client('sts').get_caller_identity()['Account']

    # --- Sub-step 1: Create or find bot ---
    bot_id = None
    try:
        bots = lex_client.list_bots(
            filters=[{'name': 'BotName', 'values': [bot_name], 'operator': 'EQ'}],
        )
        for b in bots.get('botSummaries', []):
            if b['botName'] == bot_name:
                bot_id = b['botId']
                break
    except ClientError:
        logger.debug('Could not list bots for intake bot lookup', exc_info=True)

    if bot_id:
        logger.info('Intake bot already exists: %s (ID: %s)', bot_name, bot_id)
    else:
        logger.info('Creating intake bot: %s', bot_name)
        resp = lex_client.create_bot(
            botName=bot_name,
            description=bot_description,
            roleArn=role_arn,
            dataPrivacy={'childDirected': False},
            idleSessionTTLInSeconds=idle_session_ttl,
        )
        bot_id = resp['botId']
        logger.info('Intake bot created. ID: %s', bot_id)
        time.sleep(3)

    # --- Sub-step 2: Create bot locale ---
    try:
        lex_client.describe_bot_locale(
            botId=bot_id, botVersion='DRAFT', localeId=locale_id,
        )
        logger.info('Bot locale %s already exists.', locale_id)
    except lex_client.exceptions.ResourceNotFoundException:
        logger.info('Creating bot locale: %s', locale_id)
        lex_client.create_bot_locale(
            botId=bot_id,
            botVersion='DRAFT',
            localeId=locale_id,
            nluIntentConfidenceThreshold=nlu_threshold,
        )
        logger.info('Bot locale created.')
        time.sleep(2)

    # --- Sub-step 3: Create IntakeIntent ---
    intake_intent_id = None
    try:
        intents = lex_client.list_intents(
            botId=bot_id, botVersion='DRAFT', localeId=locale_id,
        )
        for i in intents.get('intentSummaries', []):
            if i.get('intentName') == 'IntakeIntent':
                intake_intent_id = i['intentId']
                break
    except ClientError:
        logger.debug('Could not list intents for IntakeIntent lookup', exc_info=True)

    if intake_intent_id:
        logger.info('IntakeIntent already exists (ID: %s).', intake_intent_id)
    else:
        logger.info('Creating IntakeIntent...')
        resp = lex_client.create_intent(
            intentName='IntakeIntent',
            botId=bot_id,
            botVersion='DRAFT',
            localeId=locale_id,
            description='Main intake intent — shows service menu via ListPicker',
            sampleUtterances=[
                {'utterance': 'hello'},
                {'utterance': 'hi'},
                {'utterance': 'help'},
                {'utterance': 'get started'},
                {'utterance': 'start'},
                {'utterance': 'menu'},
                {'utterance': 'options'},
                {'utterance': 'services'},
            ],
            dialogCodeHook={'enabled': True},
            fulfillmentCodeHook={'enabled': True},
        )
        intake_intent_id = resp['intentId']
        logger.info('IntakeIntent created (ID: %s).', intake_intent_id)
        time.sleep(1)

    # --- Sub-step 3b: Create IntakeResponse slot on IntakeIntent ---
    intake_slot_id = None
    try:
        slots = lex_client.list_slots(
            botId=bot_id, botVersion='DRAFT', localeId=locale_id,
            intentId=intake_intent_id,
        )
        for s in slots.get('slotSummaries', []):
            if s.get('slotName') == 'IntakeResponse':
                intake_slot_id = s['slotId']
                break
    except ClientError:
        logger.debug('Could not list slots for IntakeResponse lookup', exc_info=True)

    slot_value_elicitation = {
        'slotConstraint': 'Required',
        'promptSpecification': {
            'messageGroups': [{
                'message': {
                    'plainTextMessage': {
                        'value': 'Please select a service from the menu.',
                    },
                },
            }],
            'maxRetries': 2,
        },
        'slotCaptureSetting': {
            'captureNextStep': {
                'dialogAction': {'type': 'InvokeDialogCodeHook'},
            },
            'failureNextStep': {
                'dialogAction': {
                    'type': 'ElicitSlot',
                    'slotToElicit': 'IntakeResponse',
                },
            },
            'codeHook': {
                'enableCodeHookInvocation': True,
                'active': True,
                'postCodeHookSpecification': {},
            },
            'elicitationCodeHook': {
                'enableCodeHookInvocation': True,
            },
        },
    }

    if intake_slot_id:
        logger.info('IntakeResponse slot already exists (ID: %s) — updating...', intake_slot_id)
        try:
            lex_client.update_slot(
                slotId=intake_slot_id,
                slotName='IntakeResponse',
                botId=bot_id,
                botVersion='DRAFT',
                localeId=locale_id,
                intentId=intake_intent_id,
                slotTypeId='AMAZON.FreeFormInput',
                valueElicitationSetting=slot_value_elicitation,
            )
        except ClientError as e:
            logger.warning('Could not update IntakeResponse slot: %s', e)
    else:
        logger.info('Creating IntakeResponse slot...')
        # Find AMAZON.FreeFormInput slot type
        resp = lex_client.create_slot(
            slotName='IntakeResponse',
            botId=bot_id,
            botVersion='DRAFT',
            localeId=locale_id,
            intentId=intake_intent_id,
            slotTypeId='AMAZON.FreeFormInput',
            valueElicitationSetting=slot_value_elicitation,
        )
        intake_slot_id = resp['slotId']
        logger.info('IntakeResponse slot created (ID: %s).', intake_slot_id)

    # --- Sub-step 3c: Ensure IntakeIntent priorities include IntakeResponse ---
    try:
        lex_client.update_intent(
            intentId=intake_intent_id,
            intentName='IntakeIntent',
            botId=bot_id,
            botVersion='DRAFT',
            localeId=locale_id,
            description='Main intake intent — shows service menu via ListPicker',
            sampleUtterances=[
                {'utterance': 'hello'},
                {'utterance': 'hi'},
                {'utterance': 'help'},
                {'utterance': 'get started'},
                {'utterance': 'start'},
                {'utterance': 'menu'},
                {'utterance': 'options'},
                {'utterance': 'services'},
            ],
            dialogCodeHook={'enabled': True},
            fulfillmentCodeHook={'enabled': True},
            slotPriorities=[
                {'priority': 1, 'slotId': intake_slot_id},
            ],
        )
        logger.info('IntakeIntent updated with slot priorities.')
    except Exception as e:
        logger.warning('Could not update IntakeIntent slot priorities: %s', e)

    # --- Sub-step 4: Create routing intents ---
    for route_intent_name in ('RouteToThriveAtWork', 'RouteToGeneral'):
        route_id = None
        try:
            intents = lex_client.list_intents(
                botId=bot_id, botVersion='DRAFT', localeId=locale_id,
            )
            for i in intents.get('intentSummaries', []):
                if i.get('intentName') == route_intent_name:
                    route_id = i['intentId']
                    break
        except ClientError:
            logger.debug('Could not list intents for %s lookup', route_intent_name, exc_info=True)

        if route_id:
            logger.info('%s already exists (ID: %s).', route_intent_name, route_id)
        else:
            logger.info('Creating %s intent...', route_intent_name)
            lex_client.create_intent(
                intentName=route_intent_name,
                botId=bot_id,
                botVersion='DRAFT',
                localeId=locale_id,
                description=f'Programmatic routing intent — set by Lambda (no utterances)',
            )
            logger.info('%s created.', route_intent_name)

    # --- Sub-step 5: Update FallbackIntent to invoke code hook ---
    try:
        intents = lex_client.list_intents(
            botId=bot_id, botVersion='DRAFT', localeId=locale_id,
        )
        fallback_id = None
        for i in intents.get('intentSummaries', []):
            if i.get('intentName') == 'FallbackIntent':
                fallback_id = i['intentId']
                break
        if fallback_id:
            lex_client.update_intent(
                intentId=fallback_id,
                intentName='FallbackIntent',
                botId=bot_id,
                botVersion='DRAFT',
                localeId=locale_id,
                parentIntentSignature='AMAZON.FallbackIntent',
                fulfillmentCodeHook={'enabled': True},
            )
            logger.info('FallbackIntent updated to invoke code hook.')
    except Exception as e:
        logger.warning('Could not update FallbackIntent: %s', e)

    # --- Sub-step 6: Build bot locale ---
    logger.info('Building intake bot locale...')
    lex_client.build_bot_locale(
        botId=bot_id, botVersion='DRAFT', localeId=locale_id,
    )
    build_status = wait_for_bot_locale_build(
        lex_client, bot_id, 'DRAFT', locale_id,
    )
    if build_status != 'Built':
        logger.error('Intake bot locale build did not succeed: %s', build_status)
        return None
    logger.info('Intake bot locale built successfully.')

    # --- Sub-step 7: Create bot version ---
    logger.info('Creating intake bot version...')
    resp = lex_client.create_bot_version(
        botId=bot_id,
        botVersionLocaleSpecification={
            locale_id: {'sourceBotVersion': 'DRAFT'}
        },
        description='Auto-created by deploy.py',
    )
    bot_version = resp['botVersion']
    ver_status = resp.get('botStatus', 'Creating')
    logger.info('Intake bot version: %s (status: %s)', bot_version, ver_status)

    if ver_status != 'Available':
        _ver_start = time.time()
        time.sleep(2)
        while time.time() - _ver_start < LEX_BOT_BUILD_TIMEOUT:
            try:
                desc = lex_client.describe_bot_version(botId=bot_id, botVersion=bot_version)
                ver_status = desc.get('botStatus', 'Unknown')
            except lex_client.exceptions.ResourceNotFoundException:
                elapsed = int(time.time() - _ver_start)
                logger.info('  Intake bot version not yet available (%ds elapsed)', elapsed)
                time.sleep(LEX_BOT_BUILD_POLL_INTERVAL)
                continue
            if ver_status == 'Available':
                logger.info('Intake bot version %s is Available.', bot_version)
                break
            if ver_status in ('Failed', 'Deleting'):
                raise RuntimeError(f'Intake bot version {bot_version} entered {ver_status} state.')
            elapsed = int(time.time() - _ver_start)
            logger.info('  Intake bot version status: %s (%ds elapsed)', ver_status, elapsed)
            time.sleep(LEX_BOT_BUILD_POLL_INTERVAL)
        else:
            raise TimeoutError(f'Intake bot version did not become Available within {LEX_BOT_BUILD_TIMEOUT}s')

    # --- Sub-step 8: Create or update bot alias with Lambda code hook ---
    alias_id, _ = find_existing_bot_alias(lex_client, bot_id, alias_name)
    code_hook_spec = {
        locale_id: {
            'enabled': True,
            'codeHookSpecification': {
                'lambdaCodeHook': {
                    'lambdaARN': intake_lambda_arn,
                    'codeHookInterfaceVersion': '1.0',
                },
            },
        },
    }

    if alias_id:
        logger.info('Intake bot alias exists: %s (ID: %s) — updating to version %s...',
                     alias_name, alias_id, bot_version)
        lex_client.update_bot_alias(
            botAliasId=alias_id,
            botAliasName=alias_name,
            botId=bot_id,
            botVersion=bot_version,
            botAliasLocaleSettings=code_hook_spec,
        )
        logger.info('Intake bot alias updated.')
    else:
        logger.info('Creating intake bot alias: %s → version %s', alias_name, bot_version)
        resp = lex_client.create_bot_alias(
            botAliasName=alias_name,
            botId=bot_id,
            botVersion=bot_version,
            botAliasLocaleSettings=code_hook_spec,
            description='Live alias for Connect integration',
        )
        alias_id = resp['botAliasId']
        logger.info('Intake bot alias created. ID: %s', alias_id)

    # --- Sub-step 9: Add Lambda permission for Lex to invoke ---
    lambda_client = session.client('lambda')
    statement_id = f'LexV2-{bot_id}-{alias_id}'
    try:
        lambda_client.add_permission(
            FunctionName=intake_lambda_arn,
            StatementId=statement_id,
            Action='lambda:InvokeFunction',
            Principal='lexv2.amazonaws.com',
            SourceArn=f'arn:aws:lex:{region}:{account_id}:bot-alias/{bot_id}/{alias_id}',
        )
        logger.info('Lambda permission added for Lex invocation.')
    except lambda_client.exceptions.ResourceConflictException:
        logger.info('Lambda permission already exists.')
    except Exception as e:
        logger.warning('Could not add Lambda permission: %s', e)

    bot_alias_arn = f'arn:aws:lex:{region}:{account_id}:bot-alias/{bot_id}/{alias_id}'
    logger.info('Intake bot alias ARN: %s', bot_alias_arn)

    # --- Sub-step 10: Associate with Connect ---
    connect_client = session.client('connect')
    try:
        connect_client.associate_bot(
            InstanceId=connect_instance_id,
            LexV2Bot={'AliasArn': bot_alias_arn},
        )
        logger.info('Intake bot associated with Connect instance %s.', connect_instance_id)
    except Exception as e:
        err_str = str(e).lower()
        if 'already' in err_str or 'duplicate' in err_str or 'conflict' in err_str:
            logger.info('Intake bot already associated with Connect instance.')
        else:
            logger.warning('Could not associate intake bot with Connect: %s', e)

    return {
        'botId': bot_id,
        'botVersion': bot_version,
        'botAliasId': alias_id,
        'botAliasArn': bot_alias_arn,
    }


# ---------------------------------------------------------------------------
# Contact Flow — Self-service chat with CreateWisdomSession + Lex Bot
# ---------------------------------------------------------------------------


def _build_contact_flow_content(assistant_arn, bot_alias_arn, ai_agent_version_arn,
                                intake_bot_alias_arn=None):
    """Build the Amazon Connect contact flow JSON for self-service chat.

    If intake_bot_alias_arn is provided the flow routes through the intake
    bot first:

      1. ConnectParticipantWithLexBot (IntakeBot — shows ListPicker menu)
         -> RouteToThriveAtWork: CreateWisdomSession -> Stability360Bot
         -> RouteToGeneral:     "Coming soon" message -> Disconnect
         -> Error / NoMatch:    Disconnect
      2. CreateWisdomSession (link Q Connect assistant to contact)
      3. ConnectParticipantWithLexBot (Stability360Bot + AI agent ARN)
      4. DisconnectParticipant

    Without intake_bot_alias_arn the flow goes straight to Q Connect:
      Welcome -> CreateWisdomSession -> Stability360Bot -> Disconnect
    """
    if intake_bot_alias_arn:
        return _build_intake_contact_flow(
            assistant_arn, bot_alias_arn, ai_agent_version_arn,
            intake_bot_alias_arn,
        )

    # --- Legacy flow (no intake bot) ---
    flow = {
        'Version': '2019-10-30',
        'StartAction': 'welcome-msg',
        'Metadata': {
            'entryPointPosition': {'x': -110, 'y': 126},
            'ActionMetadata': {
                'disconnect': {'position': {'x': 740, 'y': 20}},
                'welcome-msg': {'position': {'x': 20, 'y': 20}},
                'create-wisdom': {
                    'position': {'x': 260, 'y': 20},
                    'children': ['set-wisdom-data'],
                    'fragments': {'SetContactData': 'set-wisdom-data'},
                },
                'set-wisdom-data': {
                    'position': {'x': 260, 'y': 20},
                    'dynamicParams': [],
                },
                'lex-bot': {
                    'position': {'x': 500, 'y': 20},
                    'children': ['set-lex-wisdom', 'connect-lex'],
                    'fragments': {'SetContactData': 'set-lex-wisdom'},
                },
                'set-lex-wisdom': {
                    'position': {'x': 500, 'y': 20},
                    'dynamicParams': [],
                },
                'greet-customer': {
                    'position': {'x': 680, 'y': 20},
                },
                'connect-lex': {
                    'position': {'x': 850, 'y': 20},
                    'parameters': {
                        'LexV2Bot': {'AliasArn': {}},
                    },
                    'dynamicMetadata': {
                        'x-amz-lex:q-in-connect:ai-agent-arn': False,
                    },
                    'conditionMetadata': [{
                        'id': 'qinconnect-condition',
                        'operator': {
                            'name': 'Equals',
                            'value': 'Equals',
                            'shortDisplay': '=',
                        },
                        'value': 'AmazonQinConnect',
                    }],
                },
            },
        },
        'Actions': [
            {
                'Parameters': {},
                'Identifier': 'disconnect',
                'Type': 'DisconnectParticipant',
                'Transitions': {},
            },
            {
                'Parameters': {
                    'Text': (
                        'Welcome to Stability360 Thrive@Work! '
                        'How can I help you today?'
                    ),
                },
                'Identifier': 'welcome-msg',
                'Type': 'MessageParticipant',
                'Transitions': {
                    'NextAction': 'create-wisdom',
                    'Errors': [{'NextAction': 'create-wisdom', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {'WisdomAssistantArn': assistant_arn},
                'Identifier': 'create-wisdom',
                'Type': 'CreateWisdomSession',
                'Transitions': {
                    'NextAction': 'set-wisdom-data',
                    'Errors': [{'NextAction': 'lex-bot', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {'WisdomSessionArn': '$.Wisdom.SessionArn'},
                'Identifier': 'set-wisdom-data',
                'Type': 'UpdateContactData',
                'Transitions': {
                    'NextAction': 'lex-bot',
                    'Errors': [{'NextAction': 'lex-bot', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {'WisdomAssistantArn': assistant_arn},
                'Identifier': 'lex-bot',
                'Type': 'CreateWisdomSession',
                'Transitions': {
                    'NextAction': 'set-lex-wisdom',
                    'Errors': [{'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {'WisdomSessionArn': '$.Wisdom.SessionArn'},
                'Identifier': 'set-lex-wisdom',
                'Type': 'UpdateContactData',
                'Transitions': {
                    'NextAction': 'greet-customer',
                    'Errors': [{'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'}],
                },
            },
            # Visible greeting so the customer knows the AI agent is ready
            {
                'Parameters': {
                    'Text': 'How can I help you today?',
                },
                'Identifier': 'greet-customer',
                'Type': 'MessageParticipant',
                'Transitions': {
                    'NextAction': 'connect-lex',
                    'Errors': [{'NextAction': 'connect-lex', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {
                    'LexInitializationData': {
                        'InitialMessage': 'Hello',
                    },
                    'LexV2Bot': {'AliasArn': bot_alias_arn},
                    'LexSessionAttributes': {
                        'x-amz-lex:q-in-connect:ai-agent-arn': ai_agent_version_arn,
                    },
                },
                'Identifier': 'connect-lex',
                'Type': 'ConnectParticipantWithLexBot',
                'Transitions': {
                    'NextAction': 'disconnect',
                    'Conditions': [{
                        'NextAction': 'disconnect',
                        'Condition': {
                            'Operator': 'Equals',
                            'Operands': ['AmazonQinConnect'],
                        },
                    }],
                    'Errors': [
                        {'NextAction': 'disconnect', 'ErrorType': 'NoMatchingCondition'},
                        {'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'},
                    ],
                },
            },
        ],
    }
    return json.dumps(flow)


def _build_intake_contact_flow(assistant_arn, bot_alias_arn,
                                ai_agent_version_arn, intake_bot_alias_arn):
    """Build contact flow with intake bot routing.

    Simple linear flow — the IntakeBot Lambda handles all branching internally
    (General -> "coming soon" + re-show menu, staying in the bot). The bot
    only closes (exits) when the user selects Thrive@Work.

    Flow:
      IntakeBot (menu — only exits on Thrive@Work)
        -> CreateWisdomSession -> UpdateContactData
        -> CreateWisdomSession -> UpdateContactData
        -> MessageParticipant (greeting prompt)
        -> ConnectParticipantWithLexBot (Stability360Bot + AI agent)
        -> Disconnect
    """
    flow = {
        'Version': '2019-10-30',
        'StartAction': 'intake-bot',
        'Metadata': {
            'entryPointPosition': {'x': -110, 'y': 126},
            'ActionMetadata': {
                'disconnect': {'position': {'x': 1100, 'y': 20}},
                'intake-bot': {
                    'position': {'x': 20, 'y': 20},
                    'parameters': {
                        'LexV2Bot': {'AliasArn': {}},
                    },
                },
                'create-wisdom': {
                    'position': {'x': 250, 'y': 20},
                    'children': ['set-wisdom-data'],
                    'fragments': {'SetContactData': 'set-wisdom-data'},
                },
                'set-wisdom-data': {
                    'position': {'x': 250, 'y': 20},
                    'dynamicParams': [],
                },
                'lex-bot': {
                    'position': {'x': 500, 'y': 20},
                    'children': ['set-lex-wisdom', 'connect-lex'],
                    'fragments': {'SetContactData': 'set-lex-wisdom'},
                },
                'set-lex-wisdom': {
                    'position': {'x': 500, 'y': 20},
                    'dynamicParams': [],
                },
                'greet-customer': {
                    'position': {'x': 680, 'y': 20},
                },
                'connect-lex': {
                    'position': {'x': 850, 'y': 20},
                    'parameters': {
                        'LexV2Bot': {'AliasArn': {}},
                    },
                    'dynamicMetadata': {
                        'x-amz-lex:q-in-connect:ai-agent-arn': False,
                    },
                    'conditionMetadata': [{
                        'id': 'qinconnect-condition',
                        'operator': {
                            'name': 'Equals',
                            'value': 'Equals',
                            'shortDisplay': '=',
                        },
                        'value': 'AmazonQinConnect',
                    }],
                },
            },
        },
        'Actions': [
            # Disconnect
            {
                'Parameters': {},
                'Identifier': 'disconnect',
                'Type': 'DisconnectParticipant',
                'Transitions': {},
            },
            # Step 1: Intake Bot (ListPicker menu)
            # The bot only closes when the user selects Thrive@Work.
            # After close, the flow continues linearly to CreateWisdomSession.
            # NOTE: ConnectParticipantWithLexBot uses LexInitializationData
            # (not Text) for the initial message sent to the bot.
            {
                'Parameters': {
                    'LexInitializationData': {
                        'InitialMessage': 'Hello',
                    },
                    'LexV2Bot': {'AliasArn': intake_bot_alias_arn},
                },
                'Identifier': 'intake-bot',
                'Type': 'ConnectParticipantWithLexBot',
                'Transitions': {
                    'NextAction': 'create-wisdom',
                    'Conditions': [{
                        'NextAction': 'create-wisdom',
                        'Condition': {
                            'Operator': 'Equals',
                            'Operands': ['IntakeIntent'],
                        },
                    }],
                    'Errors': [
                        {'NextAction': 'disconnect', 'ErrorType': 'NoMatchingCondition'},
                        {'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'},
                    ],
                },
            },
            # Step 2: CreateWisdomSession (link Q Connect assistant to contact)
            {
                'Parameters': {'WisdomAssistantArn': assistant_arn},
                'Identifier': 'create-wisdom',
                'Type': 'CreateWisdomSession',
                'Transitions': {
                    'NextAction': 'set-wisdom-data',
                    'Errors': [{'NextAction': 'lex-bot', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {'WisdomSessionArn': '$.Wisdom.SessionArn'},
                'Identifier': 'set-wisdom-data',
                'Type': 'UpdateContactData',
                'Transitions': {
                    'NextAction': 'lex-bot',
                    'Errors': [{'NextAction': 'lex-bot', 'ErrorType': 'NoMatchingError'}],
                },
            },
            # Step 3: Second CreateWisdomSession + Connect with Stability360Bot
            {
                'Parameters': {'WisdomAssistantArn': assistant_arn},
                'Identifier': 'lex-bot',
                'Type': 'CreateWisdomSession',
                'Transitions': {
                    'NextAction': 'set-lex-wisdom',
                    'Errors': [{'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {'WisdomSessionArn': '$.Wisdom.SessionArn'},
                'Identifier': 'set-lex-wisdom',
                'Type': 'UpdateContactData',
                'Transitions': {
                    'NextAction': 'greet-customer',
                    'Errors': [{'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'}],
                },
            },
            # Visible greeting so the customer knows the AI agent is ready
            {
                'Parameters': {
                    'Text': 'Welcome to Thrive@Work! How can I help you today?',
                },
                'Identifier': 'greet-customer',
                'Type': 'MessageParticipant',
                'Transitions': {
                    'NextAction': 'connect-lex',
                    'Errors': [{'NextAction': 'connect-lex', 'ErrorType': 'NoMatchingError'}],
                },
            },
            {
                'Parameters': {
                    'LexInitializationData': {
                        'InitialMessage': 'Hello',
                    },
                    'LexV2Bot': {'AliasArn': bot_alias_arn},
                    'LexSessionAttributes': {
                        'x-amz-lex:q-in-connect:ai-agent-arn': ai_agent_version_arn,
                    },
                },
                'Identifier': 'connect-lex',
                'Type': 'ConnectParticipantWithLexBot',
                'Transitions': {
                    'NextAction': 'disconnect',
                    'Conditions': [{
                        'NextAction': 'disconnect',
                        'Condition': {
                            'Operator': 'Equals',
                            'Operands': ['AmazonQinConnect'],
                        },
                    }],
                    'Errors': [
                        {'NextAction': 'disconnect', 'ErrorType': 'NoMatchingCondition'},
                        {'NextAction': 'disconnect', 'ErrorType': 'NoMatchingError'},
                    ],
                },
            },
        ],
    }
    return json.dumps(flow)


def create_or_update_contact_flow(session, connect_instance_id,
                                   assistant_arn, bot_alias_arn,
                                   ai_agent_version_arn,
                                   intake_bot_alias_arn=None,
                                   flow_name=None):
    """Create or update the self-service contact flow.

    The flow routes chat customers through:
      IntakeBot (optional) -> CreateWisdomSession -> ConnectParticipantWithLexBot
    which enables Q Connect AI agent with MCP tools.

    Returns the contact flow ID, or None on failure.
    """
    flow_name = flow_name or CONTACT_FLOW_NAME
    connect_client = session.client('connect')
    content = _build_contact_flow_content(
        assistant_arn, bot_alias_arn, ai_agent_version_arn,
        intake_bot_alias_arn=intake_bot_alias_arn,
    )

    # Check if flow already exists
    existing_flow_id = None
    try:
        paginator = connect_client.get_paginator('list_contact_flows')
        for page in paginator.paginate(InstanceId=connect_instance_id):
            for cf in page.get('ContactFlowSummaryList', []):
                if cf['Name'] == flow_name:
                    existing_flow_id = cf['Id']
                    break
            if existing_flow_id:
                break
    except Exception as e:
        logger.warning('Could not list contact flows: %s', e)

    if existing_flow_id:
        logger.info('Contact flow already exists: %s (ID: %s) — updating...', flow_name, existing_flow_id)
        try:
            connect_client.update_contact_flow_content(
                InstanceId=connect_instance_id,
                ContactFlowId=existing_flow_id,
                Content=content,
            )
            logger.info('Contact flow updated.')
            return existing_flow_id
        except Exception as e:
            logger.warning('Could not update contact flow: %s', e)
            logger.warning('Contact flow exists (ID: %s) but update failed — check flow manually.', existing_flow_id)
            return None

    # Create new flow
    logger.info('Creating contact flow: %s', flow_name)
    try:
        resp = connect_client.create_contact_flow(
            InstanceId=connect_instance_id,
            Name=flow_name,
            Type='CONTACT_FLOW',
            Description=CONTACT_FLOW_DESCRIPTION,
            Content=content,
            Status='PUBLISHED',
        )
        flow_id = resp['ContactFlowId']
        logger.info('Contact flow created: %s (ID: %s)', flow_name, flow_id)
        return flow_id
    except Exception as e:
        logger.warning('Could not create contact flow: %s', e)
        logger.info('Create the flow manually in Connect console with:')
        logger.info('  1. MessageParticipant (welcome message)')
        logger.info('  2. CreateWisdomSession (assistant: %s)', assistant_arn)
        logger.info('  3. ConnectParticipantWithLexBot (bot alias: %s)', bot_alias_arn)
        return None


# ---------------------------------------------------------------------------
# Q Connect Knowledge Base Integration
# ---------------------------------------------------------------------------


def update_kb_bucket_policy(s3_client, bucket_name, bucket_arn):
    """Add app-integrations and wisdom service principals to the S3 bucket policy.

    Merges the required statements into any existing bucket policy, preserving
    statements that were already present. Idempotent: statements are matched
    by Sid and replaced with the current version.
    """
    required_sids = {
        'AllowQConnectKBListBucket',
        'AllowQConnectKBGetObject',
        'AllowQConnectKBGetBucketLocation',
    }

    new_statements = [
        {
            'Sid': 'AllowQConnectKBListBucket',
            'Effect': 'Allow',
            'Principal': {'Service': list(KB_S3_PRINCIPALS)},
            'Action': 's3:ListBucket',
            'Resource': bucket_arn,
        },
        {
            'Sid': 'AllowQConnectKBGetObject',
            'Effect': 'Allow',
            'Principal': {'Service': list(KB_S3_PRINCIPALS)},
            'Action': 's3:GetObject',
            'Resource': f'{bucket_arn}/*',
        },
        {
            'Sid': 'AllowQConnectKBGetBucketLocation',
            'Effect': 'Allow',
            'Principal': {'Service': list(KB_S3_PRINCIPALS)},
            'Action': 's3:GetBucketLocation',
            'Resource': bucket_arn,
        },
    ]

    # Get existing policy (if any)
    try:
        existing = s3_client.get_bucket_policy(Bucket=bucket_name)
        policy = json.loads(existing['Policy'])
    except Exception as e:
        if 'NoSuchBucketPolicy' in type(e).__name__ or 'NoSuchBucketPolicy' in str(e):
            policy = {'Version': '2012-10-17', 'Statement': []}
        else:
            raise

    # Remove any existing statements with our Sids (to replace cleanly)
    policy['Statement'] = [
        stmt for stmt in policy.get('Statement', [])
        if stmt.get('Sid') not in required_sids
    ]
    policy['Statement'].extend(new_statements)

    logger.info('Updating S3 bucket policy for KB access: %s', bucket_name)
    s3_client.put_bucket_policy(
        Bucket=bucket_name,
        Policy=json.dumps(policy),
    )
    logger.info('Bucket policy updated with Q Connect KB access.')


def find_existing_data_integration(appintegrations_client, integration_name):
    """Find an existing AppIntegrations DataIntegration by name.

    Returns (data_integration_id, data_integration_arn) or (None, None).
    """
    try:
        resp = appintegrations_client.list_data_integrations()
        for di in resp.get('DataIntegrations', []):
            if di.get('Name') == integration_name:
                arn = di.get('Arn', '')
                return arn, arn
    except ClientError:
        logger.debug('Could not list data integrations', exc_info=True)
    return None, None


def ensure_kb_kms_key(kms_client, alias_name='alias/stability360-kb'):
    """Ensure a KMS key exists for the KB DataIntegration.

    AppIntegrations requires a KMS key for data encryption. This function
    creates one if it doesn't already exist. Returns the key ARN.
    """
    # Check if alias already exists
    try:
        resp = kms_client.describe_key(KeyId=alias_name)
        key_arn = resp['KeyMetadata']['Arn']
        logger.info('KMS key already exists: %s', alias_name)
        return key_arn
    except ClientError as e:
        if e.response['Error']['Code'] != 'NotFoundException':
            raise
    # Create a new key
    logger.info('Creating KMS key for KB integration...')
    key_resp = kms_client.create_key(
        Description='Encryption key for Stability360 Q Connect knowledge base integration',
        KeyUsage='ENCRYPT_DECRYPT',
    )
    key_id = key_resp['KeyMetadata']['KeyId']
    key_arn = key_resp['KeyMetadata']['Arn']

    # Create alias for easy lookup
    try:
        kms_client.create_alias(
            AliasName=alias_name,
            TargetKeyId=key_id,
        )
        logger.info('KMS key created: %s (alias: %s)', key_arn, alias_name)
    except ClientError:
        logger.info('KMS key created: %s (alias creation failed)', key_arn)

    return key_arn


def create_or_get_data_integration(appintegrations_client, integration_name,
                                    bucket_name, description, kms_key_arn):
    """Create (or retrieve existing) an AppIntegrations DataIntegration for S3.

    The DataIntegration defines the connection between AppIntegrations and
    the S3 bucket. Its SourceURI must be s3://bucket-name.

    Returns the DataIntegration ARN, or None on failure.
    """
    source_uri = f's3://{bucket_name}'

    # Check for existing
    _, existing_arn = find_existing_data_integration(
        appintegrations_client, integration_name,
    )
    if existing_arn:
        logger.info('DataIntegration already exists: %s', integration_name)
        return existing_arn

    logger.info('Creating DataIntegration: %s', integration_name)
    logger.info('  SourceURI: %s', source_uri)
    try:
        resp = appintegrations_client.create_data_integration(
            Name=integration_name,
            Description=description,
            KmsKey=kms_key_arn,
            SourceURI=source_uri,
        )
        arn = resp.get('Arn')
        logger.info('DataIntegration created. ARN: %s', arn)
        return arn
    except Exception as e:
        err_str = str(e).lower()
        if 'already exists' in err_str or 'conflict' in err_str or 'duplicate' in err_str:
            logger.info('DataIntegration already exists (caught on create).')
            _, existing_arn = find_existing_data_integration(
                appintegrations_client, integration_name,
            )
            return existing_arn
        logger.warning('Could not create DataIntegration: %s', e)
        return None


def find_existing_knowledge_base(qconnect_client, kb_name):
    """Find an existing Q Connect knowledge base by name.

    Returns (knowledge_base_id, knowledge_base_arn) or (None, None).
    """
    try:
        resp = qconnect_client.list_knowledge_bases()
        for kb in resp.get('knowledgeBaseSummaries', []):
            if kb.get('name') == kb_name:
                return kb.get('knowledgeBaseId'), kb.get('knowledgeBaseArn')
    except ClientError:
        logger.debug('Could not list knowledge bases', exc_info=True)
    return None, None


def create_or_get_knowledge_base(qconnect_client, kb_name, description,
                                   data_integration_arn):
    """Create (or retrieve existing) a Q Connect EXTERNAL knowledge base.

    Creates a knowledge base backed by the AppIntegrations DataIntegration
    that points to the S3 bucket. If an existing KB has the right name but
    is linked to a different DataIntegration, it is deleted and recreated.

    Returns (knowledge_base_id, knowledge_base_arn) or (None, None).
    """
    # Check for existing
    existing_id, existing_arn = find_existing_knowledge_base(qconnect_client, kb_name)
    if existing_id:
        # Verify it's linked to the correct DataIntegration
        try:
            kb_resp = qconnect_client.get_knowledge_base(knowledgeBaseId=existing_id)
            kb = kb_resp.get('knowledgeBase', {})
            src = kb.get('sourceConfiguration', {}).get('appIntegrations', {})
            linked_di_arn = src.get('appIntegrationArn', '')
            if linked_di_arn and linked_di_arn != data_integration_arn:
                logger.info(
                    'KB %s linked to wrong DataIntegration (%s != %s). Recreating...',
                    existing_id, linked_di_arn, data_integration_arn,
                )
                qconnect_client.delete_knowledge_base(knowledgeBaseId=existing_id)
                logger.info('Deleted old KB %s', existing_id)
            else:
                logger.info('Knowledge base already exists: %s (ID: %s)', kb_name, existing_id)
                return existing_id, existing_arn
        except Exception as e:
            logger.debug('Could not verify KB DataIntegration link: %s', e)
            logger.info('Knowledge base already exists: %s (ID: %s)', kb_name, existing_id)
            return existing_id, existing_arn

    logger.info('Creating Q Connect knowledge base: %s', kb_name)
    logger.info('  Type: EXTERNAL')
    logger.info('  DataIntegration: %s', data_integration_arn)
    try:
        resp = qconnect_client.create_knowledge_base(
            name=kb_name,
            description=description,
            knowledgeBaseType='EXTERNAL',
            sourceConfiguration={
                'appIntegrations': {
                    'appIntegrationArn': data_integration_arn,
                }
            },
        )
        kb = resp.get('knowledgeBase', {})
        kb_id = kb.get('knowledgeBaseId')
        kb_arn = kb.get('knowledgeBaseArn')
        logger.info('Knowledge base created. ID: %s', kb_id)
        return kb_id, kb_arn
    except Exception as e:
        err_str = str(e).lower()
        if 'already exists' in err_str or 'conflict' in err_str:
            logger.info('Knowledge base already exists (caught on create).')
            return find_existing_knowledge_base(qconnect_client, kb_name)
        logger.warning('Could not create knowledge base: %s', e)
        return None, None


def find_existing_kb_association(qconnect_client, assistant_id):
    """Check if the assistant already has a KNOWLEDGE_BASE association.

    An assistant can have only ONE knowledge base association.
    Returns (association_id, kb_id) or (None, None) if none found.
    """
    try:
        resp = qconnect_client.list_assistant_associations(
            assistantId=assistant_id,
        )
        for assoc in resp.get('assistantAssociationSummaries', []):
            assoc_type = assoc.get('associationType', '')
            if assoc_type != 'KNOWLEDGE_BASE':
                continue
            assoc_id = assoc.get('assistantAssociationId')
            assoc_data = assoc.get('associationData', {})
            kb_data = assoc_data.get('knowledgeBaseAssociation', {})
            kb_id = kb_data.get('knowledgeBaseId')
            return assoc_id, kb_id
    except ClientError:
        logger.debug('Could not list assistant associations', exc_info=True)
    return None, None


def associate_kb_with_assistant(qconnect_client, assistant_id, knowledge_base_id):
    """Associate a knowledge base with a Q Connect assistant.

    An assistant supports only ONE knowledge base association. If an association
    already exists with the SAME KB, this is a no-op. If an association exists
    with a DIFFERENT KB, a warning is logged and the existing one is kept.

    Returns True if association is in place, False otherwise.
    """
    existing_assoc_id, existing_kb_id = find_existing_kb_association(
        qconnect_client, assistant_id,
    )

    if existing_assoc_id:
        if existing_kb_id == knowledge_base_id:
            logger.info('KB already associated with assistant: KB=%s', knowledge_base_id)
            return True
        else:
            logger.warning(
                'Assistant already has a DIFFERENT KB association: '
                'existing=%s, requested=%s. '
                'Only one KB per assistant is allowed. '
                'Remove the existing association manually if you want to replace it.',
                existing_kb_id, knowledge_base_id,
            )
            return False

    logger.info('Associating KB %s with assistant %s...', knowledge_base_id, assistant_id)
    try:
        qconnect_client.create_assistant_association(
            assistantId=assistant_id,
            associationType='KNOWLEDGE_BASE',
            association={
                'knowledgeBaseId': knowledge_base_id,
            },
        )
        logger.info('KB associated with assistant.')
        return True
    except Exception as e:
        err_str = str(e).lower()
        if 'already' in err_str or 'conflict' in err_str:
            logger.info('KB association already exists (caught on create).')
            return True
        logger.warning('Could not associate KB with assistant: %s', e)
        return False


def ensure_kb_bucket_in_region(s3_client, source_bucket_name, target_region, account_id):
    """Ensure a KB bucket exists in the target region.

    If the source bucket is already in the target region, returns it as-is.
    Otherwise, creates a new bucket in the target region with the same
    folder structure and encryption settings.

    Returns (bucket_name, bucket_arn) for the bucket in the target region.
    """
    # Check if source bucket is already in the target region
    try:
        loc = s3_client.get_bucket_location(Bucket=source_bucket_name)
        bucket_region = loc.get('LocationConstraint') or 'us-east-1'
        if bucket_region == target_region:
            bucket_arn = f'arn:aws:s3:::{source_bucket_name}'
            return source_bucket_name, bucket_arn
    except ClientError:
        logger.debug('Could not check bucket location for %s', source_bucket_name, exc_info=True)

    # Need a bucket in the target region — derive name from stack pattern
    # Source pattern: {stack}-kb-data-{source_region}-{account}
    # Target pattern: {stack}-kb-data-{target_region}-{account}
    import re
    region_pattern = re.compile(r'-kb-data-[a-z]{2}-[a-z]+-\d+-')
    if region_pattern.search(source_bucket_name):
        target_bucket_name = region_pattern.sub(
            f'-kb-data-{target_region}-', source_bucket_name,
        )
    else:
        target_bucket_name = f'{source_bucket_name}-{target_region}'
    # S3 bucket names max 63 chars
    target_bucket_name = target_bucket_name[:63]

    target_arn = f'arn:aws:s3:::{target_bucket_name}'

    # Check if target bucket already exists
    try:
        s3_client.head_bucket(Bucket=target_bucket_name)
        logger.info('KB bucket already exists in %s: %s', target_region, target_bucket_name)
        return target_bucket_name, target_arn
    except ClientError:
        pass  # Bucket doesn't exist — create it below

    # Create the bucket
    logger.info('Creating KB bucket in %s: %s', target_region, target_bucket_name)
    create_kwargs = {
        'Bucket': target_bucket_name,
    }
    # us-east-1 doesn't accept LocationConstraint
    if target_region != 'us-east-1':
        create_kwargs['CreateBucketConfiguration'] = {
            'LocationConstraint': target_region,
        }
    s3_client.create_bucket(**create_kwargs)

    # Enable versioning and encryption to match source
    s3_client.put_bucket_versioning(
        Bucket=target_bucket_name,
        VersioningConfiguration={'Status': 'Enabled'},
    )
    s3_client.put_bucket_encryption(
        Bucket=target_bucket_name,
        ServerSideEncryptionConfiguration={
            'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]
        },
    )
    s3_client.put_public_access_block(
        Bucket=target_bucket_name,
        PublicAccessBlockConfiguration={
            'BlockPublicAcls': True,
            'IgnorePublicAcls': True,
            'BlockPublicPolicy': True,
            'RestrictPublicBuckets': True,
        },
    )

    # Create KB folder structure
    for folder in KB_FOLDER_STRUCTURE:
        s3_client.put_object(Bucket=target_bucket_name, Key=folder, Body=b'')

    logger.info('KB bucket created with folder structure.')
    return target_bucket_name, target_arn


def _cleanup_mismatched_kb_resources(qconnect_client, appintegrations_client,
                                      assistant_id, expected_name):
    """Remove KB resources whose names don't match the expected convention.

    The Amazon Connect console resolves DataIntegration details by passing
    the KB *name* as the GetDataIntegration identifier. If the KB and
    DataIntegration have different names the console shows an error. This
    function detects and removes the mismatched set so they can be recreated
    with matching names.

    Only deletes if the current KB's backing DataIntegration has a different
    name than expected_name.
    """
    # 1. Check for existing KB association
    assoc_id, existing_kb_id = find_existing_kb_association(
        qconnect_client, assistant_id,
    )
    if not existing_kb_id:
        return  # Nothing to clean up

    # 2. Get the KB details to find its DataIntegration ARN
    try:
        kb_resp = qconnect_client.get_knowledge_base(knowledgeBaseId=existing_kb_id)
        kb = kb_resp.get('knowledgeBase', {})
        kb_name = kb.get('name', '')
        source_cfg = kb.get('sourceConfiguration', {})
        app_int_cfg = source_cfg.get('appIntegrations', {})
        di_arn = app_int_cfg.get('appIntegrationArn', '')
    except ClientError:
        logger.debug('Could not inspect existing KB %s', existing_kb_id, exc_info=True)
        return

    if not di_arn:
        return

    # 3. Get the DataIntegration name from its ARN
    try:
        di_resp = appintegrations_client.get_data_integration(Identifier=di_arn)
        di_name = di_resp.get('Name', '')
    except ClientError:
        logger.debug('Could not get DataIntegration %s', di_arn, exc_info=True)
        di_name = ''

    # 4. If names already match — nothing to fix
    if di_name == expected_name and kb_name == expected_name:
        return

    logger.info(
        'Detected KB name mismatch (KB=%r, DataIntegration=%r, expected=%r). '
        'Cleaning up mismatched resources...',
        kb_name, di_name, expected_name,
    )

    # 5. Delete association → KB → DataIntegration (reverse order of creation)
    if assoc_id:
        try:
            qconnect_client.delete_assistant_association(
                assistantId=assistant_id,
                assistantAssociationId=assoc_id,
            )
            logger.info('Deleted KB association: %s', assoc_id)
        except Exception as e:
            logger.warning('Could not delete KB association %s: %s', assoc_id, e)

    try:
        qconnect_client.delete_knowledge_base(knowledgeBaseId=existing_kb_id)
        logger.info('Deleted knowledge base: %s (%s)', kb_name, existing_kb_id)
    except Exception as e:
        logger.warning('Could not delete KB %s: %s', existing_kb_id, e)

    if di_name and di_name != expected_name:
        try:
            appintegrations_client.delete_data_integration(
                DataIntegrationIdentifier=di_arn,
            )
            logger.info('Deleted old DataIntegration: %s', di_name)
        except Exception as e:
            logger.warning('Could not delete DataIntegration %s: %s', di_name, e)

    logger.info('Cleanup complete — will recreate with matching names.')


def integrate_kb_with_qconnect(cfn_session, qc_session, assistant_id,
                                bucket_name, bucket_arn):
    """Link the S3 KB bucket to the Q Connect assistant as a knowledge base.

    Orchestrates five operations:
      1. Ensure KB bucket exists in the assistant's region
      2. Update S3 bucket policy (service principal access)
      3. Create AppIntegrations DataIntegration
      4. Create Q Connect Knowledge Base (EXTERNAL type)
      5. Associate KB with assistant

    Before creating resources, checks for mismatched KB/DataIntegration names
    and cleans them up. The Amazon Connect console requires the DataIntegration
    name to match the KB name exactly.

    If the source bucket is in a different region than the assistant,
    a new bucket is created in the assistant's region automatically.

    Returns the regional KB bucket name on success, or None on failure.
    """
    qc_region = qc_session.region_name
    account_id = qc_session.client('sts').get_caller_identity()['Account']

    # Pre-check: clean up mismatched KB/DataIntegration names
    try:
        qconnect_client = qc_session.client('qconnect')
        appintegrations_client = qc_session.client('appintegrations')
        _cleanup_mismatched_kb_resources(
            qconnect_client, appintegrations_client,
            assistant_id, KB_INTEGRATION_NAME,
        )
    except Exception as e:
        logger.debug('Mismatch check failed (non-fatal): %s', e)

    # Sub-step 1: Ensure bucket is in the assistant's region
    logger.info('KB integration 1/5: Ensuring KB bucket in %s...', qc_region)
    try:
        s3_client = qc_session.client('s3')
        kb_bucket, kb_bucket_arn = ensure_kb_bucket_in_region(
            s3_client, bucket_name, qc_region, account_id,
        )
    except Exception as e:
        logger.warning('Could not ensure KB bucket in %s: %s', qc_region, e)
        return None

    # Sub-step 2: Update S3 bucket policy
    logger.info('KB integration 2/5: Updating S3 bucket policy...')
    try:
        update_kb_bucket_policy(s3_client, kb_bucket, kb_bucket_arn)
    except Exception as e:
        logger.warning('Could not update bucket policy: %s', e)
        return None

    # Sub-step 3: Create DataIntegration (must be in assistant region)
    logger.info('KB integration 3/5: Creating DataIntegration...')
    kms_client = qc_session.client('kms')
    kms_key_arn = ensure_kb_kms_key(kms_client)

    appintegrations_client = qc_session.client('appintegrations')
    data_integration_arn = create_or_get_data_integration(
        appintegrations_client,
        KB_DATA_INTEGRATION_NAME,
        kb_bucket,
        KB_INTEGRATION_DESCRIPTION,
        kms_key_arn,
    )
    if not data_integration_arn:
        logger.warning('DataIntegration creation failed.')
        return None

    # Sub-step 4: Create Knowledge Base (must be in assistant region)
    logger.info('KB integration 4/5: Creating Q Connect knowledge base...')
    qconnect_client = qc_session.client('qconnect')
    kb_id, kb_arn = create_or_get_knowledge_base(
        qconnect_client,
        KB_INTEGRATION_NAME,
        KB_INTEGRATION_DESCRIPTION,
        data_integration_arn,
    )
    if not kb_id:
        logger.warning('Knowledge base creation failed.')
        return None

    # Sub-step 5: Associate KB with assistant
    logger.info('KB integration 5/5: Associating KB with assistant...')
    success = associate_kb_with_assistant(qconnect_client, assistant_id, kb_id)

    if success:
        logger.info('KB integration complete.')
        logger.info('  KB:     %s', kb_arn)
        logger.info('  Bucket: %s (region: %s)', kb_bucket, qc_region)
        return kb_bucket
    else:
        logger.warning('KB association step did not succeed — see warnings above.')
        return None


# ---------------------------------------------------------------------------
# Delete stack
# ---------------------------------------------------------------------------


def delete_stack(cf_client, stack_name):
    """Delete the CloudFormation stack.

    If the first deletion attempt fails (DELETE_FAILED), retries with
    RetainResources for the failing resources so the stack itself is removed.
    """
    if not stack_exists(cf_client, stack_name):
        logger.info('Stack %s does not exist.', stack_name)
        return

    logger.info('Deleting stack %s...', stack_name)
    cf_client.delete_stack(StackName=stack_name)
    wait_for_stack(cf_client, stack_name, target='DELETE_COMPLETE')

    # Check if deletion failed — retry with RetainResources for stuck resources
    status = get_stack_status(cf_client, stack_name)
    if status == 'DELETE_FAILED':
        logger.warning('Stack deletion failed. Identifying stuck resources...')
        try:
            resp = cf_client.describe_stack_events(StackName=stack_name)
            retain = []
            for event in resp.get('StackEvents', []):
                if event.get('ResourceStatus') == 'DELETE_FAILED':
                    logical_id = event.get('LogicalResourceId', '')
                    if logical_id and logical_id != stack_name and logical_id not in retain:
                        retain.append(logical_id)
                        logger.info('  Retaining stuck resource: %s', logical_id)
            if retain:
                logger.info('Retrying stack deletion (retaining %d stuck resources)...', len(retain))
                cf_client.delete_stack(StackName=stack_name, RetainResources=retain)
                wait_for_stack(cf_client, stack_name, target='DELETE_COMPLETE')
        except Exception as e:
            logger.warning('Retry deletion failed: %s', e)

    logger.info('Stack deleted.')


def destroy_all(session, stack_name, connect_instance_id, region):
    """Destroy ALL resources created by the deployment script.

    Deletes resources in reverse dependency order:
      1. Contact flow
      2. Lex bots (disassociate from Connect, then delete)
      3. AI agent (remove default, delete versions, then delete)
      4. Orchestration prompt (delete versions, then delete)
      5. KB association + knowledge base + data integration
      6. Clear security profile MCP tool permissions
      7. MCP Connect association + application
      8. Delete security profile
      9. Customer Profiles domain integration
     10. MCP gateway target
     11. API key credential
     12. MCP gateway
     13. CloudFormation stack (DynamoDB, Lambda, API GW, S3, etc.)
     14. Lex bot IAM role + inline policy
    """
    total = 14
    step = 0

    cf_client = session.client('cloudformation')

    # Discover Q Connect assistant (needed for agent, prompt, KB cleanup)
    qc_session, assistant_id, assistant_arn = None, None, None
    try:
        qc_session, assistant_id, assistant_arn = discover_qconnect_assistant(
            region, connect_instance_id=connect_instance_id,
        )
    except Exception as e:
        logger.warning('Could not discover Q Connect assistant: %s', e)

    # Discover gateway ID from stack outputs or config file
    gateway_id = None
    try:
        outputs = get_stack_outputs(cf_client, stack_name)
        gateway_id = outputs.get('McpGatewayId')
    except Exception:
        pass
    if not gateway_id:
        gateway_id = discover_gateway_id(config_file=MCP_TOOL_CONFIG_FILE)

    # Determine bot region — bots must be in Connect region
    bot_session = session
    if qc_session and qc_session.region_name != region:
        bot_session = boto3.Session(region_name=region)

    # Cache account ID
    account_id = session.client('sts').get_caller_identity()['Account']

    # ------------------------------------------------------------------ 1
    step += 1
    logger.info('[%d/%d] Deleting contact flow: %s ...', step, total, CONTACT_FLOW_NAME)
    if connect_instance_id:
        try:
            connect_client = session.client('connect')
            paginator = connect_client.get_paginator('list_contact_flows')
            flow_id = None
            for page in paginator.paginate(InstanceId=connect_instance_id):
                for cf in page.get('ContactFlowSummaryList', []):
                    if cf['Name'] == CONTACT_FLOW_NAME:
                        flow_id = cf['Id']
                        break
                if flow_id:
                    break
            if flow_id:
                connect_client.delete_contact_flow(
                    InstanceId=connect_instance_id, ContactFlowId=flow_id,
                )
                logger.info('  Deleted contact flow: %s', flow_id)
            else:
                logger.info('  Contact flow not found — skipping.')
        except Exception as e:
            logger.warning('  Could not delete contact flow: %s', e)
    else:
        logger.info('  No Connect instance — skipping.')

    # ------------------------------------------------------------------ 2
    step += 1
    logger.info('[%d/%d] Deleting Lex bots ...', step, total)
    lex_client = bot_session.client('lexv2-models')
    connect_client = session.client('connect') if connect_instance_id else None
    for bot_name in [INTAKE_BOT_NAME, LEX_BOT_NAME]:
        try:
            bot_id, _ = find_existing_lex_bot(lex_client, bot_name)
            if not bot_id:
                logger.info('  %s not found — skipping.', bot_name)
                continue

            # Disassociate from Connect first
            if connect_instance_id and connect_client:
                try:
                    alias_id = None
                    alias_resp = lex_client.list_bot_aliases(botId=bot_id)
                    for alias in alias_resp.get('botAliasSummaries', []):
                        if alias.get('botAliasName') != 'TestBotAlias':
                            alias_id = alias['botAliasId']
                            break
                    if alias_id:
                        alias_arn = (
                            f'arn:aws:lex:{bot_session.region_name}:{account_id}:'
                            f'bot-alias/{bot_id}/{alias_id}'
                        )
                        connect_client.disassociate_bot(
                            InstanceId=connect_instance_id,
                            LexV2Bot={'AliasArn': alias_arn},
                        )
                        logger.info('  Disassociated %s from Connect.', bot_name)
                except Exception as e:
                    logger.debug('  Could not disassociate %s: %s', bot_name, e)

            lex_client.delete_bot(botId=bot_id, skipResourceInUseCheck=True)
            logger.info('  Deleted %s (ID: %s)', bot_name, bot_id)
        except Exception as e:
            logger.warning('  Could not delete %s: %s', bot_name, e)

    # ------------------------------------------------------------------ 3
    step += 1
    logger.info('[%d/%d] Deleting AI agent: %s ...', step, total, AI_AGENT_NAME)
    deleted_agent_arn = None  # Saved for security profile disassociation later
    if assistant_id and qc_session:
        qc_client = qc_session.client('qconnect')
        try:
            agent_id, _ = find_existing_ai_agent(qc_client, assistant_id, AI_AGENT_NAME)
            if agent_id:
                # Save the agent ARN before deleting — needed to disassociate
                # the security profile (the association lingers after deletion).
                try:
                    agent_resp = qc_client.get_ai_agent(
                        assistantId=assistant_id, aiAgentId=agent_id,
                    )
                    deleted_agent_arn = agent_resp['aiAgent'].get('aiAgentArn', '')
                    # Strip version suffix
                    if deleted_agent_arn and ':' in deleted_agent_arn.rsplit('/', 1)[-1]:
                        deleted_agent_arn = deleted_agent_arn.rsplit(':', 1)[0]
                except Exception:
                    # Construct the ARN manually as fallback
                    deleted_agent_arn = (
                        f'arn:aws:wisdom:{qc_session.region_name}:{account_id}:'
                        f'ai-agent/{assistant_id}/{agent_id}'
                    )

                # Remove as default agent first
                try:
                    qc_client.remove_assistant_ai_agent(
                        assistantId=assistant_id,
                        aiAgentType='ORCHESTRATION',
                    )
                    logger.info('  Removed as default orchestration agent.')
                except Exception:
                    pass

                # Delete all versions
                try:
                    versions = qc_client.list_ai_agent_versions(
                        assistantId=assistant_id, aiAgentId=agent_id,
                    )
                    for v in versions.get('aiAgentVersionSummaries', []):
                        vn = v.get('versionNumber')
                        if vn:
                            try:
                                qc_client.delete_ai_agent_version(
                                    assistantId=assistant_id,
                                    aiAgentId=agent_id,
                                    versionNumber=vn,
                                )
                            except Exception:
                                pass
                    logger.info('  Deleted agent versions.')
                except Exception:
                    pass

                qc_client.delete_ai_agent(
                    assistantId=assistant_id, aiAgentId=agent_id,
                )
                logger.info('  Deleted AI agent: %s', agent_id)
            else:
                logger.info('  AI agent not found — skipping.')
        except Exception as e:
            logger.warning('  Could not delete AI agent: %s', e)
    else:
        logger.info('  No Q Connect assistant — skipping.')

    # ------------------------------------------------------------------ 4
    step += 1
    logger.info('[%d/%d] Deleting orchestration prompt: %s ...', step, total, ORCHESTRATION_PROMPT_NAME)
    if assistant_id and qc_session:
        qc_client = qc_session.client('qconnect')
        try:
            prompt_id, _ = find_existing_prompt(qc_client, assistant_id, ORCHESTRATION_PROMPT_NAME)
            if prompt_id:
                # Delete all versions first
                try:
                    versions = qc_client.list_ai_prompt_versions(
                        assistantId=assistant_id, aiPromptId=prompt_id,
                    )
                    for v in versions.get('aiPromptVersionSummaries', []):
                        vn = v.get('versionNumber')
                        if vn:
                            try:
                                qc_client.delete_ai_prompt_version(
                                    assistantId=assistant_id,
                                    aiPromptId=prompt_id,
                                    versionNumber=vn,
                                )
                            except Exception:
                                pass
                    logger.info('  Deleted prompt versions.')
                except Exception:
                    pass

                qc_client.delete_ai_prompt(
                    assistantId=assistant_id, aiPromptId=prompt_id,
                )
                logger.info('  Deleted prompt: %s', prompt_id)
            else:
                logger.info('  Prompt not found — skipping.')
        except Exception as e:
            logger.warning('  Could not delete prompt: %s', e)
    else:
        logger.info('  No Q Connect assistant — skipping.')

    # ------------------------------------------------------------------ 5
    step += 1
    logger.info('[%d/%d] Deleting KB association + knowledge base + data integration ...', step, total)
    if assistant_id and qc_session:
        qc_client = qc_session.client('qconnect')
        appint_client = qc_session.client('appintegrations')
        try:
            assoc_id, kb_id = find_existing_kb_association(qc_client, assistant_id)
            if assoc_id:
                qc_client.delete_assistant_association(
                    assistantId=assistant_id, assistantAssociationId=assoc_id,
                )
                logger.info('  Deleted KB association: %s', assoc_id)

            if kb_id:
                # Get data integration ARN before deleting KB
                di_arn = None
                try:
                    kb_resp = qc_client.get_knowledge_base(knowledgeBaseId=kb_id)
                    kb_data = kb_resp.get('knowledgeBase', {})
                    di_arn = (kb_data.get('sourceConfiguration', {})
                              .get('appIntegrations', {})
                              .get('appIntegrationArn', ''))
                except Exception:
                    pass

                qc_client.delete_knowledge_base(knowledgeBaseId=kb_id)
                logger.info('  Deleted knowledge base: %s', kb_id)

                if di_arn:
                    try:
                        appint_client.delete_data_integration(
                            DataIntegrationIdentifier=di_arn,
                        )
                        logger.info('  Deleted data integration: %s', di_arn)
                    except Exception as e:
                        logger.warning('  Could not delete data integration: %s', e)
            else:
                kb_id_standalone, _ = find_existing_knowledge_base(qc_client, KB_INTEGRATION_NAME)
                if kb_id_standalone:
                    qc_client.delete_knowledge_base(knowledgeBaseId=kb_id_standalone)
                    logger.info('  Deleted standalone KB: %s', kb_id_standalone)

                di_info = find_existing_data_integration(appint_client, KB_DATA_INTEGRATION_NAME)
                if di_info:
                    try:
                        appint_client.delete_data_integration(
                            DataIntegrationIdentifier=di_info,
                        )
                        logger.info('  Deleted standalone data integration.')
                    except Exception as e:
                        logger.warning('  Could not delete data integration: %s', e)

                if not kb_id_standalone and not di_info:
                    logger.info('  KB resources not found — skipping.')
        except Exception as e:
            logger.warning('  Could not delete KB resources: %s', e)
    else:
        logger.info('  No Q Connect assistant — skipping.')

    # ------------------------------------------------------------------ 6
    # Clear MCP tool permissions and disassociate AI agent from security
    # profile BEFORE deleting the MCP application.
    step += 1
    logger.info('[%d/%d] Clearing security profile MCP tool permissions ...', step, total)
    sp_id = None
    if connect_instance_id:
        try:
            connect_client = session.client('connect')
            paginator = connect_client.get_paginator('list_security_profiles')
            for page in paginator.paginate(InstanceId=connect_instance_id):
                for sp in page.get('SecurityProfileSummaryList', []):
                    if sp.get('Name') == SECURITY_PROFILE_NAME:
                        sp_id = sp['Id']
                        break
                if sp_id:
                    break
            if sp_id:
                # Clear all Application permissions so the profile is no
                # longer tied to the MCP application.
                connect_client.update_security_profile(
                    SecurityProfileId=sp_id,
                    InstanceId=connect_instance_id,
                    Applications=[],
                )
                logger.info('  Cleared MCP tool permissions from security profile: %s', sp_id)

                # Clear permissions (BasicAgentAccess, Wisdom.View, etc.)
                try:
                    connect_client.update_security_profile(
                        SecurityProfileId=sp_id,
                        InstanceId=connect_instance_id,
                        Permissions=[],
                    )
                except Exception:
                    pass

                # Disassociate from the AI agent entity.  The association
                # lingers even after the agent is deleted, blocking profile
                # deletion.  Use the ARN saved from step 3.
                if deleted_agent_arn:
                    try:
                        connect_client.disassociate_security_profiles(
                            InstanceId=connect_instance_id,
                            SecurityProfiles=[{'Id': sp_id}],
                            EntityType='AI_AGENT',
                            EntityArn=deleted_agent_arn,
                        )
                        logger.info('  Disassociated security profile from AI agent.')
                    except Exception as e:
                        logger.debug('  Could not disassociate from agent: %s', e)
            else:
                logger.info('  Security profile not found — skipping.')
        except Exception as e:
            logger.warning('  Could not clear security profile tools: %s', e)
    else:
        logger.info('  No Connect instance — skipping.')

    # ------------------------------------------------------------------ 7
    step += 1
    logger.info('[%d/%d] Deleting MCP Connect association + application ...', step, total)
    if connect_instance_id:
        try:
            appint_client = session.client('appintegrations')
            connect_client = session.client('connect')
            app_name = f'{stack_name} MCP Server'
            app_arn, app_id = find_existing_mcp_app(
                appint_client, gateway_id or '', app_name,
            )
            if app_arn:
                assoc_id = find_existing_connect_association(
                    connect_client, connect_instance_id, app_arn,
                )
                if assoc_id:
                    connect_client.delete_integration_association(
                        InstanceId=connect_instance_id,
                        IntegrationAssociationId=assoc_id,
                    )
                    logger.info('  Deleted Connect integration association: %s', assoc_id)
                appint_client.delete_application(Arn=app_arn)
                logger.info('  Deleted MCP application: %s', app_arn)
            else:
                logger.info('  MCP application not found — skipping.')
        except Exception as e:
            logger.warning('  Could not delete MCP registration: %s', e)
    else:
        logger.info('  No Connect instance — skipping.')

    # ------------------------------------------------------------------ 8
    step += 1
    logger.info('[%d/%d] Deleting security profile: %s ...', step, total, SECURITY_PROFILE_NAME)
    if sp_id and connect_instance_id:
        try:
            connect_client = session.client('connect')
            connect_client.delete_security_profile(
                InstanceId=connect_instance_id,
                SecurityProfileId=sp_id,
            )
            logger.info('  Deleted security profile: %s', sp_id)
        except Exception as e:
            logger.warning('  Could not delete security profile: %s', e)
    elif not sp_id:
        logger.info('  Security profile not found — skipping.')
    else:
        logger.info('  No Connect instance — skipping.')

    # ------------------------------------------------------------------ 9
    step += 1
    logger.info('[%d/%d] Removing Customer Profiles integration ...', step, total)
    if connect_instance_id:
        domain_name = f'{stack_name}-profiles'
        try:
            profiles_client = session.client('customer-profiles')
            connect_arn = (
                f'arn:aws:connect:{region}:{account_id}:instance/{connect_instance_id}'
            )
            profiles_client.delete_integration(
                DomainName=domain_name, Uri=connect_arn,
            )
            logger.info('  Removed Connect integration from profiles domain.')
            profiles_client.delete_domain(DomainName=domain_name)
            logger.info('  Deleted Customer Profiles domain: %s', domain_name)
        except Exception as e:
            err_str = str(e).lower()
            if 'not found' in err_str:
                logger.info('  Customer Profiles domain not found — skipping.')
            else:
                logger.warning('  Could not clean up Customer Profiles: %s', e)
    else:
        logger.info('  No Connect instance — skipping.')

    # ----------------------------------------------------------------- 10
    step += 1
    logger.info('[%d/%d] Deleting MCP gateway target: %s ...', step, total, MCP_TARGET_NAME)
    if gateway_id:
        try:
            agentcore_client = session.client('bedrock-agentcore-control')
            target_id = find_existing_target(agentcore_client, gateway_id, MCP_TARGET_NAME)
            if target_id:
                agentcore_client.delete_gateway_target(
                    gatewayIdentifier=gateway_id, targetId=target_id,
                )
                logger.info('  Deleted gateway target: %s', target_id)
                # Wait for target deletion to propagate
                logger.info('  Waiting for target deletion to propagate...')
                time.sleep(5)
            else:
                logger.info('  Gateway target not found — skipping.')
        except Exception as e:
            logger.warning('  Could not delete gateway target: %s', e)
    else:
        logger.info('  No gateway ID — skipping.')

    # ----------------------------------------------------------------- 11
    step += 1
    logger.info('[%d/%d] Deleting API key credential: %s ...', step, total, API_KEY_CREDENTIAL_NAME)
    try:
        agentcore_client = session.client('bedrock-agentcore-control')
        agentcore_client.delete_api_key_credential_provider(
            name=API_KEY_CREDENTIAL_NAME,
        )
        logger.info('  Deleted API key credential.')
    except Exception as e:
        err_str = str(e).lower()
        if 'not found' in err_str or 'does not exist' in err_str:
            logger.info('  API key credential not found — skipping.')
        else:
            logger.warning('  Could not delete API key credential: %s', e)

    # ----------------------------------------------------------------- 12
    step += 1
    logger.info('[%d/%d] Deleting MCP gateway ...', step, total)
    if gateway_id:
        try:
            agentcore_client = session.client('bedrock-agentcore-control')
            agentcore_client.delete_gateway(gatewayIdentifier=gateway_id)
            logger.info('  Deleted MCP gateway: %s', gateway_id)
        except Exception as e:
            err_str = str(e).lower()
            if 'not found' in err_str or 'does not exist' in err_str:
                logger.info('  Gateway not found — skipping.')
            else:
                logger.warning('  Could not delete gateway: %s', e)
    else:
        logger.info('  No gateway ID — skipping.')

    # ----------------------------------------------------------------- 13
    step += 1
    logger.info('[%d/%d] Deleting CloudFormation stack: %s ...', step, total, stack_name)
    delete_stack(cf_client, stack_name)

    # ----------------------------------------------------------------- 14
    step += 1
    logger.info('[%d/%d] Deleting Lex bot IAM role: %s ...', step, total, LEX_BOT_ROLE_NAME)
    try:
        iam_client = session.client('iam')
        # Delete inline policy first
        try:
            iam_client.delete_role_policy(
                RoleName=LEX_BOT_ROLE_NAME,
                PolicyName='QConnectAndPollyAccess',
            )
        except Exception:
            pass
        iam_client.delete_role(RoleName=LEX_BOT_ROLE_NAME)
        logger.info('  Deleted IAM role: %s', LEX_BOT_ROLE_NAME)
    except Exception as e:
        err_str = str(e).lower()
        if 'nosuchentity' in err_str or 'not found' in err_str:
            logger.info('  IAM role not found — skipping.')
        else:
            logger.warning('  Could not delete IAM role: %s', e)

    logger.info('=' * 60)
    logger.info('Destroy complete. All resources for stack %s have been removed.', stack_name)
    logger.info('=' * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    global ORCHESTRATION_PROMPT_MODEL  # noqa: PLW0603

    parser = argparse.ArgumentParser(
        description='Deploy Stability360 Thrive@Work CloudFormation stack'
    )
    parser.add_argument(
        '--stack-name', default=DEFAULT_STACK_NAME,
        help=f'CloudFormation stack name (default: {DEFAULT_STACK_NAME})'
    )
    parser.add_argument(
        '--region', default=DEFAULT_REGION,
        help=f'AWS region (default: {DEFAULT_REGION})'
    )
    parser.add_argument(
        '--environment', default=DEFAULT_ENVIRONMENT,
        choices=['dev', 'staging', 'prod'],
        help=f'Environment parameter (default: {DEFAULT_ENVIRONMENT})'
    )
    parser.add_argument(
        '--enable-mcp', action='store_true',
        help='Create AgentCore MCP Gateway (AWS_IAM auth by default)'
    )
    parser.add_argument(
        '--seed-only', action='store_true',
        help='Skip stack deployment — only seed DynamoDB data'
    )
    parser.add_argument(
        '--update-code-only', action='store_true',
        help='Skip stack deployment — only update Lambda code'
    )
    parser.add_argument(
        '--connect-instance-id', default='',
        help='Amazon Connect instance ID (implies --enable-mcp, switches auth to CUSTOM_JWT)'
    )
    parser.add_argument(
        '--connect-only', action='store_true',
        help='Skip stack deployment — only register MCP with Connect'
    )
    parser.add_argument(
        '--update-prompt', action='store_true',
        help='Skip stack deployment — only update the orchestration prompt on the AI agent'
    )
    parser.add_argument(
        '--create-bot', action='store_true',
        help='Skip stack deployment — only create/update Lex V2 bot with QinConnect intent'
    )
    parser.add_argument(
        '--integrate-kb', action='store_true',
        help='Skip stack deployment — only link S3 KB bucket to Q Connect as knowledge base'
    )
    parser.add_argument(
        '--seed-kb', action='store_true', default=True,
        help='Upload sample KB documents to the KB bucket (default: true)'
    )
    parser.add_argument(
        '--no-seed-kb', action='store_false', dest='seed_kb',
        help='Skip uploading sample KB documents'
    )
    parser.add_argument(
        '--model-id', default=ORCHESTRATION_PROMPT_MODEL,
        help=f'Model ID for orchestration prompt (default: {ORCHESTRATION_PROMPT_MODEL})'
    )
    parser.add_argument(
        '--delete', action='store_true',
        help='Delete the CloudFormation stack only (use --destroy-all for full teardown)'
    )
    parser.add_argument(
        '--destroy-all', action='store_true', dest='destroy_all',
        help='Destroy ALL resources: contact flow, bots, AI agent, prompt, KB, '
             'security profile, MCP gateway, IAM role, and CFN stack'
    )
    args = parser.parse_args()

    # Derive all resource names from the stack name so multiple stacks
    # can coexist in the same account/region without name collisions.
    init_resource_names(args.stack_name)

    # Override model ID if specified via CLI
    if args.model_id != ORCHESTRATION_PROMPT_MODEL:
        ORCHESTRATION_PROMPT_MODEL = args.model_id

    session = boto3.Session(region_name=args.region)
    cf_client = session.client('cloudformation')

    # ---- Delete mode (CFN stack only) ----
    if args.delete:
        logger.info('=== Deleting stack: %s ===', args.stack_name)
        delete_stack(cf_client, args.stack_name)
        return

    # ---- Destroy-all mode (full teardown) ----
    if args.destroy_all:
        if not args.connect_instance_id:
            logger.error('--connect-instance-id is required with --destroy-all')
            sys.exit(1)
        logger.info('=' * 60)
        logger.info('DESTROY ALL: %s (region: %s)', args.stack_name, args.region)
        logger.info('Connect instance: %s', args.connect_instance_id)
        logger.info('=' * 60)
        destroy_all(session, args.stack_name, args.connect_instance_id, args.region)
        return

    # ---- Seed-only mode ----
    if args.seed_only:
        logger.info('=== Seed-only mode ===')
        outputs = get_stack_outputs(cf_client, args.stack_name)
        table_name = outputs['EmployeesTableName']
        dynamodb_resource = session.resource('dynamodb')
        seed_dynamodb(dynamodb_resource, table_name, SEED_DATA_FILE)
        logger.info('Done.')
        return

    # ---- Connect-only mode ----
    if args.connect_only:
        if not args.connect_instance_id:
            logger.error('--connect-instance-id is required with --connect-only')
            sys.exit(1)
        logger.info('=== Connect-only mode ===')
        outputs = get_stack_outputs(cf_client, args.stack_name)
        gateway_url = outputs['McpGatewayUrl']
        gateway_id = outputs['McpGatewayId']
        logger.info('Gateway URL: %s', gateway_url)
        logger.info('Gateway ID:  %s', gateway_id)
        connect_client = session.client('connect')
        connect_url = get_connect_instance_url(connect_client, args.connect_instance_id)
        logger.info('Updating AllowedAudience to Gateway ID...')
        update_gateway_audience(session, gateway_id, connect_url)
        register_mcp_with_connect(
            session, args.connect_instance_id, gateway_url, gateway_id, args.stack_name,
        )
        logger.info('Done.')
        return

    # ---- Update-code-only mode ----
    if args.update_code_only:
        logger.info('=== Update-code-only mode ===')
        outputs = get_stack_outputs(cf_client, args.stack_name)
        lambda_client = session.client('lambda')
        function_name = outputs['EmployeeLookupFunctionName']
        update_lambda_code(lambda_client, function_name, LAMBDA_CODE_DIR)
        intake_fn = outputs.get('IntakeBotFunctionName', '')
        if intake_fn:
            update_lambda_code(lambda_client, intake_fn, INTAKE_LAMBDA_CODE_DIR)
        logger.info('Done.')
        return

    # ---- Update-prompt mode ----
    if args.update_prompt:
        logger.info('=== Update-prompt mode ===')
        logger.info('Prompt file: %s', ORCHESTRATION_PROMPT_FILE)

        # Find the Q Connect assistant (scans all available regions)
        prompt_session, assistant_id, _ = discover_qconnect_assistant(
            args.region, connect_instance_id=args.connect_instance_id or None,
        )

        if not assistant_id or not prompt_session:
            logger.error('No Q Connect assistant found. Provide --connect-instance-id or check region.')
            sys.exit(1)

        logger.info('Assistant: %s (region: %s)', assistant_id, prompt_session.region_name)

        # Update the prompt
        prompt_id = create_or_update_orchestration_prompt(
            prompt_session, assistant_id, ORCHESTRATION_PROMPT_NAME,
            ORCHESTRATION_PROMPT_FILE, ORCHESTRATION_PROMPT_MODEL,
        )
        if prompt_id:
            logger.info('Prompt updated: %s', prompt_id)

            # Also update the agent if it exists
            qc = prompt_session.client('qconnect')
            agent_id, _ = find_existing_ai_agent(qc, assistant_id, AI_AGENT_NAME)
            if agent_id:
                logger.info('Updating AI agent %s with new prompt...', AI_AGENT_NAME)
                try:
                    connect_instance_id = args.connect_instance_id
                    agent_arn = None
                    if not connect_instance_id:
                        # Try to get it from the agent's current config
                        agent = qc.get_ai_agent(assistantId=assistant_id, aiAgentId=agent_id)
                        agent_arn = agent['aiAgent'].get('aiAgentArn', '')
                        orch = agent['aiAgent']['configuration'].get('orchestrationAIAgentConfiguration', {})
                        instance_arn = orch.get('connectInstanceArn', '')
                        if instance_arn:
                            connect_instance_id = instance_arn.split('/')[-1]
                    if not agent_arn:
                        # Fetch agent ARN if we didn't already
                        agent = qc.get_ai_agent(assistantId=assistant_id, aiAgentId=agent_id)
                        agent_arn = agent['aiAgent'].get('aiAgentArn', '')
                    # Strip version suffix for association (e.g. :$LATEST)
                    if agent_arn and ':' in agent_arn.rsplit('/', 1)[-1]:
                        agent_arn = agent_arn.rsplit(':', 1)[0]
                    if connect_instance_id:
                        # Get gateway ID and stack outputs
                        stack_out = get_stack_outputs(cf_client, args.stack_name)
                        gw_id = discover_gateway_id(stack_outputs=stack_out)
                        update_ai_agent_config(
                            qc, assistant_id, agent_id,
                            connect_instance_id, prompt_session,
                            prompt_id=prompt_id,
                            gateway_id=gw_id or None,
                        )
                        logger.info('Agent updated with new prompt.')

                        # Ensure security profile has MCP tool permissions
                        # and is associated with the AI agent
                        if gw_id and connect_instance_id:
                            connect_client = prompt_session.client('connect')
                            ensure_security_profile_with_tools(
                                connect_client, connect_instance_id, gw_id,
                                agent_arn=agent_arn,
                            )

                        # Set as default self-service orchestration agent
                        set_default_ai_agent(qc, assistant_id, agent_id)
                    else:
                        logger.warning('Could not determine Connect instance ID — prompt updated but agent not refreshed.')
                except Exception as e:
                    logger.warning('Could not update agent: %s', e)
            else:
                logger.info('No agent named %s found — prompt updated only.', AI_AGENT_NAME)
        else:
            logger.error('Prompt update failed.')
            sys.exit(1)

        logger.info('Done.')
        return

    # ---- Create-bot mode ----
    if args.create_bot:
        if not args.connect_instance_id:
            logger.error('--connect-instance-id is required with --create-bot')
            sys.exit(1)
        logger.info('=== Create-bot mode ===')

        # Find the Q Connect assistant (scans all available regions)
        qc_session, assistant_id, assistant_arn = discover_qconnect_assistant(
            args.region, connect_instance_id=args.connect_instance_id,
        )

        if not assistant_id or not assistant_arn:
            logger.error('No Q Connect assistant found. Cannot create bot.')
            sys.exit(1)

        # Lex bot must be in the same region as Connect instance
        bot_session = qc_session
        if qc_session.region_name != args.region:
            logger.warning(
                'Q Connect is in %s but Connect instance is in %s. '
                'Lex bot will be created in %s (Connect region).',
                qc_session.region_name, args.region, args.region,
            )
            bot_session = boto3.Session(region_name=args.region)

        # Ensure IAM role
        iam_client = bot_session.client('iam')
        account_id = bot_session.client('sts').get_caller_identity()['Account']
        role_arn = ensure_lex_bot_role(iam_client, LEX_BOT_ROLE_NAME, account_id)

        # Create the bot
        result = create_lex_bot(
            session=bot_session,
            bot_name=LEX_BOT_NAME,
            bot_description=LEX_BOT_DESCRIPTION,
            role_arn=role_arn,
            locale_id=LEX_BOT_LOCALE,
            nlu_threshold=LEX_BOT_NLU_THRESHOLD,
            idle_session_ttl=LEX_BOT_IDLE_SESSION_TTL,
            alias_name=LEX_BOT_ALIAS_NAME,
            assistant_arn=assistant_arn,
            connect_instance_id=args.connect_instance_id,
        )

        if result:
            logger.info('Bot ready.')
            logger.info('  Bot ID:       %s', result['botId'])
            logger.info('  Version:      %s', result['botVersion'])
            logger.info('  Alias ARN:    %s', result['botAliasArn'])
            logger.info('')
            logger.info('TIP: Run a full deploy to also create the contact flow automatically,')
            logger.info('  or set the Lex alias ARN in your Connect contact flow manually:')
            logger.info('  %s', result['botAliasArn'])
        else:
            logger.error('Bot creation failed.')
            sys.exit(1)

        logger.info('Done.')
        return

    # ---- Integrate-KB mode ----
    if args.integrate_kb:
        logger.info('=== Integrate-KB mode ===')

        # Get stack outputs (need bucket info)
        outputs = get_stack_outputs(cf_client, args.stack_name)
        kb_bucket_name = outputs.get('KnowledgeBaseBucketName', '')
        kb_bucket_arn = outputs.get('KnowledgeBaseBucketArn', '')
        if not kb_bucket_name or not kb_bucket_arn:
            logger.error('KB bucket not found in stack outputs. Deploy the stack first.')
            sys.exit(1)

        # Discover assistant
        qc_session, assistant_id, assistant_arn = discover_qconnect_assistant(
            args.region, connect_instance_id=args.connect_instance_id or None,
        )
        if not assistant_id:
            logger.error('No Q Connect assistant found. Provide --connect-instance-id or check region.')
            sys.exit(1)

        logger.info('S3 Bucket:  %s', kb_bucket_name)
        logger.info('Bucket ARN: %s', kb_bucket_arn)
        logger.info('Assistant:  %s (region: %s)', assistant_id, qc_session.region_name)

        regional_bucket = integrate_kb_with_qconnect(
            cfn_session=session,
            qc_session=qc_session,
            assistant_id=assistant_id,
            bucket_name=kb_bucket_name,
            bucket_arn=kb_bucket_arn,
        )

        if not regional_bucket:
            logger.error('KB integration had issues — see warnings above.')
            sys.exit(1)

        logger.info('KB integration successful.')

        # Seed KB documents into the regional bucket
        if args.seed_kb:
            regional_s3 = qc_session.client('s3')
            count = seed_kb_documents(regional_s3, regional_bucket)
            logger.info('Seeded %d KB documents into s3://%s', count, regional_bucket)

        logger.info('Done.')
        return

    # ---- Full deployment ----
    # --connect-instance-id implies --enable-mcp
    has_connect = bool(args.connect_instance_id)
    enable_mcp = args.enable_mcp or has_connect
    connect_instance_url = ''

    # Step counts:  base=5, +3 for MCP (OpenAPI, API key, target),
    # +11 for Connect (audience, registration, profiles, security profile, prompt,
    #   KB integration, AI agent, tool config, Lex bot, intake bot, contact flow)
    total_steps = 5
    if enable_mcp:
        total_steps = 8
    if has_connect:
        total_steps = 19

    logger.info('=' * 60)
    logger.info('Stability360 Thrive@Work — Deployment')
    logger.info('Stack:       %s', args.stack_name)
    logger.info('Region:      %s', args.region)
    logger.info('Environment: %s', args.environment)
    logger.info('MCP Gateway: %s', 'enabled' if enable_mcp else 'disabled')
    if has_connect:
        logger.info('Connect:     enabled (CUSTOM_JWT)')
        logger.info('Connect ID:  %s', args.connect_instance_id)
    elif enable_mcp:
        logger.info('Connect:     disabled (AWS_IAM)')
    logger.info('=' * 60)

    # Resolve Connect instance URL if provided
    if has_connect:
        logger.info('Resolving Connect instance URL...')
        connect_client = session.client('connect')
        connect_instance_url = get_connect_instance_url(
            connect_client, args.connect_instance_id,
        )
        logger.info('Connect URL: %s', connect_instance_url)

    # Step 1: Deploy CloudFormation stack
    logger.info('[1/%d] Deploying CloudFormation stack...', total_steps)
    with open(TEMPLATE_FILE, 'r') as f:
        template_body = f.read()

    action = deploy_stack(
        cf_client, args.stack_name, template_body, args.environment,
        enable_mcp=enable_mcp,
        enable_connect=has_connect,
        connect_instance_id=args.connect_instance_id,
        connect_instance_url=connect_instance_url,
    )

    if action in ('CREATE', 'UPDATE'):
        target = f'{action}_COMPLETE'
        final_status = wait_for_stack(cf_client, args.stack_name, target=target)
        if final_status != target:
            logger.error('Stack ended in %s. Aborting.', final_status)
            sys.exit(1)
        logger.info('Stack %sd successfully.', action.lower())

    # Step 2: Get stack outputs
    logger.info('[2/%d] Retrieving stack outputs...', total_steps)
    outputs = get_stack_outputs(cf_client, args.stack_name)
    for key, val in outputs.items():
        logger.info('  %s: %s', key, val)

    # Step 3: Update Lambda code (employee lookup + intake bot)
    logger.info('[3/%d] Updating Lambda function code...', total_steps)
    lambda_client = session.client('lambda')
    function_name = outputs['EmployeeLookupFunctionName']
    update_lambda_code(lambda_client, function_name, LAMBDA_CODE_DIR)
    intake_fn = outputs.get('IntakeBotFunctionName', '')
    if intake_fn:
        update_lambda_code(lambda_client, intake_fn, INTAKE_LAMBDA_CODE_DIR)
    else:
        logger.warning('IntakeBotFunctionName not in stack outputs — skipping intake Lambda update.')

    # Step 4: Seed DynamoDB
    logger.info('[4/%d] Seeding DynamoDB with employee data...', total_steps)
    dynamodb_resource = session.resource('dynamodb')
    table_name = outputs['EmployeesTableName']
    seed_dynamodb(dynamodb_resource, table_name, SEED_DATA_FILE)

    # Step 5: Initialize KB bucket folder structure + seed sample documents
    logger.info('[5/%d] Setting up KB bucket folder structure...', total_steps)
    kb_bucket = outputs.get('KnowledgeBaseBucketName', '')
    if kb_bucket:
        s3_client = session.client('s3')
        init_kb_bucket(s3_client, kb_bucket)
        if args.seed_kb:
            count = seed_kb_documents(s3_client, kb_bucket)
            logger.info('Seeded %d KB documents into s3://%s', count, kb_bucket)
    else:
        logger.warning('KB bucket not found in outputs — skipping.')

    # Steps 6–8: MCP Gateway setup (OpenAPI spec + API key + REST API target)
    if enable_mcp:
        gateway_id = outputs.get('McpGatewayId', '')
        gateway_url = outputs.get('McpGatewayUrl', '')
        if not gateway_id or not gateway_url:
            logger.error('MCP Gateway not found in outputs. Aborting MCP setup.')
            sys.exit(1)

        api_base_url = outputs.get('EmployeeApiUrl', '')
        api_key_id = outputs.get('EmployeeApiKeyId', '')

        if not api_base_url:
            logger.error('EmployeeApiUrl not found in stack outputs. Aborting MCP setup.')
            sys.exit(1)
        if not api_key_id:
            logger.error('EmployeeApiKeyId not found in stack outputs. Aborting MCP setup.')
            sys.exit(1)
        if not kb_bucket:
            logger.error('KB bucket not available — cannot upload OpenAPI spec. Aborting MCP setup.')
            sys.exit(1)

        # Get the actual API key value
        apigw_client = session.client('apigateway')
        api_key_value = get_api_key_value(apigw_client, api_key_id)

        agentcore_client = session.client('bedrock-agentcore-control')

        # Step 6: Upload OpenAPI spec to S3
        logger.info('[6/%d] Uploading OpenAPI spec to S3...', total_steps)
        s3_client = session.client('s3')
        openapi_s3_uri = upload_openapi_spec(s3_client, kb_bucket, api_base_url)

        # Step 7: Register API key in AgentCore Identity
        logger.info('[7/%d] Registering API key in AgentCore Identity...', total_steps)
        api_key_cred_arn = register_api_key_credential(
            agentcore_client, API_KEY_CREDENTIAL_NAME, api_key_value,
        )

        # Step 8: Create/update REST API gateway target
        logger.info('[8/%d] Configuring MCP REST API target (OpenAPI + API key)...', total_steps)
        create_or_update_mcp_target(
            agentcore_client, gateway_id, MCP_TARGET_NAME,
            openapi_s3_uri, api_key_cred_arn,
        )

    # Steps 9–11: Connect integration (audience + registration + Customer Profiles)
    if has_connect:
        gateway_url = outputs.get('McpGatewayUrl', '')
        gateway_id = outputs.get('McpGatewayId', '')

        # Step 9: Update AllowedAudience to Gateway ID
        logger.info('[9/%d] Updating gateway AllowedAudience to Gateway ID...', total_steps)
        update_gateway_audience(session, gateway_id, connect_instance_url)

        # Step 10: Register MCP server with Amazon Connect
        logger.info('[10/%d] Registering MCP server with Amazon Connect...', total_steps)
        register_mcp_with_connect(
            session, args.connect_instance_id, gateway_url, gateway_id, args.stack_name,
        )

        # Step 11: Enable Customer Profiles
        logger.info('[11/%d] Enabling Customer Profiles...', total_steps)
        enable_customer_profiles(session, args.connect_instance_id, args.stack_name)

        # Step 12: Ensure Security Profile with MCP tool permissions
        logger.info('[12/%d] Ensuring AI Agent security profile with MCP tool access...', total_steps)
        connect_client = session.client('connect')
        sp_id = ensure_security_profile_with_tools(
            connect_client, args.connect_instance_id, gateway_id,
        )
        if sp_id:
            logger.info('Security profile ready: %s', sp_id)
        else:
            logger.warning('Could not create/find security profile — add MCP tools manually.')

        # Step 13: Create custom orchestration prompt (Task 7)
        logger.info('[13/%d] Creating custom orchestration prompt...', total_steps)
        qc_session, assistant_id, assistant_arn = discover_qconnect_assistant(
            args.region, connect_instance_id=args.connect_instance_id,
        )
        custom_prompt_id = None
        if assistant_id:
            custom_prompt_id = create_or_update_orchestration_prompt(
                qc_session, assistant_id, ORCHESTRATION_PROMPT_NAME,
                ORCHESTRATION_PROMPT_FILE, ORCHESTRATION_PROMPT_MODEL,
            )
            if custom_prompt_id:
                logger.info('Custom prompt ready: %s', custom_prompt_id)
            else:
                logger.warning('Custom prompt creation failed — agent will use system prompt.')
        else:
            logger.warning('Q Connect assistant not found for this Connect instance.')

        # Step 14: Link S3 KB bucket to Q Connect as knowledge base
        logger.info('[14/%d] Linking S3 KB bucket to Q Connect...', total_steps)
        if assistant_id and qc_session:
            kb_bucket_name = outputs.get('KnowledgeBaseBucketName', '')
            kb_bucket_arn = outputs.get('KnowledgeBaseBucketArn', '')
            if kb_bucket_name and kb_bucket_arn:
                regional_bucket = integrate_kb_with_qconnect(
                    cfn_session=session,
                    qc_session=qc_session,
                    assistant_id=assistant_id,
                    bucket_name=kb_bucket_name,
                    bucket_arn=kb_bucket_arn,
                )
                # Seed KB documents into the regional bucket
                if regional_bucket and args.seed_kb:
                    regional_s3 = qc_session.client('s3')
                    count = seed_kb_documents(regional_s3, regional_bucket)
                    logger.info('Seeded %d KB documents into s3://%s', count, regional_bucket)
            else:
                logger.warning('KB bucket info not in stack outputs — skipping KB integration.')
                logger.info('Run: python deploy.py --integrate-kb --connect-instance-id %s',
                             args.connect_instance_id)
        else:
            logger.warning('No Q Connect assistant — skipping KB integration.')

        # Step 15: Create AI Agent (ORCHESTRATION type, per workshop Task 6)
        logger.info('[15/%d] Creating AI Agent (ORCHESTRATION)...', total_steps)
        ai_agent_id = None
        if assistant_id:
            ai_agent_id = create_ai_agent(
                qc_session, assistant_id, AI_AGENT_NAME, AI_AGENT_DESCRIPTION,
                args.connect_instance_id, custom_prompt_id=custom_prompt_id,
                gateway_id=gateway_id,
            )
        else:
            logger.info('Ensure Amazon Q in Connect is enabled on the instance.')
            logger.info('You can create the AI Agent manually via the Connect console:')
            logger.info('  AI agent designer → AI agents → Create AI agent')

        if ai_agent_id:
            logger.info('AI Agent ready: %s (ID: %s)', AI_AGENT_NAME, ai_agent_id)
            logger.info('Select this agent in your Connect contact flow to use it.')

            # Associate security profile with the AI agent
            if sp_id and qc_session:
                try:
                    qc_client = qc_session.client('qconnect')
                    agent_resp = qc_client.get_ai_agent(
                        assistantId=assistant_id, aiAgentId=ai_agent_id,
                    )
                    agent_arn = agent_resp['aiAgent'].get('aiAgentArn', '')
                    # Strip version suffix (e.g. :$LATEST)
                    if agent_arn and ':' in agent_arn.rsplit('/', 1)[-1]:
                        agent_arn = agent_arn.rsplit(':', 1)[0]
                    if agent_arn:
                        associate_security_profile_with_agent(
                            connect_client, args.connect_instance_id,
                            sp_id, agent_arn,
                        )
                except Exception as e:
                    logger.warning('Could not associate security profile with agent: %s', e)

        # Step 16: Generate MCP tool configuration reference file
        logger.info('[16/%d] Generating MCP tool configuration reference...', total_steps)
        generate_tool_config_file(
            gateway_id=gateway_id,
            target_name=MCP_TARGET_NAME,
            operation_id=MCP_TOOL_OPERATION,
            agent_name=AI_AGENT_NAME,
            agent_id=ai_agent_id or 'UNKNOWN',
            assistant_id=assistant_id or 'UNKNOWN',
            output_path=MCP_TOOL_CONFIG_FILE,
        )

        # Ensure Lex IAM role exists (shared by Stability360Bot and IntakeBot)
        lex_role_arn = None
        if qc_session:
            iam_client = qc_session.client('iam')
            account_id = qc_session.client('sts').get_caller_identity()['Account']
            lex_role_arn = ensure_lex_bot_role(
                iam_client, LEX_BOT_ROLE_NAME, account_id,
            )

        # Step 17: Create Lex V2 Bot with AMAZON.QinConnectIntent (Task 8)
        logger.info('[17/%d] Creating Lex V2 bot with QinConnect intent...', total_steps)

        # Lex bots must be in the same region as the Connect instance.
        # Q Connect assistant may be in a different region — use a session
        # in the Connect region for bot creation.
        bot_session = qc_session
        if qc_session and qc_session.region_name != args.region:
            logger.warning(
                'Q Connect is in %s but Connect instance is in %s. '
                'Lex bot will be created in %s (Connect region).',
                qc_session.region_name, args.region, args.region,
            )
            bot_session = boto3.Session(region_name=args.region)

        lex_result = None
        if assistant_id and assistant_arn and bot_session and lex_role_arn:
            lex_result = create_lex_bot(
                session=bot_session,
                bot_name=LEX_BOT_NAME,
                bot_description=LEX_BOT_DESCRIPTION,
                role_arn=lex_role_arn,
                locale_id=LEX_BOT_LOCALE,
                nlu_threshold=LEX_BOT_NLU_THRESHOLD,
                idle_session_ttl=LEX_BOT_IDLE_SESSION_TTL,
                alias_name=LEX_BOT_ALIAS_NAME,
                assistant_arn=assistant_arn,
                connect_instance_id=args.connect_instance_id,
            )
            if lex_result:
                logger.info('Lex bot ready: %s', lex_result['botAliasArn'])
            else:
                logger.warning('Lex bot creation failed — create it manually via Connect console.')
        else:
            logger.warning('No Q Connect assistant — skipping Lex bot creation.')
            logger.info('Run: python deploy.py --create-bot --connect-instance-id %s',
                         args.connect_instance_id)

        # Step 18: Create Intake Bot (ListPicker menu → service routing)
        logger.info('[18/%d] Creating Intake Bot (service routing)...', total_steps)
        intake_result = None
        intake_lambda_arn = outputs.get('IntakeBotFunctionArn', '')
        if intake_lambda_arn and bot_session and lex_role_arn:
            intake_result = create_intake_lex_bot(
                session=bot_session,
                bot_name=INTAKE_BOT_NAME,
                bot_description=INTAKE_BOT_DESCRIPTION,
                role_arn=lex_role_arn,
                intake_lambda_arn=intake_lambda_arn,
                connect_instance_id=args.connect_instance_id,
                locale_id=LEX_BOT_LOCALE,
                nlu_threshold=LEX_BOT_NLU_THRESHOLD,
                idle_session_ttl=LEX_BOT_IDLE_SESSION_TTL,
                alias_name=INTAKE_BOT_ALIAS_NAME,
            )
            if intake_result:
                logger.info('Intake bot ready: %s', intake_result['botAliasArn'])
            else:
                logger.warning('Intake bot creation failed.')
        else:
            logger.warning('Intake Lambda not found in outputs — skipping intake bot.')

        # Step 19: Create self-service contact flow (with intake routing)
        logger.info('[19/%d] Creating self-service contact flow...', total_steps)
        contact_flow_id = None
        if lex_result and assistant_arn and ai_agent_id:
            # Build the AI agent version ARN for the Lex session attribute
            ai_agent_version_arn = (
                f'arn:aws:wisdom:{qc_session.region_name}:'
                f'{qc_session.client("sts").get_caller_identity()["Account"]}:'
                f'ai-agent/{assistant_id}/{ai_agent_id}:$LATEST'
            )
            intake_alias_arn = intake_result['botAliasArn'] if intake_result else None
            contact_flow_id = create_or_update_contact_flow(
                session=qc_session,
                connect_instance_id=args.connect_instance_id,
                assistant_arn=assistant_arn,
                bot_alias_arn=lex_result['botAliasArn'],
                ai_agent_version_arn=ai_agent_version_arn,
                intake_bot_alias_arn=intake_alias_arn,
            )
            if contact_flow_id:
                logger.info('Contact flow ready: %s (ID: %s)', CONTACT_FLOW_NAME, contact_flow_id)
            else:
                logger.warning('Contact flow creation failed — create it manually.')
        else:
            logger.warning('Missing Lex bot or AI agent — skipping contact flow creation.')
            logger.info('Create the contact flow manually in the Connect console.')

    # Summary
    logger.info('=' * 60)
    logger.info('Deployment complete!')
    logger.info('=' * 60)

    api_url = outputs.get('EmployeeLookupEndpoint', 'N/A')
    api_key_id = outputs.get('EmployeeApiKeyId', '')

    logger.info('Endpoint:   %s', api_url)

    if api_key_id:
        apigw_client = session.client('apigateway')
        try:
            key_value = get_api_key_value(apigw_client, api_key_id)
            logger.info('API Key:    %s', key_value)
        except ClientError:
            logger.info('API Key ID: %s (retrieve value from AWS Console)', api_key_id)

    logger.info('Table:      %s', table_name)
    logger.info('Function:   %s', function_name)
    logger.info('KB Bucket:  %s', kb_bucket)

    if enable_mcp:
        mcp_gateway_url = outputs.get('McpGatewayUrl', 'N/A')
        mcp_gateway_id = outputs.get('McpGatewayId', 'N/A')
        logger.info('MCP Gateway: %s', mcp_gateway_url)
        logger.info('MCP GW ID:   %s', mcp_gateway_id)
        logger.info('OpenAPI Spec: s3://%s/%s', kb_bucket, OPENAPI_S3_KEY)
        logger.info('MCP Target:  %s (REST API + OpenAPI)', MCP_TARGET_NAME)
        if has_connect:
            logger.info('Connect ID:  %s', args.connect_instance_id)
            logger.info('Connect URL: %s', connect_instance_url)
            logger.info('MCP Auth:    CUSTOM_JWT')
            logger.info('Security Profile: %s', SECURITY_PROFILE_NAME)
            logger.info('AI Agent:    %s', AI_AGENT_NAME)
            logger.info('Prompt:      %s', ORCHESTRATION_PROMPT_NAME)
            logger.info('KB:          %s', KB_INTEGRATION_NAME)
            logger.info('MCP Tool:    %s (auto-configured)', MCP_TOOL_NAME_SAFE)
            logger.info('Tool Config: %s', MCP_TOOL_CONFIG_FILE)
            if lex_result:
                logger.info('Lex Bot:     %s (ID: %s)', LEX_BOT_NAME, lex_result['botId'])
                logger.info('Lex Alias:   %s', lex_result['botAliasArn'])
            if intake_result:
                logger.info('Intake Bot:  %s (ID: %s)', INTAKE_BOT_NAME, intake_result['botId'])
                logger.info('Intake Alias: %s', intake_result['botAliasArn'])
            if contact_flow_id:
                logger.info('Contact Flow: %s (ID: %s)', CONTACT_FLOW_NAME, contact_flow_id)
        else:
            logger.info('MCP Auth:    AWS_IAM')
    else:
        logger.info('MCP Gateway: disabled')

    logger.info('Test API Gateway with:')
    logger.info('  curl -X POST %s \\', api_url)
    logger.info('    -H "Content-Type: application/json" \\')
    logger.info('    -H "x-api-key: <API_KEY>" \\')
    logger.info('    -d \'{"employee_id": "TW-10001"}\'')


if __name__ == '__main__':
    main()
