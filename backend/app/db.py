"""
DynamoDB access layer for CloudLeak.

Wraps boto3''s DynamoDB resource client behind small, purpose-specific
functions so the rest of the app never touches boto3 directly. Three
tables are used:

  - cloudleak-spend-baseline    -> daily spend history + computed baselines
  - cloudleak-anomalies         -> detected cost anomalies
  - cloudleak-flagged-resources -> idle/wasteful resources currently flagged

Table schemas (see infra/dynamodb.tf for the Terraform definitions):

  spend-baseline:     PK = "date" (S)
  anomalies:           PK = "id" (S)
  flagged-resources:   PK = "id" (S)  -- resource id (e.g. instance id)
"""

import logging
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from app.config import settings

logger = logging.getLogger("cloudleak.db")

_dynamodb_resource = None


def get_dynamodb_resource():
    """Lazily create and cache the boto3 DynamoDB resource client."""
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource(
            "dynamodb",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
        )
    return _dynamodb_resource


def get_table(table_name: str):
    return get_dynamodb_resource().Table(table_name)


# ── Spend baseline table ────────────────────────────────────────────────

def put_daily_spend(date: str, amount_usd: float, is_anomaly: bool = False) -> None:
    table = get_table(settings.DYNAMODB_TABLE_SPEND)
    table.put_item(
        Item={
            "date": date,
            "amount_usd": str(amount_usd),
            "is_anomaly": is_anomaly,
        }
    )


def get_recent_daily_spend(days: int) -> List[Dict[str, Any]]:
    """
    Scans the spend table and returns the most recent `days` entries sorted
    ascending by date. A scan is fine here — this table is tiny (one item
    per day) and free-tier DynamoDB scans are cheap at this volume.
    """
    table = get_table(settings.DYNAMODB_TABLE_SPEND)
    response = table.scan()
    items = response.get("Items", [])
    items.sort(key=lambda item: item["date"])
    return items[-days:] if days else items


# ── Anomalies table ──────────────────────────────────────────────────────

def put_anomaly(anomaly: Dict[str, Any]) -> None:
    table = get_table(settings.DYNAMODB_TABLE_ANOMALIES)
    table.put_item(Item=anomaly)


def get_anomalies(limit: int = 50) -> List[Dict[str, Any]]:
    table = get_table(settings.DYNAMODB_TABLE_ANOMALIES)
    response = table.scan(Limit=limit)
    items = response.get("Items", [])
    items.sort(key=lambda item: item.get("detected_at", ""), reverse=True)
    return items


def acknowledge_anomaly(anomaly_id: str) -> None:
    table = get_table(settings.DYNAMODB_TABLE_ANOMALIES)
    table.update_item(
        Key={"id": anomaly_id},
        UpdateExpression="SET acknowledged = :val",
        ExpressionAttributeValues={":val": True},
    )


# ── Flagged resources table ─────────────────────────────────────────────

def put_flagged_resource(resource: Dict[str, Any]) -> None:
    table = get_table(settings.DYNAMODB_TABLE_RESOURCES)
    table.put_item(Item=resource)


def get_flagged_resources() -> List[Dict[str, Any]]:
    table = get_table(settings.DYNAMODB_TABLE_RESOURCES)
    response = table.scan()
    items = response.get("Items", [])
    items.sort(key=lambda item: item.get("estimated_monthly_cost_usd", 0), reverse=True)
    return items


def get_flagged_resource(resource_id: str) -> Optional[Dict[str, Any]]:
    table = get_table(settings.DYNAMODB_TABLE_RESOURCES)
    response = table.get_item(Key={"id": resource_id})
    return response.get("Item")


def mark_resource_remediated(resource_id: str) -> None:
    table = get_table(settings.DYNAMODB_TABLE_RESOURCES)
    table.update_item(
        Key={"id": resource_id},
        UpdateExpression="SET remediated = :val",
        ExpressionAttributeValues={":val": True},
    )


def delete_flagged_resource(resource_id: str) -> None:
    table = get_table(settings.DYNAMODB_TABLE_RESOURCES)
    table.delete_item(Key={"id": resource_id})
