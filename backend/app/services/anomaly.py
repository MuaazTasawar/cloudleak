"""
Cost anomaly detection engine.

Uses a rolling-baseline z-score model: compute the mean and standard
deviation of daily spend over the last N days (excluding today, since
today is partial/incomplete), then flag today''s spend as anomalous if it
deviates from that baseline by more than ANOMALY_ZSCORE_THRESHOLD standard
deviations.

This is intentionally a simple, explainable statistical model rather than
a black-box ML model — the whole point is that in an interview you can
draw the formula on a whiteboard and explain exactly why a given day was
flagged.
"""

import logging
import statistics
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

from app.config import settings
from app.models import CostAnomaly, DailySpendPoint, RiskLevel, SpendBaseline

logger = logging.getLogger("cloudleak.anomaly")


def compute_baseline(historical_points: List[DailySpendPoint]) -> Optional[SpendBaseline]:
    """
    Computes mean and standard deviation from historical daily spend points.
    Requires at least 3 data points to produce a meaningful std dev;
    returns None otherwise (not enough history yet).
    """
    if len(historical_points) < 3:
        logger.warning("Not enough history to compute a baseline (%d points)", len(historical_points))
        return None

    amounts = [point.amount_usd for point in historical_points]
    mean_usd = statistics.mean(amounts)
    std_dev_usd = statistics.stdev(amounts) if len(amounts) > 1 else 0.0

    return SpendBaseline(
        mean_usd=mean_usd,
        std_dev_usd=std_dev_usd,
        window_days=len(historical_points),
        computed_at=datetime.now(timezone.utc),
    )


def compute_zscore(actual_amount: float, baseline: SpendBaseline) -> float:
    """
    Standard z-score: (x - mean) / std_dev. If std_dev is 0 (e.g. spend has
    been perfectly flat), any deviation at all is treated as an infinite
    z-score capped at a large sentinel value, so it still trips detection
    rather than causing a divide-by-zero.
    """
    if baseline.std_dev_usd == 0:
        return 0.0 if actual_amount == baseline.mean_usd else 999.0
    return (actual_amount - baseline.mean_usd) / baseline.std_dev_usd


def classify_risk(zscore: float, actual_amount: float, baseline: SpendBaseline) -> RiskLevel:
    """
    Risk classification combines statistical significance (zscore) with
    absolute dollar impact, since a huge z-score on a $0.50 baseline
    matters a lot less than a smaller z-score on a $50/day baseline.
    """
    absolute_zscore = abs(zscore)
    dollar_increase = actual_amount - baseline.mean_usd

    if absolute_zscore >= settings.ANOMALY_ZSCORE_THRESHOLD * 1.5 and dollar_increase > 5.0:
        return RiskLevel.HIGH
    if absolute_zscore >= settings.ANOMALY_ZSCORE_THRESHOLD:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def detect_anomaly(
    today_point: DailySpendPoint,
    historical_points: List[DailySpendPoint],
    related_resource_id: Optional[str] = None,
) -> Optional[CostAnomaly]:
    """
    Main entrypoint: given today''s spend and historical spend, returns a
    CostAnomaly if today is statistically anomalous, or None if spend
    looks normal.
    """
    baseline = compute_baseline(historical_points)
    if baseline is None:
        return None

    zscore = compute_zscore(today_point.amount_usd, baseline)

    if abs(zscore) < settings.ANOMALY_ZSCORE_THRESHOLD:
        return None

    risk = classify_risk(zscore, today_point.amount_usd, baseline)
    direction = "spike" if zscore > 0 else "drop"

    description = (
        f"Spend {direction} detected on {today_point.date}: "
        f"${today_point.amount_usd:.2f} vs baseline mean ${baseline.mean_usd:.2f} "
        f"(z-score {zscore:.2f} over {baseline.window_days}-day window)"
    )

    return CostAnomaly(
        id=str(uuid4()),
        detected_at=datetime.now(timezone.utc),
        date=today_point.date,
        actual_amount_usd=today_point.amount_usd,
        baseline_mean_usd=baseline.mean_usd,
        zscore=zscore,
        risk_level=risk,
        description=description,
        related_resource_id=related_resource_id,
    )


def project_monthly_spend(historical_points: List[DailySpendPoint]) -> float:
    """
    Rough monthly projection: average daily spend over the available
    history, multiplied by 30. Simple on purpose — this is a directional
    number for the dashboard header, not a billing-accurate forecast.
    """
    if not historical_points:
        return 0.0
    amounts = [point.amount_usd for point in historical_points]
    avg_daily = sum(amounts) / len(amounts)
    return round(avg_daily * 30, 2)
