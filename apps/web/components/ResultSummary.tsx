"use client";

import { Alert, Badge, DefinitionList, Stat } from "@/components/ui";
import { formatMoney, formatNumber, formatPercent, statusTone } from "@/lib/format";
import type { OptimizationResult } from "@/lib/types";

function tone(value: number | null): "gain" | "loss" | "neutral" {
  if (value === null) return "neutral";
  if (value > 0) return "gain";
  if (value < 0) return "loss";
  return "neutral";
}

/**
 * The answer: what the schedule saves against a valid baseline.
 *
 * Cost and emissions are always shown separately, even in balanced mode, because they are
 * the two quantities the model trades off. Negative changes stay negative and visible.
 */
export function ResultHeadline({ result }: { result: OptimizationResult }) {
  const infeasible = result.status === "infeasible";
  const failed = result.status === "numerical_error";

  if (infeasible || failed) {
    return (
      <Alert
        tone={infeasible ? "loss" : "warn"}
        title={infeasible ? "No feasible schedule exists" : "The solver result failed verification"}
      >
        {result.diagnostics.message}
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Badge tone={statusTone(result.status)}>{result.status}</Badge>
        <span className="text-xs text-ink-muted">
          {result.objective_mode === "balanced"
            ? `balanced · carbon at ${formatMoney(result.carbon_price_usd_per_tco2e)}/tCO2e`
            : `${result.objective_mode} objective`}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3">
        <Stat
          label="Cost"
          value={formatMoney(result.total_cost_usd)}
          detail={`baseline ${formatMoney(result.baseline_total_cost_usd)}`}
        />
        <Stat
          label="Cost saving"
          value={formatPercent(result.cost_savings_pct)}
          tone={tone(result.cost_savings_pct)}
          detail="vs earliest-feasible"
        />
        <Stat
          label="Emissions"
          value={`${formatNumber(result.total_emissions_tco2e, 1)} tCO₂e`}
          detail={
            result.baseline_total_emissions_tco2e === null
              ? undefined
              : `baseline ${formatNumber(result.baseline_total_emissions_tco2e, 1)}`
          }
        />
        <Stat
          label="Emissions change"
          value={formatPercent(result.emissions_reduction_pct)}
          tone={tone(result.emissions_reduction_pct)}
          detail="negative means worse"
        />
        <Stat
          label="Flexible energy moved"
          value={`${formatNumber(
            result.hourly.reduce((sum, point) => sum + point.optimized_flexible_mwh, 0),
            0,
          )} MWh`}
          detail={`over ${result.hourly.length} hours`}
        />
        <Stat
          label="Solve time"
          value={`${formatNumber(result.diagnostics.solve_seconds * 1000, 1)} ms`}
          detail={`${formatNumber(result.diagnostics.variables, 0)} variables`}
        />
      </div>

      {result.cost_savings_pct !== null && result.cost_savings_pct < 0 && (
        <p className="text-xs text-ink-muted">
          Cost rose because this objective prioritizes emissions. The trade-off is shown
          rather than hidden.
        </p>
      )}
    </div>
  );
}

/** Supporting evidence: how the answer was produced and what it assumes. */
export function ResultDetails({ result }: { result: OptimizationResult }) {
  return (
    <div className="flex flex-col gap-5">
      <DefinitionList
        items={[
          { term: "Engine", value: result.diagnostics.solver },
          { term: "Status", value: result.diagnostics.message },
          {
            term: "Problem size",
            value: `${formatNumber(result.diagnostics.variables, 0)} variables · ${formatNumber(
              result.diagnostics.constraints,
              0,
            )} constraints`,
          },
          {
            term: "Objective value",
            value:
              result.objective_mode === "balanced"
                ? `${formatMoney(result.objective_value)} (cost + priced carbon)`
                : result.objective_mode === "cost"
                  ? formatMoney(result.objective_value)
                  : `${formatNumber(result.objective_value, 2)} tCO₂e`,
          },
        ]}
      />

      {result.assumptions.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-muted">
            Assumptions
          </h3>
          <ul className="flex flex-col gap-1 text-xs text-ink-muted">
            {result.assumptions.map((assumption) => (
              <li key={assumption} className="flex gap-2">
                <span className="text-ink-faint" aria-hidden>
                  —
                </span>
                <span>{assumption}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result.constraint_violations.length > 0 && (
        <Alert tone="loss" title="Constraint violations">
          <ul className="flex flex-col gap-1">
            {result.constraint_violations.map((violation) => (
              <li key={violation}>{violation}</li>
            ))}
          </ul>
        </Alert>
      )}
    </div>
  );
}
