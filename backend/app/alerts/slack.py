"""
Slack alerting via Incoming Webhook.

Kept deliberately dependency-light (plain httpx POST to a webhook URL)
rather than the full Slack SDK, since a webhook is all this project
needs and it keeps the Lambda deployment package small.
"""

import logging
from typing import Optional

import httpx

from app.config import settings
from app.models import CostAnomaly, FlaggedResource

logger = logging.getLogger("cloudleak.alerts.slack")

RISK_EMOJI = {
    "low": ":large_yellow_circle:",
    "medium": ":large_orange_circle:",
    "high": ":red_circle:",
}


def _post_to_slack(text: str) -> bool:
    if not settings.SLACK_WEBHOOK_URL:
        logger.warning("SLACK_WEBHOOK_URL not configured, skipping alert: %s", text)
        return False

    try:
        response = httpx.post(settings.SLACK_WEBHOOK_URL, json={"text": text}, timeout=10.0)
        response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to send Slack alert: %s", exc)
        return False


def send_anomaly_alert(anomaly: CostAnomaly) -> bool:
    emoji = RISK_EMOJI.get(anomaly.risk_level.value, ":warning:")
    text = (
        f"{emoji} *CloudLeak: Cost anomaly detected* ({anomaly.risk_level.value.upper()})\n"
        f"{anomaly.description}"
    )
    return _post_to_slack(text)


def send_idle_resource_alert(resource: FlaggedResource) -> bool:
    emoji = RISK_EMOJI.get(resource.risk_level.value, ":warning:")
    text = (
        f"{emoji} *CloudLeak: Idle resource flagged* ({resource.risk_level.value.upper()})\n"
        f"`{resource.id}` ({resource.resource_type.value}) has been idle for "
        f"{resource.idle_hours:.0f}+ hours — avg CPU {resource.avg_cpu_percent:.1f}%, "
        f"estimated cost ${resource.estimated_monthly_cost_usd:.2f}/mo. "
        f"Review it in the CloudLeak dashboard."
    )
    return _post_to_slack(text)


def send_remediation_confirmation(resource_id: str, action: str, success: bool, message: str) -> bool:
    status_emoji = ":white_check_mark:" if success else ":x:"
    text = f"{status_emoji} *CloudLeak: Remediation {action}* on `{resource_id}`\n{message}"
    return _post_to_slack(text)
