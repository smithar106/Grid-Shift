/** API response types, mirroring the FastAPI contracts. */

export type ObjectiveMode = "cost" | "emissions" | "balanced";
export type SolverStatus =
  | "optimal"
  | "infeasible"
  | "unbounded"
  | "time_limit"
  | "numerical_error";

export interface Facility {
  id: string;
  name: string;
  location_id: string;
  latitude: number | null;
  longitude: number | null;
  timezone: string;
  capacity_mw: number;
  created_at: string;
}

export interface SeriesSummary {
  metric: string;
  unit: string;
  hours: number;
  start_utc: string;
  end_utc: string;
  minimum: number;
  maximum: number;
  total: number;
  is_contiguous: boolean;
}

export interface Dataset {
  id: string;
  facility_id: string | null;
  source: string;
  data_status: string;
  metrics: string[];
  retrieved_at: string;
  created_at: string;
  checksum: string;
  rows_read: number;
  rows_accepted: number;
  original_filename: string | null;
  series: SeriesSummary[];
}

export interface Workload {
  id?: string;
  job_id: string;
  energy_mwh: number;
  release_hour: number;
  deadline_hour: number;
  max_mw: number;
}

export interface Scenario {
  id: string;
  facility_id: string;
  name: string;
  objective: string;
  carbon_price_usd_per_tco2e: number;
  status: string;
  dataset_ids: string[];
  snapshot_checksum: string | null;
  created_at: string;
  workloads: Workload[];
}

export interface HourlyPoint {
  hour: number;
  timestamp_utc: string;
  price_usd_per_mwh: number;
  carbon_tco2e_per_mwh: number;
  capacity_mwh: number;
  baseline_load_mwh: number;
  optimized_flexible_mwh: number;
  optimized_consumption_mwh: number;
  baseline_flexible_mwh: number;
  baseline_consumption_mwh: number;
  optimized_cost_usd: number;
  optimized_emissions_tco2e: number;
  baseline_cost_usd: number;
  baseline_emissions_tco2e: number;
}

export interface SolverDiagnostics {
  status: SolverStatus;
  message: string;
  solver: string;
  solve_seconds: number;
  variables: number;
  constraints: number;
  time_limit_seconds: number;
  iterations: number | null;
}

export interface OptimizationResult {
  status: SolverStatus;
  objective_mode: ObjectiveMode;
  carbon_price_usd_per_tco2e: number;
  objective_value: number;
  total_cost_usd: number;
  total_emissions_tco2e: number;
  baseline_total_cost_usd: number | null;
  baseline_total_emissions_tco2e: number | null;
  cost_savings_pct: number | null;
  emissions_reduction_pct: number | null;
  hourly: HourlyPoint[];
  job_allocations: Record<string, number[]>;
  baseline_allocations: Record<string, number[]> | null;
  diagnostics: SolverDiagnostics;
  assumptions: string[];
  constraint_violations: string[];
}

export interface TradeoffPoint {
  carbon_price_usd_per_tco2e: number;
  status: string;
  total_cost_usd: number;
  total_emissions_tco2e: number;
  cost_savings_pct: number | null;
  emissions_reduction_pct: number | null;
}

export interface TradeoffCurve {
  scenario_id: string;
  snapshot_checksum: string | null;
  horizon_hours: number;
  baseline_total_cost_usd: number | null;
  baseline_total_emissions_tco2e: number | null;
  points: TradeoffPoint[];
}

export interface WeatherPoint {
  timestamp_utc: string;
  temperature_c: number | null;
  relative_humidity_pct: number | null;
}

export interface Weather {
  location_id: string;
  latitude: number;
  longitude: number;
  source: string;
  data_status: string;
  retrieved_at: string;
  from_cache: boolean;
  attribution: string;
  affects_objective: boolean;
  points: WeatherPoint[];
}
