"""
Idle resource detection.

Flags EC2 instances (and can be extended to EBS volumes, NAT gateways,
Elastic IPs) that are running but doing effectively nothing — low CPU,
low network — for longer than IDLE_HOURS_THRESHOLD. These are the
"forgotten instance" cases that quietly burn free-tier hours or real
money without anyone noticing.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import settings
from app.models import FlaggedResource, ResourceState, ResourceType, RiskLevel
from app.services.cloudwatch import get_instance_utilization, list_running_instances

logger = logging.getLogger("cloudleak.idleness")

# Rough on-demand hourly cost estimates (USD) for common free-tier-adjacent
# instance types, used to compute an estimated monthly waste figure without
# calling the Pricing API (which is slower and region-inconsistent).
INSTANCE_HOURLY_COST_USD: Dict[str, float] = {
    "t2.micro": 0.0116,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
}
DEFAULT_HOURLY_COST_USD = 0.05


def _estimate_monthly_cost(instance_type: str) -> float:
    hourly = INSTANCE_HOURLY_COST_USD.get(instance_type, DEFAULT_HOURLY_COST_USD)
    return round(hourly * 24 * 30, 2)


def is_idle(avg_cpu_percent: float, avg_network_bytes: float) -> bool:
    """
    An instance is considered idle if both its average CPU and average
    network traffic are below the configured thresholds. Both conditions
    must hold — a low-CPU, high-network instance might be doing real I/O
    work (e.g. a proxy) and shouldn''t be flagged.
    """
    return (
        avg_cpu_percent < settings.IDLE_CPU_THRESHOLD_PERCENT
        and avg_network_bytes < settings.IDLE_NETWORK_THRESHOLD_BYTES
    )


def classify_idle_risk(idle_hours: float, estimated_monthly_cost: float) -> RiskLevel:
    """Longer idle time + higher cost = higher priority to flag/remediate."""
    if idle_hours >= settings.IDLE_HOURS_THRESHOLD * 4 or estimated_monthly_cost > 20.0:
        return RiskLevel.HIGH
    if idle_hours >= settings.IDLE_HOURS_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def scan_for_idle_resources(region: Optional[str] = None) -> List[FlaggedResource]:
    """
    Main entrypoint: lists all running EC2 instances, checks utilization
    for each, and returns a list of FlaggedResource for any that qualify
    as idle for at least IDLE_HOURS_THRESHOLD hours.
    """
    region = region or settings.AWS_REGION
    flagged: List[FlaggedResource] = []

    instances = list_running_instances()
    now = datetime.now(timezone.utc)

    for instance in instances:
        instance_id = instance["instance_id"]
        instance_type = instance["instance_type"]

        utilization = get_instance_utilization(instance_id, hours=settings.IDLE_HOURS_THRESHOLD)
        avg_cpu = utilization["avg_cpu_percent"]
        avg_network = utilization["avg_network_bytes"]

        if not is_idle(avg_cpu, avg_network):
            continue

        estimated_cost = _estimate_monthly_cost(instance_type)
        idle_hours = float(settings.IDLE_HOURS_THRESHOLD)
        risk = classify_idle_risk(idle_hours, estimated_cost)

        flagged.append(
            FlaggedResource(
                id=instance_id,
                resource_type=ResourceType.EC2_INSTANCE,
                state=ResourceState.RUNNING,
                region=region,
                idle_hours=idle_hours,
                avg_cpu_percent=round(avg_cpu, 2),
                avg_network_bytes=round(avg_network, 2),
                estimated_monthly_cost_usd=estimated_cost,
                first_flagged_at=now,
                last_checked_at=now,
                risk_level=risk,
            )
        )

    logger.info("Idle resource scan complete: %d of %d running instances flagged", len(flagged), len(instances))
    return flagged
