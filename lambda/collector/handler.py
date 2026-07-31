"""
CloudLeak scheduled Lambda collector.

Triggered every 15 minutes by an EventBridge rule (see infra/eventbridge.tf).
This is the "always-on" half of CloudLeak — it does NOT import from the
backend/app package (Lambda has its own isolated deployment zip), so the
core logic (baseline z-score, idle detection, cost pulls) is duplicated
here in a dependency-light form using only boto3, which is already
available in the Lambda Python runtime.

Flow per run:
  1. Pull last 21 days of daily spend from Cost Explorer
  2. Store today's point in DynamoDB, compute baseline from prior days
  3. If today's spend is anomalous, write an anomaly record + Slack alert
  4. Scan running EC2 instances for idleness via CloudWatch
  5. Write/update flagged resources in DynamoDB + Slack alert on new flags
"""

import json
import logging
import os
import statistics
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

REGION = os.environ.get("AWS_REGION", "eu-north-1")
DYNAMODB_TABLE_SPEND = os.environ["DYNAMODB_TABLE_SPEND"]
DYNAMODB_TABLE_ANOMALIES = os.environ["DYNAMODB_TABLE_ANOMALIES"]
DYNAMODB_TABLE_RESOURCES = os.environ["DYNAMODB_TABLE_RESOURCES"]
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

ANOMALY_ZSCORE_THRESHOLD = float(os.environ.get("ANOMALY_ZSCORE_THRESHOLD", "2.5"))
COST_BASELINE_DAYS = int(os.environ.get("COST_BASELINE_DAYS", "7"))
IDLE_CPU_THRESHOLD_PERCENT = float(os.environ.get("IDLE_CPU_THRESHOLD_PERCENT", "5.0"))
IDLE_NETWORK_THRESHOLD_BYTES = float(os.environ.get("IDLE_NETWORK_THRESHOLD_BYTES", "1000000"))
IDLE_HOURS_THRESHOLD = int(os.environ.get("IDLE_HOURS_THRESHOLD", "6"))

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ce_client = boto3.client("ce", region_name="us-east-1")  # Cost Explorer is us-east-1 only
ec2_client = boto3.client("ec2", region_name=REGION)
cloudwatch_client = boto3.client("cloudwatch", region_name=REGION)


def _post_to_slack(text: str) -> None:
    if not SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not set, skipping alert: %s", text)
        return
    try:
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:  # noqa: BLE001 - alerting should never crash the collector
        logger.error("Failed to send Slack alert: %s", exc)


# ── Cost collection + anomaly detection ─────────────────────────────────

def collect_and_detect_spend_anomaly():
    end = date.today()
    start = end - timedelta(days=COST_BASELINE_DAYS + 7)

    response = ce_client.get_cost_and_usage(
        TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
    )

    daily_points = []
    for period in response.get("ResultsByTime", []):
        day = period["TimePeriod"]["Start"]
        amount = float(period["Total"]["UnblendedCost"]["Amount"])
        daily_points.append({"date": day, "amount_usd": amount})

    spend_table = dynamodb.Table(DYNAMODB_TABLE_SPEND)
    for point in daily_points:
        spend_table.put_item(
            Item={
                "date": point["date"],
                "amount_usd": Decimal(str(point["amount_usd"])),
                "is_anomaly": False,
            }
        )

    if len(daily_points) < 4:
        logger.info("Not enough history yet for anomaly detection (%d points)", len(daily_points))
        return

    history = daily_points[:-1][-COST_BASELINE_DAYS:]
    today_point = daily_points[-1]

    amounts = [p["amount_usd"] for p in history]
    mean_usd = statistics.mean(amounts)
    std_dev_usd = statistics.stdev(amounts) if len(amounts) > 1 else 0.0

    if std_dev_usd == 0:
        zscore = 0.0 if today_point["amount_usd"] == mean_usd else 999.0
    else:
        zscore = (today_point["amount_usd"] - mean_usd) / std_dev_usd

    if abs(zscore) < ANOMALY_ZSCORE_THRESHOLD:
        logger.info("No spend anomaly today (zscore=%.2f)", zscore)
        return

    dollar_increase = today_point["amount_usd"] - mean_usd
    if abs(zscore) >= ANOMALY_ZSCORE_THRESHOLD * 1.5 and dollar_increase > 5.0:
        risk = "high"
    elif abs(zscore) >= ANOMALY_ZSCORE_THRESHOLD:
        risk = "medium"
    else:
        risk = "low"

    direction = "spike" if zscore > 0 else "drop"
    description = (
        f"Spend {direction} detected on {today_point['date']}: "
        f"${today_point['amount_usd']:.2f} vs baseline mean ${mean_usd:.2f} "
        f"(z-score {zscore:.2f} over {len(history)}-day window)"
    )

    anomaly_id = str(uuid4())
    anomalies_table = dynamodb.Table(DYNAMODB_TABLE_ANOMALIES)
    anomalies_table.put_item(
        Item={
            "id": anomaly_id,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "date": today_point["date"],
            "actual_amount_usd": Decimal(str(today_point["amount_usd"])),
            "baseline_mean_usd": Decimal(str(mean_usd)),
            "zscore": Decimal(str(round(zscore, 4))),
            "risk_level": risk,
            "description": description,
            "acknowledged": False,
        }
    )

    spend_table.update_item(
        Key={"date": today_point["date"]},
        UpdateExpression="SET is_anomaly = :val",
        ExpressionAttributeValues={":val": True},
    )

    emoji = {"low": ":large_yellow_circle:", "medium": ":large_orange_circle:", "high": ":red_circle:"}.get(risk, ":warning:")
    _post_to_slack(f"{emoji} *CloudLeak: Cost anomaly detected* ({risk.upper()})\n{description}")
    logger.info("Anomaly recorded: %s", description)


