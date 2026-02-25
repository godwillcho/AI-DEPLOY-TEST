#!/usr/bin/env python3
"""
Stability360 — Actions Stack Deployment Script

Deploys the CloudFormation stack (DynamoDB, Lambda, API Gateway, MCP Gateway)
and configures 2 MCP action tools (scoringCalculate + resourceLookup) with a
NEW AI agent (not default).

Deployment steps:
  No MCP:  1-3  (CFN, outputs, Lambda)
  MCP:     1-7  (+ OpenAPI upload, API key credential, REST API target)
  Connect: 1-13 (+ audience, registration, security profile, prompt,
                  AI agent with 2 MCP tools, tool config reference)

Usage:
    python deploy.py --stack-name stability360-actions --region us-east-1 \\
      --environment prod --enable-mcp \\
      --connect-instance-id <ID>

    python deploy.py --update-code-only --stack-name <STACK>
    python deploy.py --update-prompt --connect-instance-id <ID>
    python deploy.py --delete --stack-name <STACK>
    python deploy.py --teardown --stack-name <STACK> --connect-instance-id <ID>
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

logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_FILE = os.path.join(SCRIPT_DIR, 'stability360-actions-stack.yaml')
LAMBDA_CODE_DIR = os.path.join(SCRIPT_DIR, 'lambda', 'actions')
OPENAPI_SPEC_TEMPLATE = os.path.join(SCRIPT_DIR, 'openapi', 'actions-spec.yaml')
ORCHESTRATION_PROMPT_FILE = os.path.join(SCRIPT_DIR, 'prompts', 'orchestration-prompt.txt')

DEFAULT_STACK_NAME = 'stability360-actions'
DEFAULT_REGION = 'us-west-2'
DEFAULT_ENVIRONMENT = 'dev'

POLL_INTERVAL = 10

OPENAPI_S3_KEY = 'openapi/actions-spec.yaml'

# 2 MCP tool operation IDs (from OpenAPI spec)
MCP_TOOL_OPERATIONS = ['scoringCalculate', 'resourceLookup']

ORCHESTRATION_PROMPT_MODEL = 'us.anthropic.claude-sonnet-4-5-20250929-v1:0'

MCP_TOOL_CONFIG_FILE = os.path.join(SCRIPT_DIR, 'ai-agent-tool-config.json')

# Retrieve tool instruction for this agent
RETRIEVE_TOOL_INSTRUCTION = (
    'Use this tool to search the Stability360 knowledge base whenever a '
    'customer asks about programs, services, eligibility criteria, community '
    'resources, 211 providers, Thrive@Work employer-based programs, or '
    'anything related to Stability360 and Trident United Way. Include the '
    'client\'s county when searching for community resources. Always try '
    'Retrieve before telling a customer you don\'t have information.'
)

RETRIEVE_TOOL_EXAMPLES = [
    (
        'Customer: What is Stability360?\n'
        'Agent: Let me find that information for you.\n'
        'Tool call: Retrieve with query="What is Stability360"\n'
        'Result: Stability360 is a comprehensive support program...\n'
        'Agent: Stability360 is a program operated by Trident United Way '
        'that helps people in the tri-county area access the resources '
        'they need. Would you like to know more about what we offer?'
    ),
    (
        'Customer: I need help with food in Charleston County.\n'
        'Agent: Let me look up food resources in your area.\n'
        'Tool call: Retrieve with query="food assistance Charleston County"\n'
        'Result: Lowcountry Food Bank serves Charleston County...\n'
        'Agent: There are several food assistance options in Charleston '
        'County. The Lowcountry Food Bank has multiple distribution sites, '
        'and East Cooper Outreach Ministries can help if you\'re in the '
        'Mount Pleasant area. Would you like more details on any of these?'
    ),
]

# MCP tool instructions for each action tool
SCORING_TOOL_INSTRUCTION = (
    'Use this tool after collecting housing, income, and employment data '
    'from the client to determine their recommended service path. The tool '
    'performs exact mathematical scoring — do not attempt to calculate '
    'scores yourself. Scoring results are INTERNAL ONLY — never share '
    'scores or composite values with the client. '
    'Required inputs: housing_situation, monthly_income, monthly_housing_cost, '
    'employment_status. Returns scores 1-5 for housing, employment, and '
    'financial resilience, plus a composite score and recommended path '
    '(direct_support, mixed, or referral).'
)

RESOURCE_LOOKUP_TOOL_INSTRUCTION = (
    'Use this tool to search the SC 211 community resource directory for '
    'services matching a keyword and location. Use this when a client needs '
    'community resource referrals (food, utilities, housing, healthcare, etc.). '
    'Include the county and/or zip_code for more relevant results. '
    'Required input: keyword. Optional: county, city, zip_code, max_results. '
    'Results include provider name, description, address, phone, URL, '
    'eligibility, and fees.'
)


# ---------------------------------------------------------------------------
# Resource names — derived from stack name
# ---------------------------------------------------------------------------

API_KEY_CREDENTIAL_NAME = None
MCP_TARGET_NAME = None
AI_AGENT_NAME = None
AI_AGENT_DESCRIPTION = None
MCP_TOOL_NAMES = None          # list of tool names
MCP_TOOL_NAMES_SAFE = None     # list of tool names (hyphens replaced)
ORCHESTRATION_PROMPT_NAME = None
SECURITY_PROFILE_NAME = None


def init_resource_names(stack_name):
    """Derive all resource names from the stack name."""
    global API_KEY_CREDENTIAL_NAME, MCP_TARGET_NAME
    global AI_AGENT_NAME, AI_AGENT_DESCRIPTION
    global MCP_TOOL_NAMES, MCP_TOOL_NAMES_SAFE
    global ORCHESTRATION_PROMPT_NAME, SECURITY_PROFILE_NAME

    API_KEY_CREDENTIAL_NAME = f'{stack_name}-api-key'
    MCP_TARGET_NAME = f'{stack_name}-api'

    AI_AGENT_NAME = f'{stack_name}-orchestration'
    AI_AGENT_DESCRIPTION = (
        f'AI agent for {stack_name} — Scoring, Resource Lookup, Contact Data '
        f'({len(MCP_TOOL_OPERATIONS)} MCP tools)'
    )

    # Tool name format: {target-name}___{operationId}
    MCP_TOOL_NAMES = [f'{MCP_TARGET_NAME}___{op}' for op in MCP_TOOL_OPERATIONS]
    MCP_TOOL_NAMES_SAFE = [n.replace('-', '_') for n in MCP_TOOL_NAMES]

    ORCHESTRATION_PROMPT_NAME = f'{stack_name}-orchestration'
    SECURITY_PROFILE_NAME = f'{stack_name}-AI-Agent'


# ---------------------------------------------------------------------------
# CloudFormation helpers
# ---------------------------------------------------------------------------


def stack_exists(cf_client, stack_name):
    try:
        resp = cf_client.describe_stacks(StackName=stack_name)
        status = resp['Stacks'][0]['StackStatus']
        return status != 'DELETE_COMPLETE'
    except cf_client.exceptions.ClientError:
        return False


def get_stack_status(cf_client, stack_name):
    resp = cf_client.describe_stacks(StackName=stack_name)
    return resp['Stacks'][0]['StackStatus']


def deploy_stack(cf_client, stack_name, template_body, environment,
                 enable_mcp=False, enable_connect=False,
                 connect_instance_id='', connect_instance_url='',
                 openapi_spec_url=''):
    params = [
        {'ParameterKey': 'Environment', 'ParameterValue': environment},
        {'ParameterKey': 'EnableMcpGateway', 'ParameterValue': 'true' if enable_mcp else 'false'},
        {'ParameterKey': 'EnableConnectIntegration', 'ParameterValue': 'true' if enable_connect else 'false'},
        {'ParameterKey': 'ConnectInstanceId', 'ParameterValue': connect_instance_id},
        {'ParameterKey': 'ConnectInstanceUrl', 'ParameterValue': connect_instance_url},
        {'ParameterKey': 'OpenApiSpecUrl', 'ParameterValue': openapi_spec_url},
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
    resp = cf_client.describe_stacks(StackName=stack_name)
    outputs = resp['Stacks'][0].get('Outputs', [])
    return {o['OutputKey']: o['OutputValue'] for o in outputs}


def delete_stack(cf_client, stack_name):
    logger.info('Deleting stack: %s', stack_name)
    cf_client.delete_stack(StackName=stack_name)
    wait_for_stack(cf_client, stack_name, target='DELETE_COMPLETE')
    logger.info('Stack deleted.')


def teardown_all(session, stack_name, connect_instance_id, region,
                  delete_security_profile=False):
    """Full teardown: delete all resources created by deploy.py.

    Order matters — resources have dependencies:
      1. Delete AI Agent + AI Prompt (Q Connect)
      2. Clear security profile MCP apps
      3. Delete Connect ↔ MCP integration association
      4. Delete App Integrations application
      5. Delete MCP gateway target
      6. Delete MCP gateway
      7. Delete API key credential
      8. Delete CloudFormation stack

    Security profile deletion is skipped by default (AWS sticky reference).
    Pass delete_security_profile=True to attempt it (use --delete-security-profile).
    The function logs warnings and continues on individual failures.
    """
    cf_client = session.client('cloudformation')

    # --- Read stack outputs (needed for gateway ID, etc.) ---
    outputs = {}
    try:
        outputs = get_stack_outputs(cf_client, stack_name)
    except Exception:
        logger.warning('Could not read stack outputs — some resources may need manual cleanup.')

    gateway_id = outputs.get('McpGatewayId', '')

    # --- 1. Delete AI Agent + Prompt ---
    if connect_instance_id:
        try:
            assistant_id, _ = find_qconnect_assistant(session, connect_instance_id)
            if assistant_id:
                qconnect_client = session.client('qconnect')

                # Delete AI Agent
                agent_id, _ = find_existing_ai_agent(qconnect_client, assistant_id, AI_AGENT_NAME)
                if agent_id:
                    logger.info('Deleting AI Agent: %s (%s)', AI_AGENT_NAME, agent_id)
                    try:
                        qconnect_client.delete_ai_agent(
                            assistantId=assistant_id, aiAgentId=agent_id,
                        )
                        logger.info('AI Agent deleted.')
                    except Exception as e:
                        logger.warning('Could not delete AI Agent: %s', e)
                else:
                    logger.info('AI Agent not found — nothing to delete.')

                # Delete AI Prompt
                prompt_id, _ = find_existing_prompt(qconnect_client, assistant_id, ORCHESTRATION_PROMPT_NAME)
                if prompt_id:
                    logger.info('Deleting AI Prompt: %s (%s)', ORCHESTRATION_PROMPT_NAME, prompt_id)
                    try:
                        qconnect_client.delete_ai_prompt(
                            assistantId=assistant_id, aiPromptId=prompt_id,
                        )
                        logger.info('AI Prompt deleted.')
                    except Exception as e:
                        logger.warning('Could not delete AI Prompt: %s', e)
                else:
                    logger.info('AI Prompt not found — nothing to delete.')
        except Exception as e:
            logger.warning('Could not clean up Q Connect resources: %s', e)

    # --- 2-4. Clean up Connect integration + security profile ---
    if connect_instance_id:
        connect_client = session.client('connect')
        appintegrations_client = session.client('appintegrations')

        # Find the MCP app
        app_name = f'{stack_name} MCP Server'
        app_namespace = gateway_id
        app_arn, app_id = None, None
        try:
            app_arn, app_id = find_existing_mcp_app(
                appintegrations_client, app_namespace, app_name,
            )
        except Exception:
            logger.debug('Could not search for MCP app', exc_info=True)

        # 2. Clear security profile MCP apps
        sp_id = None
        try:
            paginator = connect_client.get_paginator('list_security_profiles')
            for page in paginator.paginate(InstanceId=connect_instance_id):
                for sp in page.get('SecurityProfileSummaryList', []):
                    if sp.get('Name') == SECURITY_PROFILE_NAME:
                        sp_id = sp['Id']
                        break
                if sp_id:
                    break
        except Exception:
            pass

        if sp_id:
            logger.info('Clearing MCP apps from security profile: %s', sp_id)
            try:
                connect_client.update_security_profile(
                    SecurityProfileId=sp_id,
                    InstanceId=connect_instance_id,
                    Applications=[],
                )
                logger.info('Security profile MCP apps cleared.')
            except Exception as e:
                logger.warning('Could not clear security profile apps: %s', e)

            if delete_security_profile:
                try:
                    connect_client.delete_security_profile(
                        SecurityProfileId=sp_id,
                        InstanceId=connect_instance_id,
                    )
                    logger.info('Security profile deleted.')
                except Exception as e:
                    logger.warning('Could not delete security profile: %s', e)
            else:
                logger.info('Security profile kept (reused on next deploy). '
                            'Use --delete-security-profile to attempt deletion.')

        # 3. Delete integration association
        if app_arn:
            assoc_id = find_existing_connect_association(
                connect_client, connect_instance_id, app_arn,
            )
            if assoc_id:
                logger.info('Deleting Connect integration association: %s', assoc_id)
                try:
                    connect_client.delete_integration_association(
                        InstanceId=connect_instance_id,
                        IntegrationAssociationId=assoc_id,
                    )
                    logger.info('Integration association deleted.')
                except Exception as e:
                    logger.warning('Could not delete integration association: %s', e)

        # 4. Delete app integration
        if app_arn:
            logger.info('Deleting MCP app integration: %s', app_arn)
            try:
                appintegrations_client.delete_application(Arn=app_arn)
                logger.info('App integration deleted.')
            except Exception as e:
                logger.warning('Could not delete app integration: %s', e)

    # --- 5-6. Delete MCP gateway target + gateway ---
    if gateway_id:
        agentcore_client = session.client('bedrock-agentcore-control')

        # 5. Delete gateway target
        target_id = find_existing_target(agentcore_client, gateway_id, MCP_TARGET_NAME)
        if target_id:
            logger.info('Deleting MCP gateway target: %s (%s)', MCP_TARGET_NAME, target_id)
            try:
                agentcore_client.delete_gateway_target(
                    gatewayIdentifier=gateway_id, targetId=target_id,
                )
                logger.info('Gateway target deleted (may take a moment).')
                time.sleep(10)
            except Exception as e:
                logger.warning('Could not delete gateway target: %s', e)

        # 6. Delete gateway
        logger.info('Deleting MCP gateway: %s', gateway_id)
        try:
            agentcore_client.delete_gateway(gatewayIdentifier=gateway_id)
            logger.info('MCP gateway deleted (may take a moment).')
            time.sleep(5)
        except Exception as e:
            logger.warning('Could not delete MCP gateway: %s', e)

    # --- 7. Delete API key credential ---
    try:
        agentcore_client = session.client('bedrock-agentcore-control')
        logger.info('Deleting API key credential: %s', API_KEY_CREDENTIAL_NAME)
        agentcore_client.delete_api_key_credential_provider(
            name=API_KEY_CREDENTIAL_NAME,
        )
        logger.info('API key credential deleted.')
    except Exception as e:
        logger.warning('Could not delete API key credential: %s', e)

    # --- 8. Delete CloudFormation stack ---
    if stack_exists(cf_client, stack_name):
        delete_stack(cf_client, stack_name)
    else:
        logger.info('CloudFormation stack already deleted.')

    logger.info('')
    logger.info('=' * 60)
    logger.info('Teardown complete for: %s', stack_name)
    logger.info('=' * 60)


# ---------------------------------------------------------------------------
# Lambda packaging
# ---------------------------------------------------------------------------


def package_lambda(code_dir):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(code_dir):
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
# OpenAPI spec
# ---------------------------------------------------------------------------


def upload_openapi_spec(s3_client, bucket_name, api_base_url):
    with open(OPENAPI_SPEC_TEMPLATE, 'r') as f:
        spec_content = f.read()
    # Support both old and new placeholder conventions
    spec_content = spec_content.replace('${SERVER_URL}', api_base_url)
    spec_content = spec_content.replace('${API_GATEWAY_URL}', api_base_url)
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
# API key
# ---------------------------------------------------------------------------


def get_api_key_value(apigw_client, api_key_id):
    resp = apigw_client.get_api_key(apiKey=api_key_id, includeValue=True)
    return resp['value']


def register_api_key_credential(agentcore_client, credential_name, api_key_value):
    try:
        resp = agentcore_client.list_api_key_credential_providers()
        for cred in resp.get('credentialProviders', []):
            if cred.get('name') == credential_name:
                cred_arn = cred['credentialProviderArn']
                logger.info('API key credential already exists: %s', cred_arn)
                agentcore_client.update_api_key_credential_provider(
                    name=credential_name,
                    apiKey=api_key_value,
                )
                logger.info('API key credential updated.')
                return cred_arn
    except ClientError:
        logger.debug('Could not list API key credentials', exc_info=True)

    logger.info('Registering API key credential: %s', credential_name)
    resp = agentcore_client.create_api_key_credential_provider(
        name=credential_name,
        apiKey=api_key_value,
    )
    cred_arn = resp['credentialProviderArn']
    logger.info('Registered. ARN: %s', cred_arn)
    return cred_arn


# ---------------------------------------------------------------------------
# MCP Gateway target
# ---------------------------------------------------------------------------


def find_existing_target(agentcore_client, gateway_id, target_name):
    try:
        resp = agentcore_client.list_gateway_targets(gatewayIdentifier=gateway_id)
        targets = resp.get('targets', []) or resp.get('items', [])
        for t in targets:
            if t.get('name') == target_name:
                return t.get('targetId')
    except ClientError:
        logger.debug('Could not list gateway targets', exc_info=True)
    return None


def create_or_update_mcp_target(agentcore_client, gateway_id, target_name,
                                openapi_s3_uri, api_key_credential_arn):
    target_config = {
        'mcp': {
            'openApiSchema': {
                's3': {'uri': openapi_s3_uri}
            }
        }
    }
    cred_config = [
        {
            'credentialProviderType': 'API_KEY',
            'credentialProvider': {
                'apiKeyCredentialProvider': {
                    'providerArn': api_key_credential_arn,
                    'credentialParameterName': 'X-API-Key',
                    'credentialLocation': 'HEADER',
                }
            }
        }
    ]
    target_description = (
        'Stability360 Actions API — Scoring + Resource Lookup '
        '(2 MCP tools via single API Gateway)'
    )

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
            logger.info('Target already exists.')
            return None
        raise


# ---------------------------------------------------------------------------
# MCP Gateway audience update
# ---------------------------------------------------------------------------


def update_gateway_audience(session, gateway_id, connect_instance_url):
    agentcore_client = session.client('bedrock-agentcore-control')
    gw = agentcore_client.get_gateway(gatewayIdentifier=gateway_id)
    current_auth_type = gw.get('authorizerType', '')
    if current_auth_type != 'CUSTOM_JWT':
        logger.info('Gateway auth is %s — no audience update needed.', current_auth_type)
        return

    current_config = gw.get('authorizerConfiguration', {})
    jwt_config = current_config.get('customJWTAuthorizer', {})
    current_audiences = jwt_config.get('allowedAudience', [])

    # Build the correct discovery URL from the Connect instance URL
    correct_discovery_url = f'{connect_instance_url}/.well-known/openid-configuration'
    current_discovery_url = jwt_config.get('discoveryUrl', '')

    audience_ok = current_audiences == [gateway_id]
    discovery_ok = current_discovery_url == correct_discovery_url

    if audience_ok and discovery_ok:
        logger.info('AllowedAudience and DiscoveryUrl already correct.')
        return

    if not audience_ok:
        logger.info('Updating AllowedAudience from %s to [%s]...', current_audiences, gateway_id)
    if not discovery_ok:
        logger.info('Updating DiscoveryUrl from %s to %s...', current_discovery_url, correct_discovery_url)

    update_kwargs = {
        'gatewayIdentifier': gateway_id,
        'name': gw['name'],
        'roleArn': gw['roleArn'],
        'protocolType': gw['protocolType'],
        'authorizerType': gw['authorizerType'],
        'authorizerConfiguration': {
            'customJWTAuthorizer': {
                'discoveryUrl': correct_discovery_url,
                'allowedAudience': [gateway_id],
            }
        },
    }
    if gw.get('exceptionLevel'):
        update_kwargs['exceptionLevel'] = gw['exceptionLevel']
    agentcore_client.update_gateway(**update_kwargs)
    logger.info('AllowedAudience updated to Gateway ID.')


# ---------------------------------------------------------------------------
# MCP + Connect registration
# ---------------------------------------------------------------------------


def find_existing_mcp_app(appintegrations_client, namespace, app_name):
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


def register_mcp_with_connect(session, connect_instance_id, gateway_url,
                               gateway_id, stack_name):
    appintegrations_client = session.client('appintegrations')
    connect_client = session.client('connect')

    namespace = gateway_id
    app_name = f'{stack_name} MCP Server'

    existing_arn, _ = find_existing_mcp_app(appintegrations_client, namespace, app_name)
    if existing_arn:
        logger.info('MCP app already exists: %s', existing_arn)
        app_arn = existing_arn
    else:
        logger.info('Creating MCP_SERVER application...')
        resp = appintegrations_client.create_application(
            Name=app_name,
            Namespace=namespace,
            ApplicationType='MCP_SERVER',
            Description=f'Stability360 Actions MCP tool server ({len(MCP_TOOL_OPERATIONS)} tools)',
            ApplicationSourceConfig={
                'ExternalUrlConfig': {'AccessUrl': gateway_url}
            },
            Permissions=[],
        )
        app_arn = resp['Arn']
        logger.info('Created. ARN: %s', app_arn)

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
# Security profile
# ---------------------------------------------------------------------------


def find_or_create_security_profile(connect_client, instance_id, profile_name=None):
    profile_name = profile_name or SECURITY_PROFILE_NAME
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

    logger.info('Creating security profile: %s', profile_name)
    try:
        resp = connect_client.create_security_profile(
            SecurityProfileName=profile_name,
            Description='Security profile for Stability360 Actions AI Agent with MCP tool access',
            InstanceId=instance_id,
        )
        sp_id = resp.get('SecurityProfileId')
        logger.info('Security profile created: %s', sp_id)
        return sp_id
    except Exception as e:
        logger.warning('Could not create security profile: %s', e)
        return None


def update_security_profile_tools(connect_client, instance_id,
                                   security_profile_id, gateway_namespace,
                                   tool_names):
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
        logger.info('You may need to add MCP tool access manually:')
        logger.info('  Users → Security profiles → %s → Tools', SECURITY_PROFILE_NAME)


# ---------------------------------------------------------------------------
# Q Connect — assistant discovery
# ---------------------------------------------------------------------------


def find_qconnect_assistant(session, connect_instance_id):
    if connect_instance_id:
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
                        assistant_id = arn.split('/')[-1] if '/' in arn else None
                        logger.info('Found Q Connect assistant: %s', assistant_id)
                        return assistant_id, arn
        except ClientError:
            logger.debug('Could not list WISDOM_ASSISTANT associations', exc_info=True)
    else:
        try:
            qconnect_client = session.client('qconnect')
            resp = qconnect_client.list_assistants()
            assistants = resp.get('assistantSummaries', [])
            if assistants:
                a = assistants[0]
                return a['assistantId'], a['assistantArn']
        except ClientError:
            logger.debug('Could not list Q Connect assistants', exc_info=True)

    return None, None


# ---------------------------------------------------------------------------
# Q Connect — orchestration prompt
# ---------------------------------------------------------------------------


def find_existing_prompt(qconnect_client, assistant_id, prompt_name):
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
    qconnect_client = session.client('qconnect')

    if not os.path.isfile(prompt_file):
        logger.error('Prompt file not found: %s', prompt_file)
        return None

    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt_text = f.read()

    logger.info('Prompt content loaded (%d chars) from %s', len(prompt_text), prompt_file)

    existing_id, _ = find_existing_prompt(qconnect_client, assistant_id, prompt_name)

    template_config = {
        'textFullAIPromptEditTemplateConfiguration': {
            'text': prompt_text,
        }
    }

    if existing_id:
        logger.info('Prompt already exists: %s — updating...', existing_id)
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

        # Create a new version after updating so the latest content is published
        try:
            qconnect_client.create_ai_prompt_version(
                assistantId=assistant_id, aiPromptId=existing_id,
            )
            logger.info('Prompt version created after update.')
        except ClientError as e:
            # Version creation may fail if content hasn't changed — that's OK
            logger.debug('Could not create prompt version: %s', e)

        return f'{existing_id}:$LATEST'

    logger.info('Creating orchestration prompt: %s', prompt_name)
    logger.info('  Type: ORCHESTRATION, Model: %s, Format: MESSAGES', model_id)
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
            existing_id, _ = find_existing_prompt(
                qconnect_client, assistant_id, prompt_name,
            )
            return f'{existing_id}:$LATEST' if existing_id else None
        logger.warning('Could not create prompt: %s', e)
        return None


# ---------------------------------------------------------------------------
# Q Connect — AI Agent (CREATE new agent — NOT default)
# ---------------------------------------------------------------------------


def find_existing_ai_agent(qconnect_client, assistant_id, agent_name):
    try:
        resp = qconnect_client.list_ai_agents(assistantId=assistant_id)
        for agent in resp.get('aiAgentSummaries', []):
            if agent.get('name') == agent_name:
                return agent.get('aiAgentId'), agent.get('aiAgentArn')
    except ClientError:
        logger.debug('Could not list AI agents', exc_info=True)
    return None, None


def find_existing_kb_association(qconnect_client, assistant_id):
    try:
        resp = qconnect_client.list_assistant_associations(
            assistantId=assistant_id,
        )
        for assoc in resp.get('assistantAssociationSummaries', []):
            if assoc.get('associationType') == 'KNOWLEDGE_BASE':
                assoc_id = assoc.get('assistantAssociationId')
                kb_data = assoc.get('associationData', {}).get(
                    'knowledgeBaseAssociation', {},
                )
                kb_id = kb_data.get('knowledgeBaseId')
                return assoc_id, kb_id
    except ClientError:
        logger.debug('Could not list assistant associations', exc_info=True)
    return None, None


def _build_retrieve_override_values(assistant_id, kb_association_id):
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
                    'value': json.dumps([kb_association_id]),
                },
            },
        },
    ]


def _build_agent_tool_configurations(gateway_id, assistant_id=None,
                                      kb_association_id=None):
    """Build tool configurations for the actions agent.

    Includes: Complete, Escalate, Retrieve (KB), and 2 MCP action tools
    (scoringCalculate + resourceLookup).
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

    # Add MCP action tools
    tool_instructions = {
        'scoringCalculate': SCORING_TOOL_INSTRUCTION,
        'resourceLookup': RESOURCE_LOOKUP_TOOL_INSTRUCTION,
    }

    for op_id in MCP_TOOL_OPERATIONS:
        tool_name = f'{MCP_TARGET_NAME}___{op_id}'
        tool_name_safe = tool_name.replace('-', '_')
        mcp_tool_id = f'gateway_{gateway_id}__{tool_name}'

        tools.append({
            'toolName': tool_name_safe,
            'toolType': 'MODEL_CONTEXT_PROTOCOL',
            'toolId': mcp_tool_id,
            'instruction': {
                'instruction': tool_instructions[op_id],
            },
        })

    return tools


