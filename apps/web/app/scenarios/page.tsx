"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  Alert,
  Badge,
  Button,
  EmptyState,
  Loading,
  PageHeader,
  Panel,
  Table,
  TD,
  TH,
} from "@/components/ui";
import { exportUrl, getResults, listScenarios, optimizeScenario } from "@/lib/api";
import {
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
  shortChecksum,
  shortId,
  statusTone,
} from "@/lib/format";
import type { OptimizationResult, Scenario } from "@/lib/types";

const MAX_COMPARE = 4;

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [results, setResults] = useState<Record<string, OptimizationResult>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setScenarios(await listScenarios());
  }, []);

  useEffect(() => {
    (async () => {
      try {
        await refresh();
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Load failed");
      } finally {
        setLoading(false);
      }
    })();
  }, [refresh]);

  const run = async (scenario: Scenario) => {
    setBusy(scenario.id);
    setError(null);
    try {
      const result = await optimizeScenario(scenario.id);
      setResults((current) => ({ ...current, [scenario.id]: result }));
      await refresh();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "Optimization failed");
    } finally {
      setBusy(null);
    }
  };

  const loadResults = async (scenario: Scenario) => {
    setBusy(scenario.id);
    setError(null);
    try {
      const result = await getResults(scenario.id);
      setResults((current) => ({ ...current, [scenario.id]: result }));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No result available");
    } finally {
      setBusy(null);
    }
  };

  const toggleSelected = (id: string) => {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : current.length >= MAX_COMPARE
          ? current
          : [...current, id],
    );
  };

  if (loading) return <Loading label="Loading scenarios" />;

  const selectedScenarios = scenarios.filter((scenario) => selected.includes(scenario.id));

  return (
    <>
      <PageHeader title="Scenarios">
        <Link href="/optimize">
          <Button variant="primary">New scenario</Button>
        </Link>
      </PageHeader>

      {error && (
        <div className="mb-4">
          <Alert tone="loss" title="Request failed">
            {error}
          </Alert>
        </div>
      )}

      <Panel title={`Scenarios (${scenarios.length})`}>
        {scenarios.length === 0 ? (
          <EmptyState>
            No scenarios yet. Build one on the <Link href="/optimize" className="text-accent">Optimize</Link> screen.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <TH>Compare</TH>
                <TH>Name</TH>
                <TH>Objective</TH>
                <TH align="right">Carbon price</TH>
                <TH>Status</TH>
                <TH align="right">Jobs</TH>
                <TH>Snapshot</TH>
                <TH>Created</TH>
                <TH>Actions</TH>
              </tr>
            </thead>
            <tbody>
              {scenarios.map((scenario) => {
                const hasResult = scenario.status === "optimized" || results[scenario.id];
                return (
                  <tr key={scenario.id}>
                    <TD>
                      <input
                        type="checkbox"
                        aria-label={`Compare ${scenario.name}`}
                        className="accent-[var(--color-accent)]"
                        checked={selected.includes(scenario.id)}
                        onChange={() => toggleSelected(scenario.id)}
                      />
                    </TD>
                    <TD>
                      <span className="block text-ink">{scenario.name}</span>
                      <span className="tnum font-mono text-[11px] text-ink-faint">
                        {shortId(scenario.id)}
                      </span>
                    </TD>
                    <TD>{scenario.objective}</TD>
                    <TD align="right" numeric>
                      {scenario.carbon_price_usd_per_tco2e > 0
                        ? formatMoney(scenario.carbon_price_usd_per_tco2e)
                        : "—"}
                    </TD>
                    <TD>
                      <Badge tone={statusTone(scenario.status)}>{scenario.status}</Badge>
                    </TD>
                    <TD align="right" numeric>
                      {scenario.workloads.length}
                    </TD>
                    <TD numeric>{shortChecksum(scenario.snapshot_checksum)}</TD>
                    <TD>{formatDateTime(scenario.created_at)}</TD>
                    <TD>
                      <div className="flex flex-wrap gap-1">
                        <Button
                          variant="primary"
                          onClick={() => run(scenario)}
                          disabled={busy === scenario.id}
                        >
                          {busy === scenario.id ? "…" : "Run"}
                        </Button>
                        {hasResult && (
                          <>
                            <Button onClick={() => loadResults(scenario)}>Results</Button>
                            <a
                              href={exportUrl(scenario.id, "csv")}
                              className="rounded-[3px] px-2.5 py-1.5 text-xs text-ink-muted hover:bg-sunken hover:text-ink"
                            >
                              CSV
                            </a>
                            <a
                              href={exportUrl(scenario.id, "json")}
                              className="rounded-[3px] px-2.5 py-1.5 text-xs text-ink-muted hover:bg-sunken hover:text-ink"
                            >
                              JSON
                            </a>
                          </>
                        )}
                      </div>
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>

      <div className="mt-8">
        <Panel
          title="Comparison"
          description={`Select up to ${MAX_COMPARE} scenarios. Every figure comes from a solver run.`}
        >
          {selectedScenarios.length < 2 ? (
            <EmptyState>Select at least two scenarios to compare them.</EmptyState>
          ) : (
            <Table>
              <thead>
                <tr>
                  <TH>Scenario</TH>
                  <TH>Objective</TH>
                  <TH align="right">Optimized cost</TH>
                  <TH align="right">Baseline cost</TH>
                  <TH align="right">Saving</TH>
                  <TH align="right">Optimized tCO2e</TH>
                  <TH align="right">Emissions change</TH>
                  <TH align="right">Solve</TH>
                </tr>
              </thead>
              <tbody>
                {selectedScenarios.map((scenario) => {
                  const result = results[scenario.id];
                  if (!result) {
                    return (
                      <tr key={scenario.id}>
                        <TD>{scenario.name}</TD>
                        <TD colSpan={7}>
                          <span className="text-xs text-ink-faint">
                            No result loaded — run or open this scenario.
                          </span>
                        </TD>
                      </tr>
                    );
                  }
                  return (
                    <tr key={scenario.id}>
                      <TD>{scenario.name}</TD>
                      <TD>{result.objective_mode}</TD>
                      <TD align="right" numeric>
                        {formatMoney(result.total_cost_usd)}
                      </TD>
                      <TD align="right" numeric>
                        {formatMoney(result.baseline_total_cost_usd)}
                      </TD>
                      <TD
                        align="right"
                        numeric
                        className={
                          result.cost_savings_pct !== null && result.cost_savings_pct < 0
                            ? "text-loss"
                            : "text-gain"
                        }
                      >
                        {formatPercent(result.cost_savings_pct)}
                      </TD>
                      <TD align="right" numeric>
                        {formatNumber(result.total_emissions_tco2e, 2)}
                      </TD>
                      <TD
                        align="right"
                        numeric
                        className={
                          result.emissions_reduction_pct !== null &&
                          result.emissions_reduction_pct < 0
                            ? "text-loss"
                            : "text-gain"
                        }
                      >
                        {formatPercent(result.emissions_reduction_pct)}
                      </TD>
                      <TD align="right" numeric>
                        {formatNumber(result.diagnostics.solve_seconds * 1000, 1)} ms
                      </TD>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Panel>
      </div>
    </>
  );
}
