"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AllocationGrid } from "@/components/AllocationGrid";
import { HourlyChart } from "@/components/HourlyChart";
import { ResultDetails, ResultHeadline } from "@/components/ResultSummary";
import { TradeoffScatter } from "@/components/TradeoffScatter";
import { WindowPicker } from "@/components/WindowPicker";
import {
  Alert,
  Button,
  Disclosure,
  EmptyState,
  Field,
  Input,
  Loading,
  PageHeader,
  Select,
  Step,
  Table,
  TD,
  TH,
} from "@/components/ui";
import {
  createScenario,
  exploreTradeoff,
  getResults,
  listDatasets,
  listFacilities,
  listScenarios,
  optimizeScenario,
} from "@/lib/api";
import { formatMoney, formatNumber, metricLabel, shortChecksum } from "@/lib/format";
import type {
  Dataset,
  Facility,
  ObjectiveMode,
  OptimizationResult,
  Scenario,
  TradeoffCurve,
} from "@/lib/types";

const DEFAULT_CARBON_PRICES = [0, 25, 50, 100, 200, 400];
const FALLBACK_HORIZON = 24;

type DraftWorkload = {
  job_id: string;
  energy_mwh: number;
  max_mw: number;
  release_hour: number;
  deadline_hour: number;
};

const BLANK_WORKLOAD: DraftWorkload = {
  job_id: "",
  energy_mwh: 0,
  max_mw: 0,
  release_hour: 0,
  deadline_hour: 23,
};