# ── Idle resource scanning ───────────────────────────────────────────────

INSTANCE_HOURLY_COST_USD = {
    "t2.micro": 0.0116,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
}
DEFAULT_HOURLY_COST_USD = 0.05


def _get_metric_average(namespace, metric_name, dimensions, hours):
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=hours)
    response = cloudwatch_client.get_metric_statistics(
        Namespace=namespace,
        MetricName=metric_name,
        Dimensions=dimensions,
        StartTime=start_time,
        EndTime=end_time,
        Period=3600,
        Statistics=["Average"],
    )
    datapoints = response.get("Datapoints", [])
    if not datapoints:
        return None
    values = [point["Average"] for point in datapoints]
    return sum(values) / len(values)


def scan_and_flag_idle_resources():
    response = ec2_client.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
    )

    instances = []
    for reservation in response.get("Reservations", []):
        for instance in reservation.get("Instances", []):
            instances.append(
                {"instance_id": instance["InstanceId"], "instance_type": instance["InstanceType"]}
            )

    resources_table = dynamodb.Table(DYNAMODB_TABLE_RESOURCES)
    now_iso = datetime.now(timezone.utc).isoformat()
    newly_flagged_count = 0

    for instance in instances:
        instance_id = instance["instance_id"]
        instance_type = instance["instance_type"]
        dimensions = [{"Name": "InstanceId", "Value": instance_id}]

        cpu_avg = _get_metric_average("AWS/EC2", "CPUUtilization", dimensions, IDLE_HOURS_THRESHOLD) or 0.0
        net_in = _get_metric_average("AWS/EC2", "NetworkIn", dimensions, IDLE_HOURS_THRESHOLD) or 0.0
        net_out = _get_metric_average("AWS/EC2", "NetworkOut", dimensions, IDLE_HOURS_THRESHOLD) or 0.0
        network_avg = net_in + net_out

        is_idle = cpu_avg < IDLE_CPU_THRESHOLD_PERCENT and network_avg < IDLE_NETWORK_THRESHOLD_BYTES
        if not is_idle:
            continue

        hourly = INSTANCE_HOURLY_COST_USD.get(instance_type, DEFAULT_HOURLY_COST_USD)
        estimated_monthly_cost = round(hourly * 24 * 30, 2)

        if estimated_monthly_cost > 20.0:
            risk = "high"
        elif IDLE_HOURS_THRESHOLD >= 6:
            risk = "medium"
        else:
            risk = "low"

        existing = resources_table.get_item(Key={"id": instance_id}).get("Item")
        is_new = existing is None

        resources_table.put_item(
            Item={
                "id": instance_id,
                "resource_type": "ec2_instance",
                "state": "running",
                "region": REGION,
                "idle_hours": Decimal(str(IDLE_HOURS_THRESHOLD)),
                "avg_cpu_percent": Decimal(str(round(cpu_avg, 2))),
                "avg_network_bytes": Decimal(str(round(network_avg, 2))),
                "estimated_monthly_cost_usd": Decimal(str(estimated_monthly_cost)),
                "first_flagged_at": existing["first_flagged_at"] if existing else now_iso,
                "last_checked_at": now_iso,
                "risk_level": risk,
                "remediated": existing.get("remediated", False) if existing else False,
            }
        )

        if is_new:
            newly_flagged_count += 1
            emoji = {"low": ":large_yellow_circle:", "medium": ":large_orange_circle:", "high": ":red_circle:"}.get(risk, ":warning:")
            _post_to_slack(
                f"{emoji} *CloudLeak: Idle resource flagged* ({risk.upper()})\n"
                f"`{instance_id}` ({instance_type}) idle for {IDLE_HOURS_THRESHOLD}+ hours — "
                f"avg CPU {cpu_avg:.1f}%, estimated cost ${estimated_monthly_cost:.2f}/mo."
            )

    logger.info(
        "Idle scan complete: %d running instances checked, %d newly flagged",
        len(instances),
        newly_flagged_count,
    )


def handler(event, context):
    """Lambda entrypoint — invoked on the EventBridge schedule."""
    logger.info("CloudLeak collector run started")

    try:
        collect_and_detect_spend_anomaly()
    except Exception:
        logger.exception("Spend anomaly collection failed")

    try:
        scan_and_flag_idle_resources()
    except Exception:
        logger.exception("Idle resource scan failed")

    logger.info("CloudLeak collector run finished")
    return {"statusCode": 200, "body": json.dumps({"status": "ok"})}
