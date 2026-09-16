"use client";

import { isDaily } from "@/lib/buckets";
import type { HourlyPoint, Workload } from "@/lib/types";

/**
 * When each job runs, as a compact grid.
 *
 * A table of 336 numbers per job is unreadable, and a stacked bar chart loses job identity.
 * A grid shows the shape of the schedule — which periods each job occupies and how hard it
 * runs — which is what an operator scans for. It aggregates to days on long horizons for
 * the same reason the chart does.
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

  const daily = isDaily(hourly);
  const hoursPerBucket = daily ? 24 : 1;
  const bucketCount = daily ? Math.ceil(hourly.length / 24) : hourly.length;

  const limits = new Map(workloads.map((workload) => [workload.job_id, workload.max_mw]));

  // Axis labels: the hour for hourly views, the day-of-month for daily views.
  const labels = Array.from({ length: bucketCount }, (_, bucket) => {
    const firstHour = bucket * hoursPerBucket;
    const stamp = hourly[firstHour]?.timestamp_utc ?? "";
    return daily ? stamp.slice(8, 10) : stamp.slice(11, 13);
  });

  const labelStep = bucketCount > 40 ? 5 : bucketCount > 16 ? 2 : 1;

  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-0">
        <caption className="sr-only">
          Energy allocated to each workload per {daily ? "day" : "hour"}, shaded by
          utilisation of the workload&apos;s power limit.
        </caption>
        <thead>
          <tr>
            <th className="pr-3" />
            {labels.map((label, bucket) => (
              <th
                key={bucket}
                scope="col"
                className="pb-1 text-center text-[9px] font-normal text-ink-faint"
              >
                {bucket % labelStep === 0 ? label : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {jobIds.map((jobId) => {
            const limit = limits.get(jobId) ?? 1;
            const perHour = allocations[jobId];

            return (
              <tr key={jobId}>
                <th
                  scope="row"
                  className="whitespace-nowrap pr-3 text-right text-[11px] font-normal text-ink-muted"
                >
                  {jobId}
                </th>
                {Array.from({ length: bucketCount }, (_, bucket) => {
                  const energy = perHour
                    .slice(bucket * hoursPerBucket, (bucket + 1) * hoursPerBucket)
                    .reduce((sum, value) => sum + value, 0);
                  const ceiling = limit * hoursPerBucket;
                  const ratio = ceiling > 0 ? Math.min(energy / ceiling, 1) : 0;
                  const when = daily ? `day ${bucket + 1}` : `hour ${bucket}`;
                  return (
                    <td key={bucket} className="p-0">
                      <span
                        title={`${jobId}, ${when}: ${energy.toFixed(1)} MWh`}
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
        Shading is energy as a share of each workload&apos;s power limit
        {daily ? ", summed per day" : ", per hour"}. Axis labels are{" "}
        {daily ? "day of month" : "hour of day"}.
      </p>
    </div>
  );
}
