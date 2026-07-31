"use client";

import type { CostAnomaly } from "@/types";

interface AnomalyCardProps {
  anomaly: CostAnomaly;
  onAcknowledge: (anomalyId: string) => Promise<void>;
}

const RISK_STYLES: Record<string, string> = {
  low: "border-[var(--color-risk-low)] text-[var(--color-risk-low)]",
  medium: "border-[var(--color-risk-medium)] text-[var(--color-risk-medium)]",
  high: "border-[var(--color-risk-high)] text-[var(--color-risk-high)]",
};

export default function AnomalyCard({ anomaly, onAcknowledge }: AnomalyCardProps) {
  const riskStyle = RISK_STYLES[anomaly.risk_level] ?? RISK_STYLES.low;

  return (
    <div
      className={`rounded-lg border bg-[var(--color-surface)] p-4 flex items-start justify-between gap-4 ${
        anomaly.acknowledged ? "opacity-50" : ""
      }`}
    >
      <div>
        <span className={`text-xs font-semibold uppercase border rounded px-2 py-0.5 ${riskStyle}`}>
          {anomaly.risk_level}
        </span>
        <p className="mt-2 text-sm">{anomaly.description}</p>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          Detected {new Date(anomaly.detected_at).toLocaleString()}
        </p>
      </div>
      {!anomaly.acknowledged && (
        <button
          onClick={() => onAcknowledge(anomaly.id)}
          className="shrink-0 text-xs font-medium border border-[var(--color-border)] rounded px-3 py-1.5 hover:bg-[var(--color-border)] transition"
        >
          Acknowledge
        </button>
      )}
    </div>
  );
}
