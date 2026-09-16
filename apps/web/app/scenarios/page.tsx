"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { TradeoffScatter } from "@/components/TradeoffScatter";
import {
  Alert,
  Badge,
  Button,
  Disclosure,
  EmptyState,
  Loading,
  PageHeader,
  Table,
  TD,
  TH,
} from "@/components/ui";
import {
  exportUrl,
  exploreTradeoff,
  getResults,
  listScenarios,
  optimizeScenario,
} from "@/lib/api";
import {
  formatDateTime,
  formatMoney,
  formatNumber,
  formatPercent,
  shortChecksum,
  statusTone,
} from "@/lib/format";
import type { OptimizationResult, Scenario, TradeoffCurve } from "@/lib/types";

const DEFAULT_CARBON_PRICES = [0, 25, 50, 100, 200, 400];

export default function ScenariosPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [results, setResults] = useState<Record<string, OptimizationResult>>({});
  const [selected, setSelected] = useState<string[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [curve, setCurve] = useState<TradeoffCurve | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setScenarios(await listScenarios());
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const list = await listScenarios();
        setScenarios(list);

        // Pull the existing results in the same pass so the table shows real figures on
        // arrival rather than dashes that fill in one request at a time.
        const optimized = list.filter((scenario) => scenario.status === "optimized");
        const loaded = await Promise.all(
          optimized.map(async (scenario) => {
            try {
              return [scenario.id, await getResults(scenario.id)] as const;
            } catch {
              return null;
            }
          }),
        );
        setResults(
          Object.fromEntries(
            loaded.filter((entry): entry is readonly [string, OptimizationResult] =>
              entry !== null,
            ),
          ),
        );
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Could not load scenarios");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const loadResult = useCallback(async (scenario: Scenario) => {
    try {
      const result = await getResults(scenario.id);
      setResults((current) => ({ ...current, [scenario.id]: result }));
    } catch {
      // A scenario can exist without a result yet; the row still shows its status.
    }
  }, []);

  const open = async (scenario: Scenario) => {
    setCurve(null);
    setError(null);
    if (openId === scenario.id) {
      setOpenId(null);
      return;
    }
    setOpenId(scenario.id);
    if (!results[scenario.id]) await loadResult(scenario);
  };

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

  const toggle = (id: string) => {
    setSelected((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : current.length >= 4
          ? current
          : [...current, id],
    );
  };

  const openScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === openId) ?? null,
    [scenarios, openId],
  );

  if (loading) return <Loading label="Loading scenarios" />;

  const compared = scenarios.filter((scenario) => selected.includes(scenario.id));

  return (
    <>
      <PageHeader
        title="Scenarios"
        purpose="Every run you have saved, and how they compare."
      >
        <Link href="/">
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

      <section className="border-t border-line pt-4">
        {scenarios.length === 0 ? (
          <EmptyState>
            No scenarios yet. Build one on the{" "}
            <Link href="/" className="text-accent">
              Optimize
            </Link>{" "}
            screen.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <TH>Compare</TH>
                <TH>Scenario</TH>
                <TH>Objective</TH>
                <TH align="right">Cost</TH>
                <TH align="right">Saving</TH>
                <TH align="right">Emissions</TH>
                <TH>Status</TH>
                <TH />
              </tr>
            </thead>
            <tbody>
              {scenarios.map((scenario) => {
                const result = results[scenario.id];
                const isOpen = openId === scenario.id;
                return (
                  <tr key={scenario.id} className={isOpen ? "bg-sunken" : undefined}>
                    <TD>
                      <input
                        type="checkbox"
                        aria-label={`Compare ${scenario.name}`}
                        className="accent-[var(--color-accent)]"
                        checked={selected.includes(scenario.id)}
                        onChange={() => toggle(scenario.id)}
                      />
                    </TD>
                    <TD>
                      <button
                        type="button"
                        onClick={() => open(scenario)}
                        className="text-left text-ink hover:text-accent"
                      >
                        {scenario.name}
                      </button>
                      <span className="tnum block font-mono text-[11px] text-ink-faint">
                        {scenario.workloads.length} job
                        {scenario.workloads.length === 1 ? "" : "s"} ·{" "}
                        {shortChecksum(scenario.snapshot_checksum, 8)}
                      </span>
                    </TD>
                    <TD>
                      {scenario.objective}
                      {scenario.carbon_price_usd_per_tco2e > 0 && (
                        <span className="tnum block font-mono text-[11px] text-ink-faint">
                          @ {formatMoney(scenario.carbon_price_usd_per_tco2e)}/t
                        </span>
                      )}
                    </TD>
                    <TD align="right" numeric>
                      {result ? formatMoney(result.total_cost_usd) : "—"}
                    </TD>
                    <TD
                      align="right"
                      numeric
                      className={
                        result?.cost_savings_pct != null && result.cost_savings_pct < 0
                          ? "text-loss"
                          : undefined
                      }
                    >
                      {result ? formatPercent(result.cost_savings_pct) : "—"}
                    </TD>
                    <TD align="right" numeric>
                      {result ? formatNumber(result.total_emissions_tco2e, 0) : "—"}
                    </TD>
                    <TD>
                      <Badge tone={statusTone(scenario.status)}>{scenario.status}</Badge>
                    </TD>
                    <TD align="right">
                      <Button
                        variant={isOpen ? "secondary" : "ghost"}
                        onClick={() => open(scenario)}
                      >
                        {isOpen ? "Close" : "Details"}
                      </Button>
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </section>

      {/* --- One scenario in full ------------------------------------------------ */}
      {openScenario && results[openScenario.id] && (
        <section className="mt-8 border-t border-line pt-4">
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="text-sm font-medium text-ink">{openScenario.name}</h2>
            <div className="flex items-center gap-2">
              <a href={exportUrl(openScenario.id, "csv")}>
                <Button>Download CSV</Button>
              </a>
              <a href={exportUrl(openScenario.id, "json")}>
                <Button>Download JSON</Button>
              </a>
              <Button
                variant="primary"
                onClick={() => run(openScenario)}
                disabled={busy === openScenario.id}
              >
                {busy === openScenario.id ? "Solving…" : "Re-run"}
              </Button>
            </div>
          </div>

          <Table>
            <thead>
              <tr>
                <TH>Measure</TH>
                <TH align="right">Optimized</TH>
                <TH align="right">Baseline</TH>
                <TH align="right">Change</TH>
              </tr>
            </thead>
            <tbody>
              <tr>
                <TD>Cost</TD>
                <TD align="right" numeric>
                  {formatMoney(results[openScenario.id].total_cost_usd)}
                </TD>
                <TD align="right" numeric>
                  {formatMoney(results[openScenario.id].baseline_total_cost_usd)}
                </TD>
                <TD align="right" numeric>
                  {formatPercent(results[openScenario.id].cost_savings_pct)}
                </TD>
              </tr>
              <tr>
                <TD>Emissions (tCO₂e)</TD>
                <TD align="right" numeric>
                  {formatNumber(results[openScenario.id].total_emissions_tco2e, 2)}
                </TD>
                <TD align="right" numeric>
                  {formatNumber(
                    results[openScenario.id].baseline_total_emissions_tco2e,
                    2,
                  )}
                </TD>
                <TD align="right" numeric>
                  {formatPercent(results[openScenario.id].emissions_reduction_pct)}
                </TD>
              </tr>
              <tr>
                <TD>Horizon</TD>
                <TD align="right" numeric colSpan={3}>
                  {results[openScenario.id].hourly.length} hours · solved in{" "}
                  {formatNumber(
                    results[openScenario.id].diagnostics.solve_seconds * 1000,
                    1,
                  )}{" "}
                  ms
                </TD>
              </tr>
            </tbody>
          </Table>

          <div className="mt-4">
            <Disclosure title="Carbon price trade-off">
              <p className="mb-3 text-xs text-ink-muted">
                Each point is a full solve at a different carbon price, so the curve is the
                model&apos;s own frontier. Nothing is saved.
              </p>
              {curve ? (
                <TradeoffScatter curve={curve} />
              ) : (
                <Button
                  onClick={async () => {
                    try {
                      setCurve(
                        await exploreTradeoff(openScenario.id, DEFAULT_CARBON_PRICES),
                      );
                    } catch (sweepError) {
                      setError(
                        sweepError instanceof Error ? sweepError.message : "Sweep failed",
                      );
                    }
                  }}
                >
                  Solve across carbon prices
                </Button>
              )}
            </Disclosure>
          </div>
        </section>
      )}

      {/* --- Comparison ---------------------------------------------------------- */}
      <section className="mt-8 border-t border-line pt-4">
        <h2 className="mb-1 text-sm font-medium text-ink">Comparison</h2>
        <p className="mb-3 text-xs text-ink-muted">
          Select two to four scenarios above. Every figure comes from a solver run.
        </p>

        {compared.length < 2 ? (
          <EmptyState>Select at least two scenarios.</EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <TH>Scenario</TH>
                <TH>Objective</TH>
                <TH align="right">Cost</TH>
                <TH align="right">Saving</TH>
                <TH align="right">Emissions</TH>
                <TH align="right">Change</TH>
              </tr>
            </thead>
            <tbody>
              {compared.map((scenario) => {
                const result = results[scenario.id];
                return (
                  <tr key={scenario.id}>
                    <TD>{scenario.name}</TD>
                    <TD>
                      {result?.objective_mode ?? scenario.objective}
                      {scenario.carbon_price_usd_per_tco2e > 0 &&
                        ` @ ${formatMoney(scenario.carbon_price_usd_per_tco2e)}`}
                    </TD>
                    <TD align="right" numeric>
                      {result ? formatMoney(result.total_cost_usd) : "—"}
                    </TD>
                    <TD align="right" numeric>
                      {result ? formatPercent(result.cost_savings_pct) : "—"}
                    </TD>
                    <TD align="right" numeric>
                      {result ? formatNumber(result.total_emissions_tco2e, 1) : "—"}
                    </TD>
                    <TD align="right" numeric>
                      {result ? formatPercent(result.emissions_reduction_pct) : "—"}
                    </TD>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
        {compared.length >= 2 && (
          <p className="mt-3 text-[11px] text-ink-faint">
            Created {formatDateTime(compared[0].created_at)} onwards · values are modelled,
            not measured.
          </p>
        )}
      </section>
    </>
  );
}
