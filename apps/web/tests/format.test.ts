import { describe, expect, it } from "vitest";

import {
  formatHours,
  formatInteger,
  formatMoney,
  formatNumber,
  formatPercent,
  hourLabel,
  metricLabel,
  shortChecksum,
  shortId,
  statusTone,
} from "@/lib/format";

describe("formatPercent", () => {
  it("signs positive values so a saving reads as a change", () => {
    expect(formatPercent(12.34)).toBe("+12.3%");
  });

  it("keeps negative values negative and visible", () => {
    expect(formatPercent(-8.5)).toBe("-8.5%");
  });

  it("renders an undefined percentage as an em dash, never 0%", () => {
    // A percentage of a zero baseline is undefined; showing 0% would be a false claim.
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
  });

  it("does not sign zero", () => {
    expect(formatPercent(0)).toBe("0.0%");
  });
});

describe("numeric formatting", () => {
  it("formats money with and without cents", () => {
    expect(formatMoney(23520)).toBe("$23,520");
    expect(formatMoney(23520.456, true)).toBe("$23,520.46");
  });

  it("renders missing values as an em dash", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatNumber(undefined)).toBe("—");
    expect(formatInteger(null)).toBe("—");
  });

  it("rounds integers and fixes decimals", () => {
    expect(formatInteger(1234.6)).toBe("1,235");
    expect(formatNumber(1.234, 2)).toBe("1.23");
  });

  it("pads hours for column alignment", () => {
    expect(formatHours(3)).toBe("03:00");
    expect(formatHours(23)).toBe("23:00");
  });
});

describe("identifiers", () => {
  it("shortens checksums and ids for tables", () => {
    expect(shortChecksum("abcdef1234567890")).toBe("abcdef1234");
    expect(shortChecksum(null)).toBe("—");
    expect(shortId("cff92a76-0eaa-4ed3")).toBe("cff92a76");
    expect(shortId(null)).toBe("—");
  });
});

describe("labels", () => {
  it("humanizes known metrics and passes through unknown ones", () => {
    expect(metricLabel("electricity_price")).toBe("Electricity price");
    expect(metricLabel("carbon_intensity")).toBe("Carbon intensity");
    expect(metricLabel("something_else")).toBe("something_else");
  });

  it("extracts the UTC hour from a timestamp", () => {
    expect(hourLabel("2026-09-16T08:00:00Z")).toBe("08:00");
    expect(hourLabel("2026-09-16T23:00:00+00:00")).toBe("23:00");
  });
});

describe("statusTone", () => {
  it("maps solver outcomes to a tone", () => {
    expect(statusTone("optimal")).toBe("gain");
    expect(statusTone("optimized")).toBe("gain");
    expect(statusTone("infeasible")).toBe("loss");
    expect(statusTone("numerical_error")).toBe("loss");
    expect(statusTone("time_limit")).toBe("warn");
    expect(statusTone("draft")).toBe("neutral");
  });
});
