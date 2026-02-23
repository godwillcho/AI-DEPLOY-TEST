#!/usr/bin/env python3
"""Cleanup script for Stability360 Actions MCP resources.

Removes all MCP-related resources so deploy.py can recreate them fresh.
Useful when MCP tool discovery breaks after a gateway target update.

Resources cleaned up (in order):
  1. Q Connect AI Agent (orchestrator + tool configs)
  2. Q Connect AI Prompt (orchestration prompt)
  3. Connect Integration Association (MCP app <-> Connect)
  4. AppIntegrations Application (MCP_SERVER)
  5. MCP Gateway Target (REST API target on gateway)
  6. Security Profile MCP permissions (optional)

Does NOT delete:
  - CloudFormation stack (Lambda, API Gateway, DynamoDB, MCP Gateway)
  - Knowledge Base or KB association
  - The MCP Gateway itself (managed by CFN)

Usage:
    python steps/stability360-actions/cleanup.py                     # dev (dry-run)
    python steps/stability360-actions/cleanup.py --confirm           # dev (execute)
    python steps/stability360-actions/cleanup.py --env prod --confirm  # prod (execute)
"""

import argparse
import boto3
from botocore.exceptions import ClientError
import json
import logging
import sys
import time

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt='%H:%M:%S')
logger = logging.getLogger('cleanup')

logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Environment configs
# ---------------------------------------------------------------------------

ENVS = {
    'dev': {
        'region': 'us-west-2',
        'connect_instance_id': 'e75a053a-60c7-45f3-83f7-a24df6d3b52d',
        'assistant_id': '7cce1c51-b13c-490b-9c4f-01fd7c9e66eb',
        'stack_name': 'stability360-actions',
    },
    'prod': {
        'region': 'us-east-1',
        'connect_instance_id': '9b50ddcc-8510-441e-a9c8-96e9e9281105',
        'assistant_id': '170bfe70-4ed2-4abe-abb8-1d9f5213128d',
        'stack_name': 'stability360-actions-prod',
    },
}


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def get_stack_outputs(cf_client, stack_name):
    """Get CloudFormation stack outputs as a dict."""
    try:
        resp = cf_client.describe_stacks(StackName=stack_name)
        stacks = resp.get('Stacks', [])
        if not stacks:
            return {}
        outputs = {}
        for o in stacks[0].get('Outputs', []):
            outputs[o['OutputKey']] = o['OutputValue']
        return outputs
    except ClientError:
        return {}


def find_agents_by_prefix(qc, assistant_id, prefix):
    """Find all AI agents whose name starts with prefix."""
    agents = []
    try:
        resp = qc.list_ai_agents(assistantId=assistant_id)
        for agent in resp.get('aiAgentSummaries', []):
            name = agent.get('name', '')
            if name.startswith(prefix):
                agents.append({
                    'id': agent['aiAgentId'],
                    'name': name,
                    'type': agent.get('type', ''),
                })
    except ClientError:
        logger.debug('Could not list agents', exc_info=True)
    return agents


def find_prompts_by_prefix(qc, assistant_id, prefix):
    """Find all AI prompts whose name starts with prefix."""
    prompts = []
    try:
        resp = qc.list_ai_prompts(assistantId=assistant_id)
        for p in resp.get('aiPromptSummaries', []):
            name = p.get('name', '')
            if name.startswith(prefix):
                prompts.append({
                    'id': p['aiPromptId'],
                    'name': name,
                })
    except ClientError:
        logger.debug('Could not list prompts', exc_info=True)
    return prompts


def find_apps_by_namespace(appi, namespace):
    """Find AppIntegrations apps matching a namespace."""
    apps = []
    try:
        resp = appi.list_applications()
        for app in resp.get('Applications', []):
            if app.get('Namespace', '') == namespace:
                apps.append({
                    'arn': app['Arn'],
                    'id': app['Id'],
                    'name': app.get('Name', ''),
                    'namespace': app.get('Namespace', ''),
                })
    except ClientError:
        logger.debug('Could not list applications', exc_info=True)
    return apps


