"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { AllocationGrid } from "@/components/AllocationGrid";
import { HourlyChart } from "@/components/HourlyChart";
import { ResultSummary } from "@/components/ResultSummary";
import { TradeoffScatter } from "@/components/TradeoffScatter";
import {
  Alert,
  Button,
  EmptyState,
  Field,
  Input,
  Loading,
  Panel,
  PageHeader,
  Select,
  Table,
  TD,
  TH,
} from "@/components/ui";
import {
  createScenario,
  exploreTradeoff,
  listDatasets,
  listFacilities,
  optimizeScenario,
} from "@/lib/api";
import {
  formatMoney,
  formatNumber,
  metricLabel,
  shortChecksum,
  shortId,
} from "@/lib/format";
import type {
  Dataset,
  Facility,
  ObjectiveMode,
  OptimizationResult,
  TradeoffCurve,
  Workload,
} from "@/lib/types";

const DEFAULT_CARBON_PRICES = [0, 25, 50, 100, 200, 400];

type DraftWorkload = Omit<Workload, "id">;

const EMPTY_WORKLOAD: DraftWorkload = {
  job_id: "",
  energy_mwh: 0,
  release_hour: 0,
  deadline_hour: 23,
  max_mw: 0,
};

export default function OptimizePage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [facilityId, setFacilityId] = useState("");
  const [datasetIds, setDatasetIds] = useState<string[]>([]);
  const [name, setName] = useState("Cost optimization");
  const [objective, setObjective] = useState<ObjectiveMode>("cost");
  const [carbonPrice, setCarbonPrice] = useState(50);
  const [workloads, setWorkloads] = useState<DraftWorkload[]>([
    { job_id: "batch-1", energy_mwh: 120, release_hour: 0, deadline_hour: 23, max_mw: 20 },
  ]);

  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [scenarioId, setScenarioId] = useState<string | null>(null);
  const [curve, setCurve] = useState<TradeoffCurve | null>(null);
  const [sweeping, setSweeping] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [facilityList, datasetList] = await Promise.all([
          listFacilities(),
          listDatasets(),
        ]);
        if (cancelled) return;
        setFacilities(facilityList);
        setDatasets(datasetList);
        if (facilityList.length > 0) setFacilityId(facilityList[0].id);
        setDatasetIds(datasetList.map((dataset) => dataset.id));
      } catch (error) {
        if (!cancelled) setLoadError(error instanceof Error ? error.message : "Load failed");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedFacility = useMemo(
    () => facilities.find((facility) => facility.id === facilityId) ?? null,
    [facilities, facilityId],
  );

  const coverage = useMemo(() => {
    const chosen = datasets.filter((dataset) => datasetIds.includes(dataset.id));
    const metrics = new Set(chosen.flatMap((dataset) => dataset.metrics));
    const hours = chosen.length
      ? Math.min(...chosen.flatMap((d) => d.series.map((s) => s.hours)))
      : 0;
    return { metrics: [...metrics].sort(), hours, count: chosen.length };
  }, [datasets, datasetIds]);

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
        workloads,
      });
      const outcome = await optimizeScenario(scenario.id);
      setScenarioId(scenario.id);
      setResult(outcome);
    } catch (error) {
      setResult(null);
      setScenarioId(null);
      setRunError(error instanceof Error ? error.message : "Optimization failed");
    } finally {
      setRunning(false);
    }
  }, [carbonPrice, datasetIds, facilityId, name, objective, workloads]);

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

  if (loading) return <Loading label="Loading facilities and datasets" />;

  const ready = facilities.length > 0 && datasetIds.length > 0 && workloads.length > 0;

  return (
    <>
      <PageHeader title="Optimize">
        <Button
          variant="primary"
          onClick={run}
          disabled={!ready || running || workloads.some((w) => !w.job_id)}
        >
          {running ? "Solving…" : "Run optimization"}
        </Button>
      </PageHeader>

      {loadError && (
        <Alert tone="loss" title="Could not load inputs">
          {loadError}
        </Alert>
      )}

      {facilities.length === 0 && (
        <Alert tone="warn" title="No facility configured">
          Create a facility and upload an hourly dataset on the Data screen first.
        </Alert>
      )}

      <div className="grid gap-8 lg:grid-cols-[360px_minmax(0,1fr)]">
        {/* --- Inputs ------------------------------------------------------------- */}
        <div className="flex flex-col gap-6">
          <Panel title="Facility">
            <Field label="Facility">
              <Select
                id="facility"
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
            {selectedFacility && (
              <p className="mt-2 text-xs text-ink-faint">
                {selectedFacility.location_id} · {selectedFacility.timezone}
                {selectedFacility.latitude !== null && selectedFacility.longitude !== null
                  ? ` · ${selectedFacility.latitude.toFixed(2)}, ${selectedFacility.longitude.toFixed(2)}`
                  : ""}
              </p>
            )}
          </Panel>

          <Panel
            title="Input datasets"
            description="Prices and carbon intensity are both required."
          >
            {datasets.length === 0 ? (
              <EmptyState>No datasets uploaded yet.</EmptyState>
            ) : (
              <ul className="flex flex-col gap-2">
                {datasets.map((dataset) => (
                  <li key={dataset.id}>
                    <label className="flex cursor-pointer items-start gap-2 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1 accent-[var(--color-accent)]"
                        checked={datasetIds.includes(dataset.id)}
                        onChange={(event) =>
                          setDatasetIds((current) =>
                            event.target.checked
                              ? [...current, dataset.id]
                              : current.filter((id) => id !== dataset.id),
                          )
                        }
                      />
                      <span>
                        <span className="block text-ink">
                          {dataset.metrics.map(metricLabel).join(", ")}
                        </span>
                        <span className="block text-xs text-ink-faint">
                          {dataset.series[0]?.hours ?? 0} hrs · {dataset.rows_accepted} rows ·{" "}
                          {shortChecksum(dataset.checksum)}
                        </span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            {coverage.count > 0 && (
              <p className="mt-3 border-t border-line pt-2 text-xs text-ink-muted">
                Shared coverage: <span className="tnum font-mono">{coverage.hours}</span> hours ·{" "}
                {coverage.metrics.map(metricLabel).join(", ")}
              </p>
            )}
          </Panel>

          <Panel title="Objective">
            <div className="flex flex-col gap-3">
              <Field label="Scenario name">
                <Input
                  id="scenario-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field label="Mode">
                <Select
                  id="objective"
                  value={objective}
                  onChange={(event) => setObjective(event.target.value as ObjectiveMode)}
                >
                  <option value="cost">Minimize cost</option>
                  <option value="emissions">Minimize emissions</option>
                  <option value="balanced">Balanced (carbon price)</option>
                </Select>
              </Field>
              {objective === "balanced" && (
                <Field
                  label="Carbon price (USD / tCO2e)"
                  hint="Priced before combining, so dollars are never added to tonnes."
                >
                  <Input
                    id="carbon-price"
                    type="number"
                    min={0}
                    value={carbonPrice}
                    onChange={(event) => setCarbonPrice(Number(event.target.value))}
                  />
                </Field>
              )}
            </div>
          </Panel>

          <Panel
            title="Workloads"
            description="Hour offsets are relative to the start of the shared horizon."
            action={
              <Button
                variant="ghost"
                onClick={() => setWorkloads((current) => [...current, { ...EMPTY_WORKLOAD }])}
              >
                Add job
              </Button>
            }
          >
            <div className="flex flex-col gap-3">
              {workloads.map((workload, index) => (
                <fieldset
                  key={index}
                  className="grid grid-cols-2 gap-2 border-t border-line pt-3 first:border-t-0 first:pt-0"
                >
                  <Field label="Job id" className="col-span-2">
                    <Input
                      value={workload.job_id}
                      placeholder="batch-1"
                      onChange={(event) => updateWorkload(index, { job_id: event.target.value })}
                    />
                  </Field>
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
                  <Field label="Release hour">
                    <Input
                      type="number"
                      min={0}
                      value={workload.release_hour}
                      onChange={(event) =>
                        updateWorkload(index, { release_hour: Number(event.target.value) })
                      }
                    />
                  </Field>
                  <Field label="Deadline hour">
                    <Input
                      type="number"
                      min={0}
                      value={workload.deadline_hour}
                      onChange={(event) =>
                        updateWorkload(index, { deadline_hour: Number(event.target.value) })
                      }
                    />
                  </Field>
                  <div className="col-span-2">
                    <Button
                      variant="ghost"
                      onClick={() =>
                        setWorkloads((current) =>
                          current.filter((_, position) => position !== index),
                        )
                      }
                    >
                      Remove
                    </Button>
                  </div>
                </fieldset>
              ))}
            </div>
          </Panel>
        </div>

        {/* --- Results ------------------------------------------------------------ */}
        <div className="flex min-w-0 flex-col gap-6">
          {runError && (
            <Alert tone="loss" title="Optimization rejected">
              {runError}
            </Alert>
          )}

          {!result && !runError && (
            <Panel title="Result">
              <EmptyState>
                Configure the facility, datasets and workloads, then run the optimization.
                Every number shown will come from the solver.
              </EmptyState>
            </Panel>
          )}

          {result && (
            <>
              {scenarioId && (
                <p className="text-xs text-ink-faint">
                  Scenario <span className="tnum font-mono">{shortId(scenarioId)}</span>
                  {result.diagnostics.variables > 0
                    ? ` · ${formatNumber(result.diagnostics.variables, 0)} variables`
                    : ""}
                </p>
              )}

              <ResultSummary result={result} />

              {result.hourly.length > 0 && (
                <Panel
                  title="Hourly schedule"
                  description="Fixed load plus optimized flexible load, against the price that drove placement."
                >
                  <HourlyChart points={result.hourly} />
                </Panel>
              )}

              {Object.keys(result.job_allocations).length > 0 && (
                <Panel title="Workload placement">
                  <AllocationGrid
                    allocations={result.job_allocations}
                    workloads={workloads}
                    hourly={result.hourly}
                  />
                </Panel>
              )}

              {result.hourly.length > 0 && (
                <Panel
                  title="Trade-off frontier"
                  action={
                    <Button onClick={sweep} disabled={sweeping || !scenarioId}>
                      {sweeping ? "Sweeping…" : "Sweep carbon price"}
                    </Button>
                  }
                  description="Each point is a full solve at a different carbon price."
                >
                  {curve ? (
                    <TradeoffScatter curve={curve} />
                  ) : (
                    <EmptyState>
                      Run the sweep to see how cost and emissions trade off across carbon
                      prices.
                    </EmptyState>
                  )}
                </Panel>
              )}

              {result.hourly.length > 0 && (
                <Panel title="Hourly detail">
                  <div className="max-h-[420px] overflow-y-auto">
                    <Table>
                      <thead className="sticky top-0 bg-canvas">
                        <tr>
                          <TH>Hr</TH>
                          <TH align="right">Price</TH>
                          <TH align="right">Carbon</TH>
                          <TH align="right">Fixed</TH>
                          <TH align="right">Flex (opt)</TH>
                          <TH align="right">Total (opt)</TH>
                          <TH align="right">Total (base)</TH>
                          <TH align="right">Cost (opt)</TH>
                          <TH align="right">Cost (base)</TH>
                        </tr>
                      </thead>
                      <tbody>
                        {result.hourly.map((point) => (
                          <tr key={point.hour}>
                            <TD numeric>{String(point.hour).padStart(2, "0")}</TD>
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
                            <TD align="right" numeric>
                              {formatMoney(point.optimized_cost_usd)}
                            </TD>
                            <TD align="right" numeric>
                              {formatMoney(point.baseline_cost_usd)}
                            </TD>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </div>
                </Panel>
              )}
            </>
          )}
        </div>
      </div>
    </>
  );
}