def _get_existing_agent_config(qconnect_client, assistant_id, agent_id):
    """Read the existing agent config so we never lose tools during updates."""
    try:
        resp = qconnect_client.get_ai_agent(
            assistantId=assistant_id, aiAgentId=agent_id,
        )
        return resp.get('aiAgent', {}).get('configuration', {})
    except ClientError:
        logger.debug('Could not read existing agent config', exc_info=True)
        return {}


def _strip_mcp_overrides(tools):
    """Strip fields that MCP tools reject (inputSchema, outputSchema, description, title)."""
    MCP_BLOCKED_FIELDS = {'inputSchema', 'outputSchema', 'description', 'title'}
    cleaned = []
    for tool in tools:
        if tool.get('toolType') == 'MODEL_CONTEXT_PROTOCOL':
            tool = {k: v for k, v in tool.items() if k not in MCP_BLOCKED_FIELDS}
        cleaned.append(tool)
    return cleaned


def _safe_update_ai_agent(qconnect_client, assistant_id, agent_id, config):
    """Update an agent, always preserving existing tools if new config has none.

    The update_ai_agent API replaces the ENTIRE configuration.
    If toolConfigurations is missing, all tools get wiped. This helper
    reads the existing config first and merges tools to prevent that.
    """
    orch_config = config.get('orchestrationAIAgentConfiguration', {})
    new_tools = orch_config.get('toolConfigurations')

    if not new_tools:
        # No tools in the new config — preserve existing ones
        existing_config = _get_existing_agent_config(
            qconnect_client, assistant_id, agent_id,
        )
        existing_orch = existing_config.get('orchestrationAIAgentConfiguration', {})
        existing_tools = existing_orch.get('toolConfigurations', [])

        if existing_tools:
            logger.info('Preserving %d existing tools during agent update.', len(existing_tools))
            orch_config['toolConfigurations'] = existing_tools
            config['orchestrationAIAgentConfiguration'] = orch_config

    # Strip fields that MCP tools reject
    if orch_config.get('toolConfigurations'):
        orch_config['toolConfigurations'] = _strip_mcp_overrides(
            orch_config['toolConfigurations'],
        )

    qconnect_client.update_ai_agent(
        assistantId=assistant_id,
        aiAgentId=agent_id,
        configuration=config,
        visibilityStatus='PUBLISHED',
    )


