/**
 * Thin fetch wrapper around the same-origin GridShift API proxy.
 *
 * Browser code always calls `/api/v1/*` on its own origin. The Next.js route handler
 * at `app/api/v1/[...path]/route.ts` forwards to the FastAPI service, which keeps the
 * API off the public internet and avoids cross-origin configuration entirely.
 */

import type {
  Dataset,
  Facility,
  ObjectiveMode,
  OptimizationResult,
  Scenario,
  TradeoffCurve,
  Weather,
  Workload,
} from "./types";

export const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type ApiFetchOptions = Omit<RequestInit, "body"> & {
  body?: unknown;
  timeoutMs?: number;
};

function extractMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.detail === "string") return record.detail;
    if (Array.isArray(record.detail) && record.detail.length > 0) {
      const first = record.detail[0];
      if (first && typeof first === "object" && "msg" in first) {
        return String((first as Record<string, unknown>).msg);
      }
    }
    // GridShift's validation handlers return every reason; show them all.
    if (Array.isArray(record.issues) && record.issues.length > 0) {
      return record.issues.map(String).join(" · ");
    }
    if (Array.isArray(record.reasons) && record.reasons.length > 0) {
      return record.reasons.map(String).join(" ");
    }
  }
  return fallback;
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { body, timeoutMs = 30_000, headers, ...rest } = options;
  const signal = rest.signal ?? AbortSignal.timeout(timeoutMs);

  const response = await fetch(`${API_PREFIX}${path}`, {
    ...rest,
    signal,
    headers: {
      Accept: "application/json",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const contentType = response.headers.get("content-type") ?? "";
  const isJson = contentType.includes("application/json");
  const payload: unknown = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    throw new ApiError(
      extractMessage(payload, `Request failed with status ${response.status}`),
      response.status,
      payload,
    );
  }

  return payload as T;
}

async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    method: "POST",
    body: form,
    signal: AbortSignal.timeout(60_000),
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      extractMessage(payload, `Upload failed with status ${response.status}`),
      response.status,
      payload,
    );
  }
  return payload as T;
}

// --- Endpoints ---------------------------------------------------------------------

export const getHealth = () =>
  apiFetch<{ status: string; service: string; version: string; environment: string }>("/health", {
    timeoutMs: 8_000,
  });

export const listFacilities = () => apiFetch<Facility[]>("/facilities");

export const createFacility = (payload: {
  name: string;
  location_id: string;
  latitude?: number | null;
  longitude?: number | null;
  timezone: string;
  capacity_mw: number;
}) => apiFetch<Facility>("/facilities", { method: "POST", body: payload });

export const listDatasets = (facilityId?: string) =>
  apiFetch<Dataset[]>(facilityId ? `/datasets?facility_id=${facilityId}` : "/datasets");

export const uploadDataset = (
  file: File,
  options: { facilityId?: string; timezone?: string; allowGaps?: boolean } = {},
) => {
  const form = new FormData();
  form.append("file", file);
  if (options.facilityId) form.append("facility_id", options.facilityId);
  if (options.timezone) form.append("timezone", options.timezone);
  form.append("allow_gaps", String(options.allowGaps ?? false));
  return apiUpload<Dataset>("/datasets", form);
};

export const listScenarios = () => apiFetch<Scenario[]>("/scenarios");

export const getScenario = (id: string) => apiFetch<Scenario>(`/scenarios/${id}`);

export const createScenario = (payload: {
  facility_id: string;
  name: string;
  objective: ObjectiveMode;
  carbon_price_usd_per_tco2e: number;
  dataset_ids: string[];
  workloads: Omit<Workload, "id">[];
}) => apiFetch<Scenario>("/scenarios", { method: "POST", body: payload });

export const optimizeScenario = (id: string) =>
  apiFetch<OptimizationResult>(`/scenarios/${id}/optimize`, { method: "POST", timeoutMs: 60_000 });

export const getResults = (id: string) => apiFetch<OptimizationResult>(`/scenarios/${id}/results`);

export const exploreTradeoff = (id: string, carbonPrices: number[]) =>
  apiFetch<TradeoffCurve>(`/scenarios/${id}/explore`, {
    method: "POST",
    body: { carbon_prices_usd_per_tco2e: carbonPrices },
    timeoutMs: 60_000,
  });

export const exportUrl = (id: string, format: "csv" | "json") =>
  `${API_PREFIX}/scenarios/${id}/export?format=${format}`;

export const getWeather = (params: {
  latitude: number;
  longitude: number;
  locationId: string;
  forecastDays?: number;
}) => {
  const query = new URLSearchParams({
    latitude: String(params.latitude),
    longitude: String(params.longitude),
    location_id: params.locationId,
    forecast_days: String(params.forecastDays ?? 2),
  });
  return apiFetch<Weather>(`/weather?${query}`, { timeoutMs: 20_000 });
};
