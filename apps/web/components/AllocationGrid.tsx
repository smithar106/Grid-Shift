"use client";

import { hourLabel } from "@/lib/format";
import type { HourlyPoint, Workload } from "@/lib/types";

/**
 * When each job runs, as a compact grid.
 *
 * A table of 24 numbers per job is unreadable at a glance, and a stacked bar chart loses
 * job identity. A grid shows the *shape* of the schedule — which hours each job occupies
 * and how hard it is running — which is what an operator actually scans for.
 */
export function AllocationGrid({
  allocations,
  workloads,
  hourly,
}: {
  allocations: Record<string, number[]>;
  workloads: Workload[];
  hourly: HourlyPoint[];
}) {
  const jobIds = Object.keys(allocations);
  if (jobIds.length === 0) {
    return <p className="py-4 text-sm text-ink-faint">No flexible workloads in this scenario.</p>;
  }

  const limits = new Map(workloads.map((workload) => [workload.job_id, workload.max_mw]));
  const hours = hourly.map((point) => hourLabel(point.timestamp_utc));

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0">
        <caption className="sr-only">
          Energy allocated to each workload in each hour, shaded by utilisation of the
          workload&apos;s power limit.
        </caption>
        <thead>
          <tr>
            <th className="pr-3" />
            {hours.map((hour, index) => (
              <th
                key={hour}
                scope="col"
                className="pb-1 text-center text-[9px] font-normal text-ink-faint"
              >
                {index % 2 === 0 ? hour.slice(0, 2) : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {jobIds.map((jobId) => {
            const limit = limits.get(jobId) ?? Math.max(...allocations[jobId], 1);
            return (
              <tr key={jobId}>
                <th
                  scope="row"
                  className="whitespace-nowrap pr-3 text-right text-[11px] font-normal text-ink-muted"
                >
                  {jobId}
                </th>
                {allocations[jobId].map((energy, hour) => {
                  const ratio = limit > 0 ? Math.min(energy / limit, 1) : 0;
                  const label =
                    energy > 0
                      ? `${jobId}, ${hours[hour] ?? `hour ${hour}`}: ${energy.toFixed(2)} MWh`
                      : `${jobId}, ${hours[hour] ?? `hour ${hour}`}: idle`;
                  return (
                    <td key={hour} className="p-0">
                      <span
                        title={label}
                        className="block size-4 rounded-[2px] border border-line"
                        style={{
                          backgroundColor:
                            ratio > 0
                              ? `color-mix(in oklab, var(--color-accent) ${Math.round(
                                  ratio * 100,
                                )}%, transparent)`
                              : "transparent",
                        }}
                      />
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-ink-faint">
        Shading is energy as a share of each workload&apos;s power limit.
      </p>
    </div>
  );
}
