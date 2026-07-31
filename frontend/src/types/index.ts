export interface DailySpendPoint {
  date: string;
  amount_usd: number;
  is_anomaly: boolean;
}

export interface SpendBaseline {
  mean_usd: number;
  std_dev_usd: number;
  window_days: number;
  computed_at: string;
}

export interface SpendTrendResponse {
  points: DailySpendPoint[];
  baseline: SpendBaseline | null;
  current_projected_monthly_usd: number;
}

export type RiskLevel = "low" | "medium" | "high";

export interface CostAnomaly {
  id: string;
  detected_at: string;
  date: string;
  actual_amount_usd: number;
  baseline_mean_usd: number;
  zscore: number;
  risk_level: RiskLevel;
  description: string;
  related_resource_id: string | null;
  acknowledged: boolean;
}

export interface AnomalyListResponse {
  anomalies: CostAnomaly[];
  total_count: number;
}

export type ResourceType = "ec2_instance" | "ebs_volume" | "nat_gateway" | "elastic_ip";
export type ResourceState = "running" | "stopped" | "terminated";

export interface FlaggedResource {
  id: string;
  resource_type: ResourceType;
  state: ResourceState;
  region: string;
  idle_hours: number;
  avg_cpu_percent: number;
  avg_network_bytes: number;
  estimated_monthly_cost_usd: number;
  first_flagged_at: string;
  last_checked_at: string;
  risk_level: RiskLevel;
  remediated: boolean;
}

export interface FlaggedResourceListResponse {
  resources: FlaggedResource[];
  total_estimated_monthly_waste_usd: number;
}

export type RemediationActionType = "stop" | "terminate";

export interface RemediationResult {
  resource_id: string;
  action: RemediationActionType;
  dry_run: boolean;
  success: boolean;
  message: string;
  executed_at: string;
}