export default function OptimizePage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [facilityId, setFacilityId] = useState("");
  const [datasetIds, setDatasetIds] = useState<string[]>([]);
  const [name, setName] = useState("Cost optimization");
  const [objective, setObjective] = useState<ObjectiveMode>("cost");
  const [carbonPrice, setCarbonPrice] = useState(80);
  const [workloads, setWorkloads] = useState<DraftWorkload[]>([]);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [resultName, setResultName] = useState<string | null>(null);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [curve, setCurve] = useState<TradeoffCurve | null>(null);
  const [sweeping, setSweeping] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [facilityList, datasetList, scenarioList] = await Promise.all([
          listFacilities(),
          listDatasets(),
          listScenarios(),
        ]);
        setFacilities(facilityList);
        setDatasets(datasetList);
        setScenarios(scenarioList);

        if (facilityList.length > 0) setFacilityId(facilityList[0].id);
        setDatasetIds(datasetList.map((dataset) => dataset.id));

        // Land on the most recent result and populate the form from it, so the screen
        // shows a coherent scenario rather than a result above an empty form.
        const latest = scenarioList.find((scenario) => scenario.status === "optimized");
        if (latest) {
          setScenarioId(latest.id);
          setResultName(latest.name);
          setName(latest.name);
          setObjective(latest.objective as ObjectiveMode);
          if (latest.carbon_price_usd_per_tco2e > 0) {
            setCarbonPrice(latest.carbon_price_usd_per_tco2e);
          }
          setFacilityId(latest.facility_id);
          if (latest.dataset_ids.length > 0) setDatasetIds(latest.dataset_ids);
          setWorkloads(
            latest.workloads.map((workload) => ({
              job_id: workload.job_id,
              energy_mwh: workload.energy_mwh,
              max_mw: workload.max_mw,
              release_hour: workload.release_hour,
              deadline_hour: workload.deadline_hour,
            })),
          );
          try {
            setResult(await getResults(latest.id));
          } catch {
            setResult(null);
          }
        }
      } catch (error) {
        setLoadError(error instanceof Error ? error.message : "Could not load data");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selectedFacility = useMemo(
    () => facilities.find((facility) => facility.id === facilityId) ?? null,
    [facilities, facilityId],
  );

  const selectedDatasets = useMemo(
    () => datasets.filter((dataset) => datasetIds.includes(dataset.id)),
    [datasets, datasetIds],
  );

  /** The horizon the API will actually use: the overlap of the selected series. */
  const horizonHours = useMemo(() => {
    const lengths = selectedDatasets.flatMap((dataset) =>
      dataset.series.map((series) => series.hours),
    );
    return lengths.length > 0 ? Math.min(...lengths) : FALLBACK_HORIZON;
  }, [selectedDatasets]);

  const metrics = useMemo(
    () => [...new Set(selectedDatasets.flatMap((dataset) => dataset.metrics))].sort(),
    [selectedDatasets],
  );

  /**
   * Clamp every window to the current horizon.
   *
   * Done in the handlers that change the horizon rather than in an effect, because an
   * effect would re-render on every dataset toggle for a value we can compute directly.
   */
  const clampToHorizon = (items: DraftWorkload[], hours: number) =>
    items.map((workload) => ({
      ...workload,
      release_hour: Math.min(workload.release_hour, hours - 1),
      deadline_hour: Math.min(workload.deadline_hour, hours - 1),
    }));

  const toggleDataset = (id: string, checked: boolean) => {
    const next = checked
      ? [...datasetIds, id]
      : datasetIds.filter((item) => item !== id);
    setDatasetIds(next);

    const lengths = datasets
      .filter((dataset) => next.includes(dataset.id))
      .flatMap((dataset) => dataset.series.map((series) => series.hours));
    const nextHorizon = lengths.length > 0 ? Math.min(...lengths) : FALLBACK_HORIZON;
    setWorkloads((current) => clampToHorizon(current, nextHorizon));
  };

  const updateWorkload = (index: number, patch: Partial<DraftWorkload>) => {
    setWorkloads((current) =>
      current.map((workload, position) =>
        position === index ? { ...workload, ...patch } : workload,
      ),
    );
  };

  const run = useCallback(async () => {
    setRunning(true);
    setRunError(null);
    setCurve(null);
    try {
      const scenario = await createScenario({
        facility_id: facilityId,
        name,
        objective,
        carbon_price_usd_per_tco2e: objective === "balanced" ? carbonPrice : 0,
        dataset_ids: datasetIds,
        // Defensive: a window outside the horizon would be rejected by the API.
        workloads: clampToHorizon(workloads, horizonHours),
      });
      const outcome = await optimizeScenario(scenario.id);
      setScenarioId(scenario.id);
      setResultName(scenario.name);
      setResult(outcome);
      setScenarios(await listScenarios());
    } catch (error) {
      setResult(null);
      setRunError(error instanceof Error ? error.message : "Optimization failed");
    } finally {
      setRunning(false);
    }
  }, [carbonPrice, datasetIds, facilityId, horizonHours, name, objective, workloads]);

  const sweep = useCallback(async () => {
    if (!scenarioId) return;
    setSweeping(true);
    try {
      setCurve(await exploreTradeoff(scenarioId, DEFAULT_CARBON_PRICES));
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "Trade-off sweep failed");
    } finally {
      setSweeping(false);
    }
  }, [scenarioId]);

  if (loading) return <Loading label="Loading" />;

  const configured = facilities.length > 0 && datasets.length > 0;
  const canRun =
    configured &&
    datasetIds.length > 0 &&
    workloads.length > 0 &&
    workloads.every((workload) => workload.job_id.trim() && workload.energy_mwh > 0);

  return (
    <>
      <PageHeader
        title="Optimize"
        purpose="Choose the inputs, set the constraints, and see what the solver can save."
      >
        <Button variant="primary" onClick={run} disabled={!canRun || running}>
          {running ? "Solving…" : "Run optimization"}
        </Button>
      </PageHeader>

      {loadError && (
        <div className="mb-4">
          <Alert tone="loss" title="Could not reach the API">
            {loadError}
          </Alert>
        </div>
      )}

      {!configured && !loadError && (
        <div className="mb-4">
          <Alert tone="warn" title="No facility or data yet">
            GridShift needs a facility and an hourly dataset before it can solve anything.{" "}
            <Link href="/data" className="text-accent underline">
              Set them up on the Data screen
            </Link>
            .
          </Alert>
        </div>
      )}

      {/* Context: what we are working with, in one line. */}
      <div className="mb-6 flex flex-wrap items-center gap-x-6 gap-y-1 border-y border-line py-2 text-xs text-ink-muted">
        <span>
          Facility{" "}
          <span className="text-ink">{selectedFacility?.name ?? "—"}</span>
        </span>
        <span>
          Data{" "}
          <span className="tnum font-mono text-ink">{horizonHours}h</span> ·{" "}
          {metrics.length > 0 ? metrics.map(metricLabel).join(", ") : "—"}
        </span>
        <span>
          Scenarios <span className="tnum font-mono text-ink">{scenarios.length}</span>
        </span>
        {selectedFacility && (
          <span>
            Capacity{" "}
            <span className="tnum font-mono text-ink">
              {formatNumber(selectedFacility.capacity_mw, 0)} MW
            </span>
          </span>
        )}
      </div>

      <div className="grid gap-10 lg:grid-cols-[380px_minmax(0,1fr)]">
        {/* ---- 1. Inputs ---- */}
        <div className="flex flex-col gap-6">
          <Step
            index={1}
            title="Inputs"
            purpose="Which facility, and which data describes it."
          >
            <div className="flex flex-col gap-3">
              <Field label="Facility">
                <Select
                  value={facilityId}
                  onChange={(event) => setFacilityId(event.target.value)}
                >
                  {facilities.map((facility) => (
                    <option key={facility.id} value={facility.id}>
                      {facility.name} · {facility.capacity_mw} MW
                    </option>
                  ))}
                </Select>
              </Field>

              {datasets.length === 0 ? (
                <EmptyState>No datasets uploaded.</EmptyState>
              ) : (
                <ul className="flex flex-col gap-1.5">
                  {datasets.map((dataset) => (
                    <li key={dataset.id}>
                      <label className="flex cursor-pointer items-start gap-2 text-sm">
                        <input
                          type="checkbox"
                          className="mt-0.5 accent-[var(--color-accent)]"
                          checked={datasetIds.includes(dataset.id)}
                          onChange={(event) =>
                            toggleDataset(dataset.id, event.target.checked)
                          }
                        />
                        <span className="text-xs">
                          <span className="text-ink">
                            {dataset.series[0]?.hours ?? 0}h ·{" "}
                            {dataset.metrics.map(metricLabel).join(", ")}
                          </span>
                          <span className="tnum ml-2 font-mono text-ink-faint">
                            {shortChecksum(dataset.checksum, 8)}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-ink-faint">
                Prices and carbon intensity are both required. Manage data on the{" "}
                <Link href="/data" className="text-accent">
                  Data
                </Link>{" "}
                screen.
              </p>
            </div>
          </Step>

          {/* ---- 2. Workloads ---- */}
          <Step
            index={2}
            title="Workloads"
            purpose="What must run, and how much freedom it has."
            action={
              <Button
                variant="ghost"
                onClick={() =>
                  setWorkloads((current) => [
                    ...current,
                    {
                      ...BLANK_WORKLOAD,
                      deadline_hour: Math.max(23, horizonHours - 1),
                    },
                  ])
                }
              >
                Add workload
              </Button>
            }
          >
            {workloads.length === 0 ? (
              <EmptyState>
                No workloads yet. Add one to give the solver something to schedule.
              </EmptyState>
            ) : (
              <div className="flex flex-col gap-4">
                {workloads.map((workload, index) => (
                  <div key={index} className="rounded-[3px] border border-line p-3">
                    <div className="mb-2 flex items-center gap-2">
                      <Input
                        aria-label={`Workload ${index + 1} name`}
                        value={workload.job_id}
                        placeholder="model-training"
                        onChange={(event) =>
                          updateWorkload(index, { job_id: event.target.value })
                        }
                      />
                      <Button
                        variant="ghost"
                        aria-label={`Remove workload ${index + 1}`}
                        onClick={() =>
                          setWorkloads((current) =>
                            current.filter((_, position) => position !== index),
                          )
                        }
                      >
                        Remove
                      </Button>
                    </div>

                    <div className="mb-2 grid grid-cols-2 gap-2">
                      <Field label="Energy (MWh)">
                        <Input
                          type="number"
                          min={0}
                          value={workload.energy_mwh}
                          onChange={(event) =>
                            updateWorkload(index, { energy_mwh: Number(event.target.value) })
                          }
                        />
                      </Field>
                      <Field label="Max power (MW)">
                        <Input
                          type="number"
                          min={0}
                          value={workload.max_mw}
                          onChange={(event) =>
                            updateWorkload(index, { max_mw: Number(event.target.value) })
                          }
                        />
                      </Field>
                    </div>

                    <WindowPicker
                      horizonHours={horizonHours}
                      release_hour={workload.release_hour}
                      deadline_hour={workload.deadline_hour}
                      onChange={(next) => updateWorkload(index, next)}
                    />
                  </div>
                ))}
              </div>
            )}
          </Step>

          {/* ---- 3. Objective ---- */}
          <Step
            index={3}
            title="Objective"
            purpose="What the solver should minimize."
          >
            <div className="flex flex-col gap-3">
              <Field label="Scenario name">
                <Input value={name} onChange={(event) => setName(event.target.value)} />
              </Field>
              <Field label="Mode">
                <Select
                  value={objective}
                  onChange={(event) => setObjective(event.target.value as ObjectiveMode)}
                >
                  <option value="cost">Minimize cost</option>
                  <option value="emissions">Minimize emissions</option>
                  <option value="balanced">Balanced (price the carbon)</option>
                </Select>
              </Field>
              {objective === "balanced" && (
                <Field
                  label="Carbon price (USD / tCO₂e)"
                  hint="Priced before combining, so dollars are never added to tonnes."
                >
                  <Input
                    type="number"
                    min={0}
                    value={carbonPrice}
                    onChange={(event) => setCarbonPrice(Number(event.target.value))}
                  />
                </Field>
              )}
            </div>
          </Step>
        </div>

        {/* ---- Result ---- */}
        <div className="flex min-w-0 flex-col gap-6">
          {runError && (
            <Alert tone="loss" title="Optimization rejected">
              {runError}
            </Alert>
          )}

          {!result && !runError && (
            <div className="border-t border-line pt-4">
              <EmptyState>
                Run an optimization to see the schedule, what it saves, and where every
                hour of load lands. Every figure comes from the solver.
              </EmptyState>
            </div>
          )}

          {result && (
            <>
              <section className="border-t border-line pt-4">
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-3">
                  <h2 className="text-sm font-medium text-ink">Result</h2>
                  {resultName && (
                    <span className="text-xs text-ink-faint">
                      {resultName}
                      {scenarios.length > 0 && (
                        <>
                          {" · "}
                          <Link href="/scenarios" className="text-accent">
                            all scenarios
                          </Link>
                        </>
                      )}
                    </span>
                  )}
                </div>
                <ResultHeadline result={result} />
              </section>

              {result.hourly.length > 0 && (
                <section className="border-t border-line pt-4">
                  <h2 className="mb-1 text-sm font-medium text-ink">Schedule</h2>
                  <p className="mb-3 text-xs text-ink-muted">
                    Flexible load lands in the cheapest or cleanest hours the constraints
                    allow. The dashed line is the price that drove it.
                  </p>
                  <HourlyChart points={result.hourly} />
                  {Object.keys(result.job_allocations).length > 0 && (
                    <div className="mt-5">
                      <AllocationGrid
                        allocations={result.job_allocations}
                        workloads={workloads}
                        hourly={result.hourly}
                      />
                    </div>
                  )}
                </section>
              )}

              {result.hourly.length > 0 && (
                <Disclosure
                  title="Hourly detail"
                  summary={`${result.hourly.length} hours`}
                >
                  <div className="max-h-[420px] overflow-y-auto">
                    <Table>
                      <thead className="sticky top-0 bg-canvas">
                        <tr>
                          <TH>Hr</TH>
                          <TH align="right">Price</TH>
                          <TH align="right">Carbon</TH>
                          <TH align="right">Fixed</TH>
                          <TH align="right">Flexible</TH>
                          <TH align="right">Total</TH>
                          <TH align="right">Baseline</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {result.hourly.map((point) => (
                          <tr key={point.hour}>
                            <TD numeric>{point.hour}</TD>
                            <TD align="right" numeric>
                              {formatMoney(point.price_usd_per_mwh, true)}
                            </TD>
                            <TD align="right" numeric>
                              {formatNumber(point.carbon_tco2e_per_mwh, 3)}
                            </TD>
                            <TD align="right" numeric>
                              {formatNumber(point.baseline_load_mwh)}
                            </TD>
                            <TD align="right" numeric>
                              {formatNumber(point.optimized_flexible_mwh)}
                            </TD>
                            <TD align="right" numeric>
                              {formatNumber(point.optimized_consumption_mwh)}
                            </TD>
                            <TD align="right" numeric>
                              {formatNumber(point.baseline_consumption_mwh)}
                            </TD>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </Disclosure>
              )}

              {result.hourly.length > 0 && (
                <Disclosure title="Solver and assumptions">
                  <ResultDetails result={result} />
                </Disclosure>
              )}

              {result.hourly.length > 0 && (
                <Disclosure
                  title="Carbon price trade-off"
                  summary={curve ? `${curve.points.length} prices solved` : undefined}
                >
                  <p className="mb-3 text-xs text-ink-muted">
                    Each point is a full solve at a different carbon price, so the curve is
                    the model&apos;s own frontier. Nothing is saved.
                  </p>
                  {curve ? (
                    <TradeoffScatter curve={curve} />
                  ) : (
                    <Button onClick={sweep} disabled={sweeping || !scenarioId}>
                      {sweeping ? "Solving…" : "Solve across carbon prices"}
                    </Button>
                  )}
                </Disclosure>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
