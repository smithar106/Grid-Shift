/** Formatting helpers. Kept pure so they can be unit-tested and reused everywhere. */

const NUMBER = new Intl.NumberFormat("en-US");
const MONEY = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});
const MONEY_PRECISE = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMoney(value: number | null | undefined, precise = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return precise ? MONEY_PRECISE.format(value) : MONEY.format(value);
}

export function formatNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatInteger(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return NUMBER.format(Math.round(value));
}

/**
 * Percentage change. `null` is rendered as an em dash rather than 0%, because a
 * percentage of a zero baseline is undefined — showing 0% would be a false claim.
 */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatHours(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

/** UTC hour label from an ISO timestamp, e.g. "16T08". */
export function hourLabel(iso: string): string {
  const date = new Date(iso);
  return `${String(date.getUTCHours()).padStart(2, "0")}:00`;
}

export function dayLabel(iso: string): string {
  const date = new Date(iso);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

export function shortChecksum(checksum: string | null | undefined, length = 10): string {
  if (!checksum) return "—";
  return checksum.slice(0, length);
}

export function shortId(id: string | null | undefined, length = 8): string {
  if (!id) return "—";
  return id.slice(0, length);
}

/** Human label for a metric identifier. */
export function metricLabel(metric: string): string {
  return (
    {
      electricity_price: "Electricity price",
      carbon_intensity: "Carbon intensity",
      facility_load: "Facility load",
      temperature: "Temperature",
      relative_humidity: "Relative humidity",
    }[metric] ?? metric
  );
}

export function statusTone(status: string): "gain" | "loss" | "warn" | "neutral" {
  if (status === "optimal" || status === "optimized") return "gain";
  if (status === "infeasible" || status === "failed" || status === "numerical_error") return "loss";
  if (status === "time_limit" || status === "unbounded") return "warn";
  return "neutral";
}
