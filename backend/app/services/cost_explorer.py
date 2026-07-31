"""
AWS Cost Explorer integration.

Cost Explorer''s API has a cost per call ($0.01/request outside the free
tier console UI, but the API itself is billed), so this module is written
to be called sparingly (once per collector run, not per dashboard refresh)
and always requests DAILY granularity grouped by service so a single call
covers the whole baseline window.
"""

import logging
from datetime import date, timedelta
from typing import Dict, List

import boto3

from app.config import settings

logger = logging.getLogger("cloudleak.cost_explorer")

_ce_client = None


def get_ce_client():
    global _ce_client
    if _ce_client is None:
        _ce_client = boto3.client(
            "ce",
            region_name="us-east-1",  # Cost Explorer is only available in us-east-1
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
    return _ce_client


def get_daily_spend(days: int = 14) -> List[Dict[str, str]]:
    """
    Returns daily total unblended cost for the last `days` days as a list of
    {"date": "YYYY-MM-DD", "amount_usd": "12.34"} dicts, oldest first.

    Cost Explorer's GetCostAndUsage end date is exclusive, so we request
    [today - days, today] to get `days` full days of history (today's
    partial day is excluded since it's usually incomplete/inaccurate).
    """
    client = get_ce_client()
    end = date.today()
    start = end - timedelta(days=days)

    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": start.isoformat(),
            "End": end.isoformat(),
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )

    results = []
    for period in response.get("ResultsByTime", []):
        day = period["TimePeriod"]["Start"]
        amount = period["Total"]["UnblendedCost"]["Amount"]
        results.append({"date": day, "amount_usd": amount})

    return results


def get_spend_by_service(days: int = 1) -> List[Dict[str, str]]:
    """
    Returns cost broken down by AWS service for the last `days` days.
    Used to help trace which service is driving an anomaly.
    """
    client = get_ce_client()
    end = date.today()
    start = end - timedelta(days=days)

    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": start.isoformat(),
            "End": end.isoformat(),
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )

    breakdown = []
    for period in response.get("ResultsByTime", []):
        for group in period.get("Groups", []):
            service_name = group["Keys"][0]
            amount = group["Metrics"]["UnblendedCost"]["Amount"]
            if float(amount) > 0:
                breakdown.append({"service": service_name, "amount_usd": amount})

    breakdown.sort(key=lambda item: float(item["amount_usd"]), reverse=True)
    return breakdown


def get_month_to_date_spend() -> float:
    """Returns total unblended cost for the current month so far."""
    client = get_ce_client()
    today = date.today()
    start = today.replace(day=1)

    response = client.get_cost_and_usage(
        TimePeriod={
            "Start": start.isoformat(),
            "End": (today + timedelta(days=1)).isoformat(),
        },
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )

    results = response.get("ResultsByTime", [])
    if not results:
        return 0.0
    return float(results[0]["Total"]["UnblendedCost"]["Amount"])
