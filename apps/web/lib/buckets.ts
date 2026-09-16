import type { HourlyPoint } from "./types";

/**
 * Bucketing for long horizons.
 *
 * A fortnight is 336 hours. Drawing 336 bars makes an unreadable smear and 336 grid
 * columns overflow the page, so anything longer than four days is grouped by day. The
 * decision at that scale is "which days took the work", not "which hour", so daily
 * aggregation is the more useful view rather than merely a cheaper one.
 */

/** Above this many hours, the views switch to daily buckets. */
export const HOURLY_LIMIT = 96;

export interface EnergyBucket {
  /** Stable identity. Never the display label: hour labels repeat across days. */
  key: string;
  /** Short axis label. */
  label: string;
  /** Longer description for tooltips and screen readers. */
  detail: string;
  hours: number;
  /** Mean price across the bucket, USD/MWh. */
  price: number;
  /** Mean carbon intensity across the bucket, tCO2e/MWh. */
  carbon: number;
  /** Total fixed load, MWh. */
  fixed: number;
  /** Total optimized flexible load, MWh. */
  flexible: number;
  /** Total optimized consumption, MWh. */
  total: number;
  /** Total baseline consumption, MWh. */
  baseline: number;
  /** Highest capacity ceiling in the bucket, MWh. */
  capacity: number;
}

export function isDaily(points: HourlyPoint[]): boolean {
  return points.length > HOURLY_LIMIT;
}

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

function dayLabel(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

function hourLabel(iso: string): string {
  return `${iso.slice(11, 13)}:00`;
}

const mean = (values: number[]) =>
  values.length === 0 ? 0 : values.reduce((sum, value) => sum + value, 0) / values.length;

export function toBuckets(points: HourlyPoint[]): EnergyBucket[] {
  if (!isDaily(points)) {
    return points.map((point) => ({
      key: String(point.hour),
      label: hourLabel(point.timestamp_utc),
      detail: `Hour ${point.hour} · ${point.timestamp_utc.slice(0, 16).replace("T", " ")} UTC`,
      hours: 1,
      price: point.price_usd_per_mwh,
      carbon: point.carbon_tco2e_per_mwh,
      fixed: point.baseline_load_mwh,
      flexible: point.optimized_flexible_mwh,
      total: point.optimized_consumption_mwh,
      baseline: point.baseline_consumption_mwh,
      capacity: point.capacity_mwh,
    }));
  }

  const grouped = new Map<string, HourlyPoint[]>();
  for (const point of points) {
    const key = dayKey(point.timestamp_utc);
    const bucket = grouped.get(key);
    if (bucket) bucket.push(point);
    else grouped.set(key, [point]);
  }

  return [...grouped.entries()].map(([key, members]) => ({
    key,
    label: dayLabel(members[0].timestamp_utc),
    detail: `${dayLabel(members[0].timestamp_utc)} · ${members.length} hours`,
    hours: members.length,
    price: mean(members.map((point) => point.price_usd_per_mwh)),
    carbon: mean(members.map((point) => point.carbon_tco2e_per_mwh)),
    fixed: members.reduce((sum, point) => sum + point.baseline_load_mwh, 0),
    flexible: members.reduce((sum, point) => sum + point.optimized_flexible_mwh, 0),
    total: members.reduce((sum, point) => sum + point.optimized_consumption_mwh, 0),
    baseline: members.reduce((sum, point) => sum + point.baseline_consumption_mwh, 0),
    capacity: Math.max(...members.map((point) => point.capacity_mwh)) * members.length,
  }));
}
