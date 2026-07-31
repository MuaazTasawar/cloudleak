"use client";

import { useEffect, useState } from "react";
import {
  acknowledgeAnomaly,
  dismissResource,
  getAnomalies,
  getFlaggedResources,
  getSpendTrend,
  remediateResource,
} from "@/lib/api";
import type { AnomalyListResponse, FlaggedResourceListResponse, SpendTrendResponse } from "@/types";
import SpendChart from "@/components/SpendChart";
import AnomalyCard from "@/components/AnomalyCard";
import ResourceTable from "@/components/ResourceTable";

export default function DashboardPage() {
  const [spend, setSpend] = useState<SpendTrendResponse | null>(null);
  const [anomalies, setAnomalies] = useState<AnomalyListResponse | null>(null);
  const [resources, setResources] = useState<FlaggedResourceListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadAll() {
    try {
      setError(null);
      const [spendData, anomalyData, resourceData] = await Promise.all([
        getSpendTrend(),
        getAnomalies(),
        getFlaggedResources(),
      ]);
      setSpend(spendData);
      setAnomalies(anomalyData);
      setResources(resourceData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 30000); // refresh every 30s
    return () => clearInterval(interval);
  }, []);

  async function handleAcknowledge(anomalyId: string) {
    await acknowledgeAnomaly(anomalyId);
    await loadAll();
  }

  async function handleRemediate(resourceId: string, action: "stop" | "terminate", dryRun: boolean) {
    const result = await remediateResource(resourceId, action, dryRun);
    if (!dryRun) {
      await loadAll();
    }
    return result;
  }

  async function handleDismiss(resourceId: string) {
    await dismissResource(resourceId);
    await loadAll();
  }

  if (loading) {
    return <p className="text-[var(--color-text-muted)]">Loading dashboard...</p>;
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[var(--color-risk-high)] bg-[var(--color-surface)] p-4">
        <p className="text-[var(--color-risk-high)]">Failed to load: {error}</p>
        <p className="text-sm text-[var(--color-text-muted)] mt-2">
          Check that the backend is running and NEXT_PUBLIC_API_BASE_URL is correct.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-2xl font-semibold mb-1">CloudLeak Dashboard</h1>
        <p className="text-[var(--color-text-muted)]">
          Projected monthly spend:{" "}
          <span className="text-[var(--color-text-primary)] font-medium">
            ${spend?.current_projected_monthly_usd.toFixed(2) ?? "0.00"}
          </span>
          {resources && resources.total_estimated_monthly_waste_usd > 0 && (
            <>
              {" "}· Estimated waste:{" "}
              <span className="text-[var(--color-risk-high)] font-medium">
                ${resources.total_estimated_monthly_waste_usd.toFixed(2)}/mo
              </span>
            </>
          )}
        </p>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Spend Trend</h2>
        {spend && <SpendChart points={spend.points} baseline={spend.baseline} />}
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Anomalies</h2>
        <div className="space-y-3">
          {anomalies && anomalies.anomalies.length > 0 ? (
            anomalies.anomalies.map((anomaly) => (
              <AnomalyCard key={anomaly.id} anomaly={anomaly} onAcknowledge={handleAcknowledge} />
            ))
          ) : (
            <p className="text-[var(--color-text-muted)] text-sm">No anomalies detected. Spend looks normal.</p>
          )}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Flagged Idle Resources</h2>
        <ResourceTable
          resources={resources?.resources ?? []}
          onRemediate={handleRemediate}
          onDismiss={handleDismiss}
        />
      </section>
    </div>
  );
}
