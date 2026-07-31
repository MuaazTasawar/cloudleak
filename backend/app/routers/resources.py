"""
Resource-related API endpoints — listing flagged idle resources and
triggering remediation (stop/terminate), always dry-run by default.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.db import delete_flagged_resource, get_flagged_resource, get_flagged_resources, mark_resource_remediated
from app.models import (
    FlaggedResource,
    FlaggedResourceListResponse,
    RemediationRequest,
    RemediationResult,
)
from app.services.remediation import remediate_resource
from app.alerts.slack import send_remediation_confirmation

logger = logging.getLogger("cloudleak.routers.resources")

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("", response_model=FlaggedResourceListResponse)
def list_flagged_resources():
    """Returns all currently flagged idle/wasteful resources, sorted by estimated monthly cost."""
    raw_resources = get_flagged_resources()

    resources = []
    total_waste = 0.0
    for item in raw_resources:
        resource = FlaggedResource(
            id=item["id"],
            resource_type=item["resource_type"],
            state=item["state"],
            region=item["region"],
            idle_hours=float(item["idle_hours"]),
            avg_cpu_percent=float(item["avg_cpu_percent"]),
            avg_network_bytes=float(item["avg_network_bytes"]),
            estimated_monthly_cost_usd=float(item["estimated_monthly_cost_usd"]),
            first_flagged_at=item["first_flagged_at"],
            last_checked_at=item["last_checked_at"],
            risk_level=item["risk_level"],
            remediated=bool(item.get("remediated", False)),
        )
        resources.append(resource)
        if not resource.remediated:
            total_waste += resource.estimated_monthly_cost_usd

    return FlaggedResourceListResponse(
        resources=resources,
        total_estimated_monthly_waste_usd=round(total_waste, 2),
    )


@router.post("/{resource_id}/remediate", response_model=RemediationResult)
def remediate_flagged_resource(resource_id: str, request: RemediationRequest):
    """
    Executes (or dry-run previews) a remediation action on a flagged
    resource. request.resource_id in the body should match the path
    param — the path param is treated as the source of truth.
    """
    existing = get_flagged_resource(resource_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No flagged resource found with id '{resource_id}'.")

    request.resource_id = resource_id
    result = remediate_resource(request)

    if result.success and not result.dry_run:
        mark_resource_remediated(resource_id)

    send_remediation_confirmation(
        resource_id=resource_id,
        action=request.action.value,
        success=result.success,
        message=result.message,
    )

    return result


@router.delete("/{resource_id}")
def dismiss_flagged_resource(resource_id: str):
    """Removes a resource from the flagged list without remediating it (e.g. a false positive)."""
    existing = get_flagged_resource(resource_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"No flagged resource found with id '{resource_id}'.")

    delete_flagged_resource(resource_id)
    return {"id": resource_id, "dismissed": True}
