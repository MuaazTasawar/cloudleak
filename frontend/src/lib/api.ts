import type {
  AnomalyListResponse,
  FlaggedResourceListResponse,
  RemediationActionType,
  RemediationResult,
  SpendTrendResponse,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`CloudLeak API error ${response.status}: ${body}`);
  }

  return response.json() as Promise<T>;
}

export function getSpendTrend(): Promise<SpendTrendResponse> {
  return apiFetch<SpendTrendResponse>("/api/spend/trend");
}

export function getAnomalies(limit = 50): Promise<AnomalyListResponse> {
  return apiFetch<AnomalyListResponse>(`/api/spend/anomalies?limit=${limit}`);
}

export function acknowledgeAnomaly(anomalyId: string): Promise<{ id: string; acknowledged: boolean }> {
  return apiFetch(`/api/spend/anomalies/${anomalyId}/acknowledge`, { method: "POST" });
}

export function getFlaggedResources(): Promise<FlaggedResourceListResponse> {
  return apiFetch<FlaggedResourceListResponse>("/api/resources");
}

export function remediateResource(
  resourceId: string,
  action: RemediationActionType,
  dryRun: boolean
): Promise<RemediationResult> {
  return apiFetch<RemediationResult>(`/api/resources/${resourceId}/remediate`, {
    method: "POST",
    body: JSON.stringify({
      resource_id: resourceId,
      resource_type: "ec2_instance",
      action,
      dry_run: dryRun,
    }),
  });
}

export function dismissResource(resourceId: string): Promise<{ id: string; dismissed: boolean }> {
  return apiFetch(`/api/resources/${resourceId}`, { method: "DELETE" });
}
