"""
CloudWatch integration for resource utilization metrics.

Used by the idleness detector to figure out whether a running EC2 instance
(or attached EBS volume) is actually doing anything, or just burning money
while idle. Pulls average CPUUtilization and NetworkIn/NetworkOut over a
lookback window.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import boto3

from app.config import settings

logger = logging.getLogger("cloudleak.cloudwatch")

_cloudwatch_client = None
_ec2_client = None


def get_cloudwatch_client():
    global _cloudwatch_client
    if _cloudwatch_client is None:
        _cloudwatch_client = boto3.client(
            "cloudwatch",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
    return _cloudwatch_client


def get_ec2_client():
    global _ec2_client
    if _ec2_client is None:
        _ec2_client = boto3.client(
            "ec2",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
    return _ec2_client


def list_running_instances() -> List[Dict[str, str]]:
    """Returns a list of {"instance_id", "instance_type", "launch_time"} for all running EC2 instances."""
    client = get_ec2_client()
    response = client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )

    instances = []
    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instances.append(
                {
                    "instance_id": instance["InstanceId"],
                    "instance_type": instance["InstanceType"],
                    "launch_time": instance["LaunchTime"].isoformat(),
                }
            )
    return instances


def _get_metric_average(
    namespace: str,
    metric_name: str,
    dimensions: List[Dict[str, str]],
    hours: int,
    stat: str = "Average",
) -> Optional[float]:
    client = get_cloudwatch_client()
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)

    response = client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,  # 1 hour buckets
        Statistics=[stat],
    )

    datapoints = response.get("Datapoints", [])
    if not datapoints:
        return None

    values = [point[stat] for point in datapoints]
    return sum(values) / len(values)


def get_instance_utilization(instance_id: str, hours: int = 6) -> Dict[str, float]:
    """
    Returns average CPU utilization (%) and average network in+out (bytes)
    for an EC2 instance over the last `hours` hours. Missing metrics
    default to 0.0 rather than raising, since a brand-new instance may not
    have datapoints yet.
    """
    dimensions = [{"Name": "InstanceId", "Value": instance_id}]

    cpu_avg = _get_metric_average("AWS/EC2", "CPUUtilization", dimensions, hours)
    network_in_avg = _get_metric_average("AWS/EC2", "NetworkIn", dimensions, hours)
    network_out_avg = _get_metric_average("AWS/EC2", "NetworkOut", dimensions, hours)

    return {
        "avg_cpu_percent": cpu_avg if cpu_avg is not None else 0.0,
        "avg_network_bytes": (network_in_avg or 0.0) + (network_out_avg or 0.0),
    }
