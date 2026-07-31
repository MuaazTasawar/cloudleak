"""
Pydantic models shared across the CloudLeak backend — API request/response
shapes and the internal data shapes stored in DynamoDB.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ResourceType(str, Enum):
    EC2_INSTANCE = "ec2_instance"
    EBS_VOLUME = "ebs_volume"
    NAT_GATEWAY = "nat_gateway"
    ELASTIC_IP = "elastic_ip"


class ResourceState(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    TERMINATED = "terminated"


# ── Spend / cost tracking ────────────────────────────────────────────────

class DailySpendPoint(BaseModel):
    """A single day's total spend, used to render the spend trend chart."""
    date: str  # ISO date, e.g. "2026-07-30"
    amount_usd: float
    is_anomaly: bool = False


class SpendBaseline(BaseModel):
    """Rolling baseline statistics computed from historical daily spend."""
    mean_usd: float
    std_dev_usd: float
    window_days: int
    computed_at: datetime


class SpendTrendResponse(BaseModel):
    points: List[DailySpendPoint]
    baseline: Optional[SpendBaseline] = None
    current_projected_monthly_usd: float


# ── Anomalies ─────────────────────────────────────────────────────────────

class CostAnomaly(BaseModel):
    id: str
    detected_at: datetime
    date: str
    actual_amount_usd: float
    baseline_mean_usd: float
    zscore: float
    risk_level: RiskLevel
    description: str
    related_resource_id: Optional[str] = None
    acknowledged: bool = False


class AnomalyListResponse(BaseModel):
    anomalies: List[CostAnomaly]
    total_count: int


# ── Flagged / idle resources ────────────────────────────────────────────

class FlaggedResource(BaseModel):
    id: str  # AWS resource id, e.g. i-0abc123...
    resource_type: ResourceType
    state: ResourceState
    region: str
    idle_hours: float
    avg_cpu_percent: float
    avg_network_bytes: float
    estimated_monthly_cost_usd: float
    first_flagged_at: datetime
    last_checked_at: datetime
    risk_level: RiskLevel
    remediated: bool = False


class FlaggedResourceListResponse(BaseModel):
    resources: List[FlaggedResource]
    total_estimated_monthly_waste_usd: float


class RemediationAction(str, Enum):
    STOP = "stop"
    TERMINATE = "terminate"


class RemediationRequest(BaseModel):
    resource_id: str
    resource_type: ResourceType
    action: RemediationAction
    dry_run: bool = Field(
        default=True,
        description="If true, simulates the action and returns what would happen without calling AWS.",
    )


class RemediationResult(BaseModel):
    resource_id: str
    action: RemediationAction
    dry_run: bool
    success: bool
    message: str
    executed_at: datetime
