"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailySpendPoint, SpendBaseline } from "@/types";

interface SpendChartProps {
  points: DailySpendPoint[];
  baseline: SpendBaseline | null;
}

export default function SpendChart({ points, baseline }: SpendChartProps) {
  const chartData = points.map((point) => ({
    date: point.date.slice(5), // MM-DD
    amount: point.amount_usd,
    isAnomaly: point.is_anomaly,
  }));

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis dataKey="date" stroke="var(--color-text-muted)" fontSize={12} />
          <YAxis stroke="var(--color-text-muted)" fontSize={12} tickFormatter={(v) => `$${v}`} />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--color-bg)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
            }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, "Spend"]}
          />
          {baseline && (
            <ReferenceLine
              y={baseline.mean_usd}
              stroke="var(--color-text-muted)"
              strokeDasharray="4 4"
              label={{ value: "baseline", fill: "var(--color-text-muted)", fontSize: 11 }}
            />
          )}
          <Line
            type="monotone"
            dataKey="amount"
            stroke="var(--color-accent)"
            strokeWidth={2}
            dot={(props: any) => {
              const isAnomaly = chartData[props.index]?.isAnomaly;
              return (
                <circle
                  key={`dot-${props.index}`}
                  cx={props.cx}
                  cy={props.cy}
                  r={isAnomaly ? 5 : 3}
                  fill={isAnomaly ? "var(--color-risk-high)" : "var(--color-accent)"}
                />
              );
            }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
