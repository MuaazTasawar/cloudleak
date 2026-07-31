"use client";

import { useState } from "react";
import type { FlaggedResource, RemediationActionType, RemediationResult } from "@/types";

interface ResourceTableProps {
  resources: FlaggedResource[];
  onRemediate: (
    resourceId: string,
    action: RemediationActionType,
    dryRun: boolean
  ) => Promise<RemediationResult>;
  onDismiss: (resourceId: string) => Promise<void>;
}

const RISK_BADGE: Record<string, string> = {
  low: "bg-[var(--color-risk-low)]",
  medium: "bg-[var(--color-risk-medium)]",
  high: "bg-[var(--color-risk-high)]",
};

export default function ResourceTable({ resources, onRemediate, onDismiss }: ResourceTableProps) {
  const [pendingPreview, setPendingPreview] = useState<Record<string, RemediationResult>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  async function handlePreview(resourceId: string, action: RemediationActionType) {
    setBusyId(resourceId);
    try {
      const result = await onRemediate(resourceId, action, true);
      setPendingPreview((prev) => ({ ...prev, [resourceId]: result }));
    } finally {
      setBusyId(null);
    }
  }

  async function handleConfirm(resourceId: string, action: RemediationActionType) {
    setBusyId(resourceId);
    try {
      await onRemediate(resourceId, action, false);
      setPendingPreview((prev) => {
        const next = { ...prev };
        delete next[resourceId];
        return next;
      });
    } finally {
      setBusyId(null);
    }
  }

  if (resources.length === 0) {
    return <p className="text-[var(--color-text-muted)] text-sm">No idle resources flagged right now.</p>;
  }

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[var(--color-text-muted)] border-b border-[var(--color-border)]">
            <th className="px-4 py-3 font-medium">Resource</th>
            <th className="px-4 py-3 font-medium">Idle</th>
            <th className="px-4 py-3 font-medium">Avg CPU</th>
            <th className="px-4 py-3 font-medium">Est. Cost/mo</th>
            <th className="px-4 py-3 font-medium">Risk</th>
            <th className="px-4 py-3 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {resources.map((resource) => {
            const preview = pendingPreview[resource.id];
            const badge = RISK_BADGE[resource.risk_level] ?? RISK_BADGE.low;

            return (
              <tr key={resource.id} className="border-b border-[var(--color-border)] last:border-0">
                <td className="px-4 py-3">
                  <div className="font-mono text-xs">{resource.id}</div>
                  <div className="text-xs text-[var(--color-text-muted)]">{resource.resource_type}</div>
                </td>
                <td className="px-4 py-3">{resource.idle_hours.toFixed(0)}h</td>
                <td className="px-4 py-3">{resource.avg_cpu_percent.toFixed(1)}%</td>
                <td className="px-4 py-3">${resource.estimated_monthly_cost_usd.toFixed(2)}</td>
                <td className="px-4 py-3">
                  <span className={`inline-block w-2 h-2 rounded-full mr-2 ${badge}`} />
                  {resource.risk_level}
                </td>
                <td className="px-4 py-3 text-right space-x-2">
                  {resource.remediated ? (
                    <span className="text-xs text-[var(--color-text-muted)]">Remediated</span>
                  ) : preview ? (
                    <>
                      <span className="text-xs text-[var(--color-text-muted)] mr-2">{preview.message}</span>
                      <button
                        disabled={busyId === resource.id}
                        onClick={() => handleConfirm(resource.id, preview.action)}
                        className="text-xs font-medium border border-[var(--color-risk-high)] text-[var(--color-risk-high)] rounded px-2 py-1 hover:bg-[var(--color-risk-high)] hover:text-white transition disabled:opacity-50"
                      >
                        Confirm {preview.action}
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        disabled={busyId === resource.id}
                        onClick={() => handlePreview(resource.id, "stop")}
                        className="text-xs font-medium border border-[var(--color-border)] rounded px-2 py-1 hover:bg-[var(--color-border)] transition disabled:opacity-50"
                      >
                        Stop
                      </button>
                      <button
                        disabled={busyId === resource.id}
                        onClick={() => handlePreview(resource.id, "terminate")}
                        className="text-xs font-medium border border-[var(--color-border)] rounded px-2 py-1 hover:bg-[var(--color-border)] transition disabled:opacity-50"
                      >
                        Terminate
                      </button>
                      <button
                        disabled={busyId === resource.id}
                        onClick={() => onDismiss(resource.id)}
                        className="text-xs font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition disabled:opacity-50"
                      >
                        Dismiss
                      </button>
                    </>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
