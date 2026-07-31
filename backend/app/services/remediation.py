"""
Remediation actions for flagged resources.

Every remediation call supports dry_run (default True) — the function
always computes and returns what it *would* do, and only calls the actual
AWS mutating API (StopInstances / TerminateInstances) when dry_run=False.
This is the safety guardrail: the dashboard defaults every action to a
dry-run preview, and the user has to explicitly confirm before anything
destructive happens.
"""

import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models import RemediationAction, RemediationRequest, RemediationResult, ResourceType

logger = logging.getLogger("cloudleak.remediation")

_ec2_client = None


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


def _remediate_ec2_instance(request: RemediationRequest) -> RemediationResult:
    now = datetime.now(timezone.utc)

    if request.dry_run:
        action_verb = "stop" if request.action == RemediationAction.STOP else "terminate"
        return RemediationResult(
            resource_id=request.resource_id,
            action=request.action,
            dry_run=True,
            success=True,
            message=(
                f"[DRY RUN] Would {action_verb} EC2 instance {request.resource_id}. "
                f"No changes were made. Re-run with dry_run=false to execute."
            ),
            executed_at=now,
        )

    client = get_ec2_client()

    try:
        if request.action == RemediationAction.STOP:
            client.stop_instances(InstanceIds=[request.resource_id])
            message = f"Stop request sent for EC2 instance {request.resource_id}."
        else:
            client.terminate_instances(InstanceIds=[request.resource_id])
            message = f"Terminate request sent for EC2 instance {request.resource_id}."

        logger.info(message)
        return RemediationResult(
            resource_id=request.resource_id,
            action=request.action,
            dry_run=False,
            success=True,
            message=message,
            executed_at=now,
        )

    except ClientError as exc:
        error_message = f"Failed to {request.action.value} instance {request.resource_id}: {exc}"
        logger.error(error_message)
        return RemediationResult(
            resource_id=request.resource_id,
            action=request.action,
            dry_run=False,
            success=False,
            message=error_message,
            executed_at=now,
        )


def remediate_resource(request: RemediationRequest) -> RemediationResult:
    """
    Main entrypoint. Dispatches to the correct handler based on resource
    type. Only EC2 instances are supported in this MVP — EBS/NAT/EIP
    remediation can be added here following the same dry_run pattern.
    """
    if request.resource_type == ResourceType.EC2_INSTANCE:
        return _remediate_ec2_instance(request)

    return RemediationResult(
        resource_id=request.resource_id,
        action=request.action,
        dry_run=request.dry_run,
        success=False,
        message=f"Remediation for resource type '{request.resource_type.value}' is not yet supported.",
        executed_at=datetime.now(timezone.utc),
    )
