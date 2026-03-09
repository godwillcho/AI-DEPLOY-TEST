"""
Stability360 Actions — Queue Availability Checker

Checks real-time agent availability in the BasicQueue using
Amazon Connect GetCurrentMetricData API.

Used by intake_helper to:
  - Show/hide "Speak with someone now" option in getNextSteps
  - Redirect live_transfer requests to callback when no agents available
"""

import logging
import os

import boto3

logger = logging.getLogger('queue_checker')

BASIC_QUEUE_ARN = os.environ.get('BASIC_QUEUE_ARN', '')
CONNECT_INSTANCE_ID = os.environ.get('CONNECT_INSTANCE_ID', '')
CONNECT_REGION = os.environ.get('CONNECT_REGION', os.environ.get('AWS_REGION', 'us-west-2'))


def _extract_queue_id(queue_arn):
    """Extract the queue ID from a Connect queue ARN."""
    # ARN format: arn:aws:connect:region:account:instance/id/queue/queue-id
    if '/queue/' in queue_arn:
        return queue_arn.split('/queue/')[-1]
    return queue_arn


def check_queue_availability(instance_id=None):
    """Check if agents are available or online in BasicQueue.

    Returns dict with:
        agents_available (int): Agents in Available state for this queue
        agents_online (int): Agents logged in (any state)
        is_available (bool): True if at least 1 agent is available
    """
    instance_id = instance_id or CONNECT_INSTANCE_ID
    queue_arn = BASIC_QUEUE_ARN

    if not instance_id or not queue_arn:
        logger.warning('Queue check skipped — missing instance_id or BASIC_QUEUE_ARN')
        return {
            'agents_available': 0,
            'agents_online': 0,
            'is_available': False,
        }

    queue_id = _extract_queue_id(queue_arn)

    try:
        connect = boto3.client('connect', region_name=CONNECT_REGION)
        resp = connect.get_current_metric_data(
            InstanceId=instance_id,
            Filters={'Queues': [queue_id], 'Channels': ['CHAT']},
            CurrentMetrics=[
                {'Name': 'AGENTS_AVAILABLE', 'Unit': 'COUNT'},
                {'Name': 'AGENTS_ONLINE', 'Unit': 'COUNT'},
            ],
        )

        available = 0
        online = 0
        for collection in resp.get('MetricResults', []):
            for metric in collection.get('Collections', []):
                name = metric.get('Metric', {}).get('Name', '')
                value = int(metric.get('Value', 0))
                if name == 'AGENTS_AVAILABLE':
                    available = value
                elif name == 'AGENTS_ONLINE':
                    online = value

        logger.info(
            'Queue availability: %d available, %d online (queue=%s)',
            available, online, queue_id,
        )
        return {
            'agents_available': available,
            'agents_online': online,
            'is_available': available > 0,
        }

    except Exception:
        logger.warning('Queue availability check failed', exc_info=True)
        return {
            'agents_available': 0,
            'agents_online': 0,
            'is_available': False,
        }
