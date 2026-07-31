"""
Spend-related API endpoints — trend chart data, current anomalies, and
acknowledging anomalies from the dashboard.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.db import get_anomalies as db_get_anomalies
from app.db import acknowledge_anomaly as db_acknowledge_anomaly
from app.db import get_recent_daily_spend
from app.models import AnomalyListResponse, CostAnomaly, DailySpendPoint, SpendTrendResponse
from app.services.anomaly import compute_baseline, project_monthly_spend

logger = logging.getLogger("cloudleak.routers.spend")

router = APIRouter(prefix="/api/spend", tags=["spend"])


@router.get("/trend", response_model=SpendTrendResponse)
def get_spend_trend():
    """
    Returns the daily spend trend for the configured baseline window,
    the computed baseline stats, and a rough monthly projection. This is
    the primary data source for the dashboard's spend chart.
    """
    raw_points = get_recent_daily_spend(settings.COST_BASELINE_DAYS + 7)

    points = [
        DailySpendPoint(
            date=item["date"],
            amount_usd=float(item["amount_usd"]),
            is_anomaly=bool(item.get("is_anomaly", False)),
        )
        for item in raw_points
    ]

    baseline = compute_baseline(points[:-1]) if len(points) > 1 else None
    projected = project_monthly_spend(points)

    return SpendTrendResponse(
        points=points,
        baseline=baseline,
        current_projected_monthly_usd=projected,
    )


@router.get("/anomalies", response_model=AnomalyListResponse)
def list_anomalies(limit: int = 50):
    """Returns recently detected cost anomalies, most recent first."""
    raw_anomalies = db_get_anomalies(limit=limit)

    anomalies = []
    for item in raw_anomalies:
        anomalies.append(
            CostAnomaly(
                id=item["id"],
                detected_at=item["detected_at"],
                date=item["date"],
                actual_amount_usd=float(item["actual_amount_usd"]),
                baseline_mean_usd=float(item["baseline_mean_usd"]),
                zscore=float(item["zscore"]),
                risk_level=item["risk_level"],
                description=item["description"],
                related_resource_id=item.get("related_resource_id"),
                acknowledged=bool(item.get("acknowledged", False)),
            )
        )

    return AnomalyListResponse(anomalies=anomalies, total_count=len(anomalies))


@router.post("/anomalies/{anomaly_id}/acknowledge")
def acknowledge_anomaly(anomaly_id: str):
    """Marks an anomaly as acknowledged so it stops showing as a fresh alert on the dashboard."""
    try:
        db_acknowledge_anomaly(anomaly_id)
    except Exception as exc:
        logger.error("Failed to acknowledge anomaly %s: %s", anomaly_id, exc)
        raise HTTPException(status_code=500, detail="Failed to acknowledge anomaly.") from exc

    return {"id": anomaly_id, "acknowledged": True, "updated_at": datetime.now(timezone.utc).isoformat()}
