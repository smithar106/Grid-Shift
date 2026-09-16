import { describe, expect, it } from "vitest";

import { HOURLY_LIMIT, isDaily, toBuckets } from "@/lib/buckets";
import type { HourlyPoint } from "@/lib/types";

function point(hour: number, overrides: Partial<HourlyPoint> = {}): HourlyPoint {
  const day = Math.floor(hour / 24);
  const hourOfDay = hour % 24;
  const stamp = new Date(Date.UTC(2026, 8, 14 + day, hourOfDay)).toISOString();
  return {
    hour,
    timestamp_utc: stamp,
    price_usd_per_mwh: 10 + hourOfDay,
    carbon_tco2e_per_mwh: 0.5,
    capacity_mwh: 38,
    baseline_load_mwh: 2,
    optimized_flexible_mwh: 1,
    optimized_consumption_mwh: 3,
    baseline_flexible_mwh: 0,
    baseline_consumption_mwh: 2,
    optimized_cost_usd: 30,
    optimized_emissions_tco2e: 1.5,
    baseline_cost_usd: 20,
    baseline_emissions_tco2e: 1,
    ...overrides,
  };
}

function series(hours: number): HourlyPoint[] {
  return Array.from({ length: hours }, (_, hour) => point(hour));
}

describe("isDaily", () => {
  it("keeps short horizons hourly", () => {
    expect(isDaily(series(24))).toBe(false);
    expect(isDaily(series(HOURLY_LIMIT))).toBe(false);
  });

  it("switches to daily beyond the limit", () => {
    expect(isDaily(series(HOURLY_LIMIT + 1))).toBe(true);
    expect(isDaily(series(336))).toBe(true);
  });
});

describe("toBuckets, hourly", () => {
  it("returns one bucket per hour", () => {
    const buckets = toBuckets(series(24));
    expect(buckets).toHaveLength(24);
    expect(buckets[0].hours).toBe(1);
    expect(buckets[8].label).toBe("08:00");
    expect(buckets[8].price).toBe(18);
  });

  it("uses a unique key per bucket even when labels would repeat", () => {
    // The bug this guards: hour labels repeat every day, so using a label as a React key
    // produced duplicate-key warnings and unstable rows.
    const buckets = toBuckets(series(72));
    expect(new Set(buckets.map((bucket) => bucket.key)).size).toBe(72);
  });
});

describe("toBuckets, daily", () => {
  it("groups a fortnight into 14 days", () => {
    const buckets = toBuckets(series(336));
    expect(buckets).toHaveLength(14);
    expect(buckets.every((bucket) => bucket.hours === 24)).toBe(true);
  });

  it("sums energy and averages price", () => {
    const buckets = toBuckets(series(336));
    // Each hour contributes 2 MWh fixed, 1 MWh flexible.
    expect(buckets[0].fixed).toBeCloseTo(48);
    expect(buckets[0].flexible).toBeCloseTo(24);
    expect(buckets[0].total).toBeCloseTo(72);
    // Mean of hours 0..23 of (10 + hourOfDay) = 10 + 11.5.
    expect(buckets[0].price).toBeCloseTo(21.5);
  });

  it("uses unique keys and distinct labels per day", () => {
    const buckets = toBuckets(series(336));
    expect(new Set(buckets.map((bucket) => bucket.key)).size).toBe(14);
    expect(new Set(buckets.map((bucket) => bucket.label)).size).toBe(14);
  });

  it("handles a horizon that is not a whole number of days", () => {
    const buckets = toBuckets(series(100));
    expect(buckets).toHaveLength(5);
    expect(buckets[4].hours).toBe(4);
  });
});