def create_ai_agent(session, assistant_id, agent_name, description,
                     connect_instance_id, custom_prompt_id=None,
                     gateway_id=None):
    """Create a NEW ORCHESTRATION AI agent for the actions tools.

    This agent is NOT set as the default. It exists alongside the
    thrive-at-work agent.
    """
    qconnect_client = session.client('qconnect')

    existing_id, _ = find_existing_ai_agent(qconnect_client, assistant_id, agent_name)
    if existing_id:
        logger.info('AI Agent already exists: %s (ID: %s) — updating config...', agent_name, existing_id)
        if custom_prompt_id or gateway_id:
            try:
                kb_assoc_id, _ = find_existing_kb_association(qconnect_client, assistant_id)
                tools = _build_agent_tool_configurations(
                    gateway_id=gateway_id, assistant_id=assistant_id,
                    kb_association_id=kb_assoc_id,
                )

                region = session.region_name
                account = session.client('sts').get_caller_identity()['Account']
                connect_instance_arn = f'arn:aws:connect:{region}:{account}:instance/{connect_instance_id}'

                config = {
                    'orchestrationAIAgentConfiguration': {
                        'orchestrationAIPromptId': custom_prompt_id,
                        'locale': 'en_US',
                        'connectInstanceArn': connect_instance_arn,
                        'toolConfigurations': tools,
                    }
                }

                _safe_update_ai_agent(
                    qconnect_client, assistant_id, existing_id, config,
                )
                logger.info('AI Agent updated with new tools and prompt.')
            except Exception as e:
                logger.warning('Could not update agent: %s', e)
        # NOT setting as default — this is intentional
        return existing_id

    prompt_id = custom_prompt_id
    if not prompt_id:
        logger.warning('No orchestration prompt available.')
        return None

    region = session.region_name
    account = session.client('sts').get_caller_identity()['Account']
    connect_instance_arn = f'arn:aws:connect:{region}:{account}:instance/{connect_instance_id}'

    kb_assoc_id, _ = find_existing_kb_association(qconnect_client, assistant_id)
    if kb_assoc_id:
        logger.info('KB association found for Retrieve tool: %s', kb_assoc_id)

    tools = _build_agent_tool_configurations(
        gateway_id=gateway_id, assistant_id=assistant_id,
        kb_association_id=kb_assoc_id,
    )
    tool_names = [t['toolName'] for t in tools]

    config = {
        'orchestrationAIAgentConfiguration': {
            'orchestrationAIPromptId': prompt_id,
            'locale': 'en_US',
            'connectInstanceArn': connect_instance_arn,
            'toolConfigurations': tools,
        }
    }

    logger.info('Creating AI Agent: %s (type: ORCHESTRATION)', agent_name)
    logger.info('  Prompt: %s', prompt_id)
    logger.info('  Tools: %s', ', '.join(tool_names))
    logger.info('  NOTE: This agent will NOT be set as default')

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

        try:
            qconnect_client.create_ai_agent_version(
                assistantId=assistant_id, aiAgentId=agent_id,
            )
            logger.info('AI Agent version 1 created.')
        except ClientError:
            logger.warning('Could not create agent version', exc_info=True)

        # NOT setting as default — intentional
        logger.info('Agent created but NOT set as default (actions-only agent).')
        return agent_id

    except Exception as e:
        err_str = str(e).lower()
        if 'already exists' in err_str or 'conflict' in err_str:
            logger.info('AI Agent already exists.')
            existing_id, _ = find_existing_ai_agent(
                qconnect_client, assistant_id, agent_name,
            )
            return existing_id
        logger.warning('Could not create AI Agent: %s', e)
        return None


