"use client";

import { Alert, Badge, DefinitionList, Panel, Stat } from "@/components/ui";
import { formatMoney, formatNumber, formatPercent, statusTone } from "@/lib/format";
import type { OptimizationResult } from "@/lib/types";

function tone(value: number | null): "gain" | "loss" | "neutral" {
  if (value === null) return "neutral";
  if (value > 0) return "gain";
  if (value < 0) return "loss";
  return "neutral";
}

/**
 * The headline comparison.
 *
 * Cost and emissions are always shown separately, even in balanced mode, because they are
 * the two quantities the model trades off. Negative changes stay negative and visible.
 */
export function ResultSummary({ result }: { result: OptimizationResult }) {
  const infeasible = result.status === "infeasible";
  const failed = result.status === "numerical_error";

  return (
    <div className="flex flex-col gap-5">
      {infeasible && (
        <Alert tone="loss" title="No feasible schedule exists">
          {result.diagnostics.message}
        </Alert>
      )}
      {failed && (
        <Alert tone="warn" title="The solver result failed verification">
          {result.diagnostics.message}
        </Alert>
      )}

      {!infeasible && (
        <Panel title="Baseline vs optimized">
          <div className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Optimized cost" value={formatMoney(result.total_cost_usd)} />
            <Stat
              label="Baseline cost"
              value={formatMoney(result.baseline_total_cost_usd)}
              detail="Earliest-feasible"
            />
            <Stat
              label="Cost saving"
              value={formatPercent(result.cost_savings_pct)}
              tone={tone(result.cost_savings_pct)}
            />
            <Stat
              label="Optimized emissions"
              value={`${formatNumber(result.total_emissions_tco2e, 2)}`}
              detail="tCO2e"
            />
            <Stat
              label="Baseline emissions"
              value={
                result.baseline_total_emissions_tco2e === null
                  ? "—"
                  : formatNumber(result.baseline_total_emissions_tco2e, 2)
              }
              detail="tCO2e"
            />
            <Stat
              label="Emissions change"
              value={formatPercent(result.emissions_reduction_pct)}
              tone={tone(result.emissions_reduction_pct)}
            />
          </div>
          {result.cost_savings_pct !== null && result.cost_savings_pct < 0 && (
            <p className="mt-4 text-xs text-ink-muted">
              Cost rose because this objective prioritizes emissions. The trade-off is
              shown rather than hidden.
            </p>
          )}
        </Panel>
      )}

      <Panel title="Solver">
        <DefinitionList
          items={[
            {
              term: "Status",
              value: (
                <span className="flex items-center gap-2">
                  <Badge tone={statusTone(result.status)}>{result.status}</Badge>
                  {result.objective_mode} objective
                </span>
              ),
            },
            { term: "Engine", value: result.diagnostics.solver },
            {
              term: "Problem size",
              value: `${formatNumber(result.diagnostics.variables, 0)} variables · ${formatNumber(
                result.diagnostics.constraints,
                0,
              )} constraints`,
            },
            {
              term: "Solve time",
              value: `${formatNumber(result.diagnostics.solve_seconds * 1000, 1)} ms`,
            },
            {
              term: "Objective value",
              value:
                result.objective_mode === "balanced"
                  ? `${formatMoney(result.objective_value)} (cost + priced carbon)`
                  : result.objective_mode === "cost"
                    ? formatMoney(result.objective_value)
                    : `${formatNumber(result.objective_value, 3)} tCO2e`,
            },
          ]}
        />
      </Panel>

      {result.assumptions.length > 0 && (
        <Panel title="Assumptions">
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
        </Panel>
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
