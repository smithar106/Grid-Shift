"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { HourlyChart } from "@/components/HourlyChart";
import { ResultSummary } from "@/components/ResultSummary";
import {
  Alert,
  Button,
  DefinitionList,
  EmptyState,
  Loading,
  PageHeader,
  Panel,
  Stat,
  Table,
  TD,
  TH,
} from "@/components/ui";
import { getResults, listDatasets, listFacilities, listScenarios } from "@/lib/api";
import {
  formatDateTime,
  formatInteger,
  formatNumber,
  metricLabel,
  shortChecksum,
} from "@/lib/format";
import type { Dataset, Facility, OptimizationResult, Scenario } from "@/lib/types";

export default function OverviewPage() {
  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [result, setResult] = useState<OptimizationResult | null>(null);
  const [resultScenario, setResultScenario] = useState<Scenario | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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

        const latest = scenarioList.find((scenario) => scenario.status === "optimized");
        if (latest) {
          setResultScenario(latest);
          try {
            setResult(await getResults(latest.id));
          } catch {
            // A scenario can be marked optimized while its result is unavailable; the
            // rest of the overview is still useful, so this is not a page-level error.
            setResult(null);
          }
        }
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Load failed");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <Loading label="Loading overview" />;

  const facility = facilities[0] ?? null;
  const totalHours = datasets.reduce(
    (sum, dataset) => sum + (dataset.series[0]?.hours ?? 0),
    0,
  );
  const metrics = [...new Set(datasets.flatMap((dataset) => dataset.metrics))].sort();

  const steps = [
    { done: facilities.length > 0, label: "Create a facility", href: "/data" },
    { done: datasets.length > 0, label: "Upload hourly price and carbon data", href: "/data" },
    { done: scenarios.length > 0, label: "Define a scenario with workloads", href: "/optimize" },
    {
      done: scenarios.some((scenario) => scenario.status === "optimized"),
      label: "Run the optimization",
      href: "/optimize",
    },
  ];
  const allDone = steps.every((step) => step.done);

  return (
    <>
      <PageHeader title="Overview" />

      {error && (
        <div className="mb-4">
          <Alert tone="loss" title="Could not reach the API">
            {error}
          </Alert>
        </div>
      )}

      <div className="flex flex-col gap-8">
        <Panel>
          <div className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Facilities" value={formatInteger(facilities.length)} />
            <Stat label="Datasets" value={formatInteger(datasets.length)} />
            <Stat label="Observed hours" value={formatInteger(totalHours)} />
            <Stat label="Scenarios" value={formatInteger(scenarios.length)} />
            <Stat
              label="Optimized"
              value={formatInteger(
                scenarios.filter((scenario) => scenario.status === "optimized").length,
              )}
            />
          </div>
        </Panel>

        {!allDone && (
          <Panel title="Getting started">
            <ol className="flex flex-col gap-1.5 text-sm">
              {steps.map((step) => (
                <li key={step.label} className="flex items-center gap-2">
                  <span className={step.done ? "text-gain" : "text-ink-faint"} aria-hidden>
                    {step.done ? "✓" : "○"}
                  </span>
                  {step.done ? (
                    <span className="text-ink-muted line-through">{step.label}</span>
                  ) : (
                    <Link href={step.href} className="text-ink hover:text-accent">
                      {step.label}
                    </Link>
                  )}
                </li>
              ))}
            </ol>
          </Panel>
        )}

        {facility && (
          <Panel
            title="Facility"
            action={
              <Link href="/data">
                <Button>Manage</Button>
              </Link>
            }
          >
            <DefinitionList
              items={[
                { term: "Name", value: facility.name },
                { term: "Location id", value: <span className="tnum font-mono">{facility.location_id}</span> },
                {
                  term: "Capacity",
                  value: <span className="tnum font-mono">{formatNumber(facility.capacity_mw)} MW</span>,
                },
                { term: "Timezone", value: facility.timezone },
                {
                  term: "Coordinates",
                  value:
                    facility.latitude !== null && facility.longitude !== null
                      ? `${facility.latitude.toFixed(3)}, ${facility.longitude.toFixed(3)}`
                      : "—",
                },
              ]}
            />
          </Panel>
        )}

        <Panel
          title="Data coverage"
          action={
            <Link href="/data">
              <Button>Upload</Button>
            </Link>
          }
        >
          {datasets.length === 0 ? (
            <EmptyState>No data uploaded. GridShift needs hourly prices and carbon intensity.</EmptyState>
          ) : (
            <>
              <Table>
                <thead>
                  <tr>
                    <TH>Metrics</TH>
                    <TH align="right">Hours</TH>
                    <TH>Window</TH>
                    <TH>Integrity</TH>
                    <TH>Checksum</TH>
                  </tr>
                </thead>
                <tbody>
                  {datasets.slice(0, 5).map((dataset) => {
                    const first = dataset.series[0];
                    return (
                      <tr key={dataset.id}>
                        <TD>{dataset.metrics.map(metricLabel).join(", ")}</TD>
                        <TD align="right" numeric>
                          {first?.hours ?? "—"}
                        </TD>
                        <TD>
                          {first
                            ? `${formatDateTime(first.start_utc)} → ${formatDateTime(first.end_utc)}`
                            : "—"}
                        </TD>
                        <TD>
                          {dataset.series.every((series) => series.is_contiguous) ? (
                            <span className="text-gain">contiguous</span>
                          ) : (
                            <span className="text-warn">has gaps</span>
                          )}
                        </TD>
                        <TD numeric>{shortChecksum(dataset.checksum)}</TD>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
              {metrics.length > 0 && (
                <p className="mt-3 text-xs text-ink-muted">
                  Metrics available: {metrics.map(metricLabel).join(", ")}
                </p>
              )}
            </>
          )}
        </Panel>

        <Panel
          title={resultScenario ? `Latest result — ${resultScenario.name}` : "Latest result"}
          action={
            <Link href="/optimize">
              <Button variant="primary">Optimize</Button>
            </Link>
          }
        >
          {result ? (
            <div className="flex flex-col gap-6">
              <ResultSummary result={result} />
              {result.hourly.length > 0 && <HourlyChart points={result.hourly} />}
            </div>
          ) : (
            <EmptyState>
              No optimization has been run yet. Build a scenario on the Optimize screen to
              see the baseline comparison here.
            </EmptyState>
          )}
        </Panel>
      </div>
    </>
  );
}