# ---------------------------------------------------------------------------
# Tool config reference
# ---------------------------------------------------------------------------


def generate_tool_config_file(gateway_id, target_name, agent_name,
                               agent_id, assistant_id, output_path):
    tools = []
    for op_id in MCP_TOOL_OPERATIONS:
        tool_name = f'{target_name}___{op_id}'
        tool_id = f'gateway_{gateway_id}__{tool_name}'
        tools.append({
            'operationId': op_id,
            'toolName': tool_name.replace('-', '_'),
            'toolId': tool_id,
        })

    config = {
        '_note': '=== MCP TOOL REFERENCE: Auto-configured during deployment ===',
        'agent': {
            'name': agent_name,
            'agentId': agent_id,
            'assistantId': assistant_id,
            'isDefault': False,
        },
        'gateway': {
            'gatewayId': gateway_id,
            'targetName': target_name,
        },
        'tools': tools,
    }

    with open(output_path, 'w') as f:
        json.dump(config, f, indent=2)
    logger.info('Tool config reference written to: %s', output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description='Deploy Stability360 Actions stack (2 MCP tools)',
    )
    parser.add_argument('--stack-name', default=DEFAULT_STACK_NAME)
    parser.add_argument('--region', default=DEFAULT_REGION)
    parser.add_argument('--environment', default=DEFAULT_ENVIRONMENT,
                        choices=['dev', 'staging', 'prod'])
    parser.add_argument('--enable-mcp', action='store_true')
    parser.add_argument('--connect-instance-id', default='')
    parser.add_argument('--update-code-only', action='store_true')
    parser.add_argument('--update-prompt', action='store_true')
    parser.add_argument('--connect-only', action='store_true',
                        help='Skip CFN/Lambda, do MCP (5-7) + Connect (8-13) steps only')
    parser.add_argument('--openapi-spec-url', default='',
                        help='URL for MCP-facing OpenAPI spec (auto-detected if not set)')
    parser.add_argument('--model-id', default=ORCHESTRATION_PROMPT_MODEL)
    parser.add_argument('--delete', action='store_true',
                        help='Delete CFN stack only (use --teardown for full cleanup)')
    parser.add_argument('--teardown', action='store_true',
                        help='Full teardown: delete all resources (MCP gateway, agent, prompt, '
                             'integration, credentials, CFN stack)')
    parser.add_argument('--delete-security-profile', action='store_true',
                        help='With --teardown: also attempt to delete the Connect security profile')
    args = parser.parse_args()

    # Init resource names
    init_resource_names(args.stack_name)

    logger.info('=' * 60)
    logger.info('Stability360 Actions — Deployment')
    logger.info('=' * 60)
    logger.info('Stack name:    %s', args.stack_name)
    logger.info('Region:        %s', args.region)
    logger.info('Environment:   %s', args.environment)

    session = boto3.Session(region_name=args.region)
    cf_client = session.client('cloudformation')

    # --- Teardown mode (full cleanup) ---
    if args.teardown:
        if not args.connect_instance_id:
            logger.warning('No --connect-instance-id provided — only CFN + MCP resources will be deleted.')
        teardown_all(session, args.stack_name, args.connect_instance_id, args.region,
                     delete_security_profile=args.delete_security_profile)
        return

    # --- Delete mode (CFN stack only) ---
    if args.delete:
        delete_stack(cf_client, args.stack_name)
        return

    # --- Update code only ---
    if args.update_code_only:
        outputs = get_stack_outputs(cf_client, args.stack_name)
        lambda_client = session.client('lambda')
        update_lambda_code(lambda_client, outputs['ActionsFunctionName'], LAMBDA_CODE_DIR)
        return

    # --- Update prompt only ---
    if args.update_prompt:
        if not args.connect_instance_id:
            logger.error('--connect-instance-id required for --update-prompt')
            sys.exit(1)
        assistant_id, _ = find_qconnect_assistant(session, args.connect_instance_id)
        if not assistant_id:
            logger.error('Could not find Q Connect assistant')
            sys.exit(1)
        prompt_id = create_or_update_orchestration_prompt(
            session, assistant_id, ORCHESTRATION_PROMPT_NAME,
            ORCHESTRATION_PROMPT_FILE, args.model_id,
        )
        logger.info('Prompt updated: %s', prompt_id)
        return

    # --- Connect-only mode (skip CFN steps 1-4, do MCP 5-7 + Connect 8-13) ---
    if args.connect_only:
        if not args.connect_instance_id:
            logger.error('--connect-instance-id required for --connect-only')
            sys.exit(1)
        outputs = get_stack_outputs(cf_client, args.stack_name)
        if not outputs:
            logger.error('Could not read stack outputs for %s', args.stack_name)
            sys.exit(1)
        api_url = outputs.get('ActionsApiUrl', '')
        spec_bucket = outputs.get('SpecBucketName', '')
        api_key_id = outputs.get('ActionsApiKeyId', '')
        gateway_id = outputs.get('McpGatewayId', '')
        connect_instance_url = ''
        try:
            connect_client = session.client('connect')
            resp = connect_client.describe_instance(InstanceId=args.connect_instance_id)
            connect_instance_url = resp['Instance'].get('InstanceAccessUrl', '')
            if not connect_instance_url:
                connect_instance_url = f'https://{args.connect_instance_id}.my.connect.aws'
        except Exception:
            connect_instance_url = f'https://{args.connect_instance_id}.my.connect.aws'
        logger.info('Connect-only mode: skipping CFN/Lambda/KB steps')
        logger.info('API URL:     %s', api_url)
        logger.info('Gateway:     %s', gateway_id)
        # Jump to MCP steps (5-7) + Connect steps (8-13)
        agentcore_client = session.client('bedrock-agentcore-control')
        logger.info('')
        logger.info('--- Step 5: OpenAPI spec ---')
        openapi_s3_location = outputs.get('OpenApiSpecS3Location', '')
        if openapi_s3_location:
            logger.info('OpenAPI spec from CFN: %s', openapi_s3_location)
            openapi_uri = openapi_s3_location
        else:
            s3_client = session.client('s3')
            openapi_uri = upload_openapi_spec(s3_client, spec_bucket, api_url)
            logger.info('OpenAPI URI: %s', openapi_uri)
        logger.info('')
        logger.info('--- Step 6: Register API key credential ---')
        api_key_value = outputs.get('ApiKeyValue', '')
        if not api_key_value:
            apigw_client = session.client('apigateway')
            api_key_value = get_api_key_value(apigw_client, api_key_id)
        cred_arn = register_api_key_credential(
            agentcore_client, API_KEY_CREDENTIAL_NAME, api_key_value,
        )
        logger.info('')
        logger.info('--- Step 7: Create MCP REST API target ---')
        target_id = create_or_update_mcp_target(
            agentcore_client, gateway_id, MCP_TARGET_NAME,
            openapi_uri, cred_arn,
        )
        connect_client = session.client('connect')
        gateway_url = outputs.get('McpGatewayUrl', '')
        logger.info('')
        logger.info('--- Step 8: Update gateway AllowedAudience ---')
        update_gateway_audience(session, gateway_id, connect_instance_url)
        logger.info('')
        logger.info('--- Step 9: Register MCP with Connect ---')
        register_mcp_with_connect(
            session, args.connect_instance_id, gateway_url,
            gateway_id, args.stack_name,
        )
        logger.info('')
        logger.info('--- Step 10: Create security profile ---')
        sp_id = find_or_create_security_profile(
            connect_client, args.connect_instance_id,
        )
        if sp_id and gateway_id:
            update_security_profile_tools(
                connect_client, args.connect_instance_id, sp_id,
                gateway_id, MCP_TOOL_NAMES,
            )
        logger.info('')
        logger.info('--- Step 11: Create orchestration prompt ---')
        assistant_id, _ = find_qconnect_assistant(session, args.connect_instance_id)
        prompt_id = None
        if assistant_id:
            prompt_id = create_or_update_orchestration_prompt(
                session, assistant_id, ORCHESTRATION_PROMPT_NAME,
                ORCHESTRATION_PROMPT_FILE, args.model_id,
            )
        logger.info('')
        logger.info('--- Step 12: Create AI Agent (NOT default) ---')
        agent_id = None
        if assistant_id and prompt_id:
            agent_id = create_ai_agent(
                session, assistant_id, AI_AGENT_NAME, AI_AGENT_DESCRIPTION,
                args.connect_instance_id,
                custom_prompt_id=prompt_id,
                gateway_id=gateway_id,
            )
        logger.info('')
        logger.info('--- Step 13: Generate MCP tool config ---')
        if gateway_id and agent_id and assistant_id:
            generate_tool_config_file(
                gateway_id, MCP_TARGET_NAME, AI_AGENT_NAME,
                agent_id, assistant_id, MCP_TOOL_CONFIG_FILE,
            )
        logger.info('')
        logger.info('=' * 60)
        logger.info('Connect-only deployment complete!')
        logger.info('Agent: %s', agent_id or 'N/A')
        logger.info('Tools: %s', ', '.join(MCP_TOOL_OPERATIONS))
        logger.info('=' * 60)
        return

    # ===================================================================
    # FULL DEPLOYMENT
    # ===================================================================

    # Resolve Connect instance URL (needed for CFN)
    connect_instance_url = ''
    if args.connect_instance_id:
        args.enable_mcp = True
        try:
            connect_client = session.client('connect')
            resp = connect_client.describe_instance(InstanceId=args.connect_instance_id)
            connect_instance_url = resp['Instance'].get('InstanceAccessUrl', '')
            if not connect_instance_url:
                region = args.region
                connect_instance_url = f'https://{args.connect_instance_id}.my.connect.aws'
            logger.info('Connect instance URL: %s', connect_instance_url)
        except Exception as e:
            logger.warning('Could not describe Connect instance: %s', e)
            connect_instance_url = f'https://{args.connect_instance_id}.my.connect.aws'

    # --- Step 1: Deploy CloudFormation stack ---
    logger.info('')
    logger.info('--- Step 1: Deploy CloudFormation stack ---')
    with open(TEMPLATE_FILE, 'r') as f:
        template_body = f.read()

    # Build OpenAPI spec URL for CFN custom resource (S3 upload)
    # The spec URL can be a local file path via deploy.py pre-upload, or a public URL
    openapi_spec_url = args.openapi_spec_url if hasattr(args, 'openapi_spec_url') and args.openapi_spec_url else ''
    if not openapi_spec_url and os.path.isfile(OPENAPI_SPEC_TEMPLATE):
        # Pre-upload the spec template to S3 so CFN custom resource can fetch it
        s3_client = session.client('s3')
        spec_bucket_name = f'{args.stack_name}-specs-{args.region}-{session.client("sts").get_caller_identity()["Account"]}'
        try:
            with open(OPENAPI_SPEC_TEMPLATE, 'r') as sf:
                spec_body = sf.read()
            s3_client.put_object(
                Bucket=spec_bucket_name,
                Key='openapi/actions-spec-template.yaml',
                Body=spec_body.encode('utf-8'),
                ContentType='application/x-yaml',
            )
            openapi_spec_url = f's3://{spec_bucket_name}/openapi/actions-spec-template.yaml'
            logger.info('Pre-uploaded spec template to %s', openapi_spec_url)
        except Exception as e:
            logger.warning('Could not pre-upload spec template: %s', e)
            logger.info('CFN custom resource may need OpenApiSpecUrl parameter')

    action = deploy_stack(
        cf_client, args.stack_name, template_body, args.environment,
        enable_mcp=args.enable_mcp or bool(args.connect_instance_id),
        enable_connect=bool(args.connect_instance_id),
        connect_instance_id=args.connect_instance_id,
        connect_instance_url=connect_instance_url,
        openapi_spec_url=openapi_spec_url,
    )

    if action in ('CREATE', 'UPDATE'):
        target_status = 'CREATE_COMPLETE' if action == 'CREATE' else 'UPDATE_COMPLETE'
        final_status = wait_for_stack(cf_client, args.stack_name, target=target_status)
        if final_status != target_status:
            logger.error('Stack ended with status: %s', final_status)
            sys.exit(1)

    # --- Step 2: Retrieve stack outputs ---
    logger.info('')
    logger.info('--- Step 2: Retrieve stack outputs ---')
    outputs = get_stack_outputs(cf_client, args.stack_name)
    for k, v in sorted(outputs.items()):
        logger.info('  %s = %s', k, v)

    api_url = outputs.get('ActionsApiUrl', '')
    spec_bucket = outputs.get('SpecBucketName', '')
    actions_function = outputs.get('ActionsFunctionName', '')
    api_key_id = outputs.get('ActionsApiKeyId', '')
    gateway_id = outputs.get('McpGatewayId', '')

    # --- Step 3: Update Lambda code ---
    logger.info('')
    logger.info('--- Step 3: Update Lambda code ---')
    lambda_client = session.client('lambda')
    update_lambda_code(lambda_client, actions_function, LAMBDA_CODE_DIR)

    # --- MCP Steps (5-7) ---
    if args.enable_mcp or args.connect_instance_id:
        agentcore_client = session.client('bedrock-agentcore-control')

        # Step 5: OpenAPI spec (now handled by CFN custom resource)
        logger.info('')
        logger.info('--- Step 5: OpenAPI spec ---')
        openapi_s3_location = outputs.get('OpenApiSpecS3Location', '')
        if openapi_s3_location:
            logger.info('OpenAPI spec uploaded by CFN custom resource: %s', openapi_s3_location)
            openapi_uri = openapi_s3_location
        else:
            logger.info('OpenAPI spec not in CFN outputs — uploading manually...')
            s3_client = session.client('s3')
            openapi_uri = upload_openapi_spec(s3_client, spec_bucket, api_url)
            logger.info('OpenAPI URI: %s', openapi_uri)

        # Step 6: Register API key credential
        logger.info('')
        logger.info('--- Step 6: Register API key credential ---')
        api_key_value = outputs.get('ApiKeyValue', '')
        if not api_key_value:
            logger.info('ApiKeyValue not in CFN outputs — retrieving from API Gateway...')
            apigw_client = session.client('apigateway')
            api_key_value = get_api_key_value(apigw_client, api_key_id)
        cred_arn = register_api_key_credential(
            agentcore_client, API_KEY_CREDENTIAL_NAME, api_key_value,
        )

        # Step 7: Create MCP REST API target
        logger.info('')
        logger.info('--- Step 7: Create MCP REST API target ---')
        target_id = create_or_update_mcp_target(
            agentcore_client, gateway_id, MCP_TARGET_NAME,
            openapi_uri, cred_arn,
        )

    # --- Connect Steps (8-13) ---
    if args.connect_instance_id:
        connect_client = session.client('connect')
        gateway_url = outputs.get('McpGatewayUrl', '')

        # Step 8: Update gateway AllowedAudience
        logger.info('')
        logger.info('--- Step 8: Update gateway AllowedAudience ---')
        update_gateway_audience(session, gateway_id, connect_instance_url)

        # Step 9: Register MCP with Connect
        logger.info('')
        logger.info('--- Step 9: Register MCP with Connect ---')
        register_mcp_with_connect(
            session, args.connect_instance_id, gateway_url,
            gateway_id, args.stack_name,
        )

        # Step 10: Create/update security profile
        logger.info('')
        logger.info('--- Step 10: Create security profile ---')
        sp_id = find_or_create_security_profile(
            connect_client, args.connect_instance_id,
        )
        if sp_id and gateway_id:
            update_security_profile_tools(
                connect_client, args.connect_instance_id, sp_id,
                gateway_id, MCP_TOOL_NAMES,
            )

        # Step 11: Create orchestration prompt
        logger.info('')
        logger.info('--- Step 11: Create orchestration prompt ---')
        assistant_id, _ = find_qconnect_assistant(session, args.connect_instance_id)
        prompt_id = None
        if assistant_id:
            prompt_id = create_or_update_orchestration_prompt(
                session, assistant_id, ORCHESTRATION_PROMPT_NAME,
                ORCHESTRATION_PROMPT_FILE, args.model_id,
            )
        else:
            logger.warning('No Q Connect assistant found.')

        # Step 12: Create AI Agent (NOT default)
        logger.info('')
        logger.info('--- Step 12: Create AI Agent (NOT default) ---')
        agent_id = None
        if assistant_id and prompt_id:
            agent_id = create_ai_agent(
                session, assistant_id, AI_AGENT_NAME, AI_AGENT_DESCRIPTION,
                args.connect_instance_id,
                custom_prompt_id=prompt_id,
                gateway_id=gateway_id,
            )

        # Step 13: Generate tool config reference
        logger.info('')
        logger.info('--- Step 13: Generate MCP tool config ---')
        if gateway_id and agent_id and assistant_id:
            generate_tool_config_file(
                gateway_id, MCP_TARGET_NAME, AI_AGENT_NAME,
                agent_id, assistant_id, MCP_TOOL_CONFIG_FILE,
            )

    # --- Summary ---
    logger.info('')
    logger.info('=' * 60)
    logger.info('Deployment complete!')
    logger.info('=' * 60)
    logger.info('Stack:           %s', args.stack_name)
    logger.info('API URL:         %s', api_url)
    logger.info('Lambda:          %s', actions_function)
    logger.info('DynamoDB:        %s', outputs.get('ActionsTableName', ''))
    if gateway_id:
        logger.info('MCP Gateway:     %s', gateway_id)
        logger.info('MCP Target:      %s', MCP_TARGET_NAME)
        logger.info('Tools:           %s', ', '.join(MCP_TOOL_OPERATIONS))
    if args.connect_instance_id:
        logger.info('Connect:         %s', args.connect_instance_id)
        logger.info('Agent:           %s (NOT default)', AI_AGENT_NAME)
        logger.info('Security Profile:%s', SECURITY_PROFILE_NAME)

    logger.info('')
    logger.info('Test endpoints:')
    logger.info('  POST %s/scoring/calculate', api_url)
    logger.info('  POST %s/resources/search', api_url)


if __name__ == '__main__':
    main()