def find_connect_associations(connect, instance_id, app_arns):
    """Find Connect integration associations for given app ARNs."""
    associations = []
    try:
        paginator = connect.get_paginator('list_integration_associations')
        for page in paginator.paginate(
            InstanceId=instance_id, IntegrationType='APPLICATION'
        ):
            for assoc in page.get('IntegrationAssociationSummaryList', []):
                if assoc.get('IntegrationArn', '') in app_arns:
                    associations.append({
                        'id': assoc['IntegrationAssociationId'],
                        'arn': assoc.get('IntegrationArn', ''),
                    })
    except ClientError:
        logger.debug('Could not list associations', exc_info=True)
    return associations


def find_gateway_targets(agentcore, gateway_id):
    """Find all targets on a gateway."""
    targets = []
    try:
        resp = agentcore.list_gateway_targets(gatewayIdentifier=gateway_id)
        for t in resp.get('items', []):
            targets.append({
                'id': t['targetId'],
                'name': t.get('name', ''),
                'status': t.get('status', ''),
            })
    except ClientError:
        logger.debug('Could not list targets', exc_info=True)
    return targets


def find_security_profiles(connect, instance_id, prefix):
    """Find security profiles matching a prefix."""
    profiles = []
    try:
        paginator = connect.get_paginator('list_security_profiles')
        for page in paginator.paginate(InstanceId=instance_id):
            for sp in page.get('SecurityProfileSummaryList', []):
                if sp.get('Name', '').startswith(prefix):
                    profiles.append({
                        'id': sp['Id'],
                        'name': sp.get('Name', ''),
                    })
    except ClientError:
        logger.debug('Could not list security profiles', exc_info=True)
    return profiles


# ---------------------------------------------------------------------------
# Cleanup actions
# ---------------------------------------------------------------------------


def remove_orchestrator_assignment(qc, assistant_id, agent_ids, dry_run=True):
    """Remove the agent from the Connect.SelfService orchestrator if assigned."""
    try:
        resp = qc.get_assistant(assistantId=assistant_id)
        orch_list = resp.get('assistant', {}).get('orchestratorConfigurationList', [])
        for item in orch_list:
            assigned_id = item.get('aiAgentId', '').split(':')[0]
            if assigned_id in agent_ids:
                use_case = item.get('orchestratorUseCase', '')
                if dry_run:
                    logger.info('  [DRY-RUN] Would remove orchestrator: %s -> %s',
                                use_case, item.get('aiAgentId'))
                else:
                    logger.info('  Removing orchestrator assignment: %s', use_case)
                    try:
                        qc.remove_assistant_ai_agent(
                            assistantId=assistant_id,
                            aiAgentType='ORCHESTRATION',
                        )
                        logger.info('  Removed.')
                    except Exception as e:
                        logger.warning('  Could not remove orchestrator: %s', e)
    except Exception as e:
        logger.warning('  Could not check orchestrator: %s', e)


def delete_agent_versions(qc, assistant_id, agent_id, dry_run=True):
    """Delete all versions of an AI agent."""
    try:
        resp = qc.list_ai_agent_versions(
            assistantId=assistant_id, aiAgentId=agent_id
        )
        for v in resp.get('aiAgentVersionSummaries', []):
            ver = v.get('versionNumber', '')
            if dry_run:
                logger.info('  [DRY-RUN] Would delete agent version: %s', ver)
            else:
                try:
                    qc.delete_ai_agent_version(
                        assistantId=assistant_id,
                        aiAgentId=agent_id,
                        versionNumber=ver,
                    )
                    logger.info('  Deleted agent version: %s', ver)
                except Exception as e:
                    logger.warning('  Could not delete version %s: %s', ver, e)
    except Exception as e:
        logger.debug('Could not list agent versions: %s', e)


def cleanup_dev(env_name, cfg, dry_run=True):
    """Full cleanup for an environment."""
    session = boto3.Session(region_name=cfg['region'])
    cf = session.client('cloudformation')
    qc = session.client('qconnect')
    connect = session.client('connect')
    appi = session.client('appintegrations')
    agentcore = session.client('bedrock-agentcore-control')

    stack_name = cfg['stack_name']
    assistant_id = cfg['assistant_id']
    instance_id = cfg['connect_instance_id']
    prefix = stack_name  # e.g. 'stability360-actions' or 'stability360-actions-prod'

    logger.info('=' * 60)
    logger.info('Cleanup: %s (%s)', env_name.upper(), cfg['region'])
    logger.info('Stack:     %s', stack_name)
    logger.info('Assistant: %s', assistant_id)
    logger.info('Connect:   %s', instance_id)
    if dry_run:
        logger.info('MODE:      DRY-RUN (use --confirm to execute)')
    else:
        logger.info('MODE:      EXECUTE')
    logger.info('=' * 60)

    # Get stack outputs for gateway ID
    outputs = get_stack_outputs(cf, stack_name)
    gateway_id = outputs.get('McpGatewayId', '')
    logger.info('MCP Gateway: %s', gateway_id or '(not found)')

    # ---------------------------------------------------------------
    # Step 1: Find and remove AI agents
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('--- Step 1: AI Agents ---')
    agents = find_agents_by_prefix(qc, assistant_id, prefix)
    if not agents:
        logger.info('  No agents found with prefix: %s', prefix)
    else:
        agent_ids = [a['id'] for a in agents]
        # First remove orchestrator assignment
        remove_orchestrator_assignment(qc, assistant_id, agent_ids, dry_run)

        for agent in agents:
            logger.info('  Agent: %s (ID: %s, type: %s)',
                        agent['name'], agent['id'], agent['type'])
            if dry_run:
                logger.info('  [DRY-RUN] Would delete agent and versions')
            else:
                delete_agent_versions(qc, assistant_id, agent['id'], dry_run=False)
                try:
                    qc.delete_ai_agent(
                        assistantId=assistant_id, aiAgentId=agent['id']
                    )
                    logger.info('  Deleted agent: %s', agent['name'])
                except Exception as e:
                    logger.warning('  Could not delete agent: %s', e)

    # ---------------------------------------------------------------
    # Step 2: Find and remove AI prompts
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('--- Step 2: AI Prompts ---')
    prompts = find_prompts_by_prefix(qc, assistant_id, prefix)
    if not prompts:
        logger.info('  No prompts found with prefix: %s', prefix)
    else:
        for prompt in prompts:
            logger.info('  Prompt: %s (ID: %s)', prompt['name'], prompt['id'])
            if dry_run:
                logger.info('  [DRY-RUN] Would delete prompt')
            else:
                try:
                    qc.delete_ai_prompt(
                        assistantId=assistant_id, aiPromptId=prompt['id']
                    )
                    logger.info('  Deleted prompt: %s', prompt['name'])
                except Exception as e:
                    logger.warning('  Could not delete prompt: %s', e)

    # ---------------------------------------------------------------
    # Step 3: Find and remove Connect integration associations
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('--- Step 3: Connect Integration Associations ---')
    if gateway_id:
        apps = find_apps_by_namespace(appi, gateway_id)
        app_arns = [a['arn'] for a in apps]
        associations = find_connect_associations(connect, instance_id, app_arns)
        if not associations:
            logger.info('  No associations found')
        for assoc in associations:
            logger.info('  Association: %s', assoc['id'])
            if dry_run:
                logger.info('  [DRY-RUN] Would delete association')
            else:
                try:
                    connect.delete_integration_association(
                        InstanceId=instance_id,
                        IntegrationAssociationId=assoc['id'],
                    )
                    logger.info('  Deleted association: %s', assoc['id'])
                except Exception as e:
                    logger.warning('  Could not delete association: %s', e)
        time.sleep(2) if not dry_run and associations else None
    else:
        logger.info('  No gateway ID — skipping')

    # ---------------------------------------------------------------
    # Step 4: Find and remove AppIntegrations applications
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('--- Step 4: AppIntegrations Applications ---')
    if gateway_id:
        apps = find_apps_by_namespace(appi, gateway_id)
        if not apps:
            logger.info('  No apps found with namespace: %s', gateway_id)
        for app in apps:
            logger.info('  App: %s (ID: %s)', app['name'], app['id'])
            if dry_run:
                logger.info('  [DRY-RUN] Would delete app')
            else:
                try:
                    appi.delete_application(Arn=app['arn'])
                    logger.info('  Deleted app: %s', app['name'])
                except Exception as e:
                    logger.warning('  Could not delete app: %s', e)
        time.sleep(2) if not dry_run and apps else None
    else:
        logger.info('  No gateway ID — skipping')

    # ---------------------------------------------------------------
    # Step 5: Find and remove MCP gateway targets
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('--- Step 5: MCP Gateway Targets ---')
    if gateway_id:
        targets = find_gateway_targets(agentcore, gateway_id)
        if not targets:
            logger.info('  No targets found on gateway: %s', gateway_id)
        for target in targets:
            logger.info('  Target: %s (ID: %s, status: %s)',
                        target['name'], target['id'], target['status'])
            if dry_run:
                logger.info('  [DRY-RUN] Would delete target')
            else:
                try:
                    agentcore.delete_gateway_target(
                        gatewayIdentifier=gateway_id,
                        targetId=target['id'],
                    )
                    logger.info('  Deleted target: %s', target['name'])
                except Exception as e:
                    logger.warning('  Could not delete target: %s', e)
        # Wait for target deletion
        if not dry_run and targets:
            logger.info('  Waiting for target deletion to propagate...')
            time.sleep(5)
    else:
        logger.info('  No gateway ID — skipping')

    # ---------------------------------------------------------------
    # Step 6: Security profile MCP permissions
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('--- Step 6: Security Profile ---')
    profiles = find_security_profiles(connect, instance_id, prefix)
    if not profiles:
        logger.info('  No security profiles found with prefix: %s', prefix)
    for sp in profiles:
        logger.info('  Profile: %s (ID: %s)', sp['name'], sp['id'])
        if dry_run:
            logger.info('  [DRY-RUN] Would clear MCP permissions')
        else:
            try:
                connect.update_security_profile(
                    SecurityProfileId=sp['id'],
                    InstanceId=instance_id,
                    Applications=[],  # Clear all MCP permissions
                )
                logger.info('  Cleared MCP permissions on: %s', sp['name'])
            except Exception as e:
                logger.warning('  Could not clear permissions: %s', e)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    logger.info('')
    logger.info('=' * 60)
    if dry_run:
        logger.info('DRY-RUN complete. Run with --confirm to execute.')
    else:
        logger.info('Cleanup complete for %s!', env_name.upper())
        logger.info('')
        logger.info('To redeploy, run:')
        if env_name == 'dev':
            logger.info('  python steps/stability360-actions/deploy.py \\')
            logger.info('    --stack-name %s --region %s --environment dev \\',
                        stack_name, cfg['region'])
            logger.info('    --connect-instance-id %s \\', instance_id)
            logger.info('    --thrive-stack-name stability360-thrive-at-work --no-seed-kb')
        elif env_name == 'prod':
            logger.info('  python steps/stability360-actions/deploy.py \\')
            logger.info('    --stack-name %s --region %s --environment prod \\',
                        stack_name, cfg['region'])
            logger.info('    --connect-instance-id %s \\', instance_id)
            logger.info('    --thrive-stack-name stability360-thrive-at-work-prod --no-seed-kb')
    logger.info('=' * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup Stability360 Actions MCP resources'
    )
    parser.add_argument('--env', choices=['dev', 'prod'], default='dev',
                        help='Environment to clean up (default: dev)')
    parser.add_argument('--confirm', action='store_true',
                        help='Actually execute the cleanup (default: dry-run)')
    args = parser.parse_args()

    cfg = ENVS[args.env]
    cleanup_dev(args.env, cfg, dry_run=not args.confirm)
    return 0


if __name__ == '__main__':
    sys.exit(main())
