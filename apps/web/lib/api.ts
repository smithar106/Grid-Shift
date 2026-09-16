/**
 * Thin fetch wrapper around the same-origin GridShift API proxy.
 *
 * Browser code always calls `/api/v1/*` on its own origin. The Next.js route handler
 * at `app/api/v1/[...path]/route.ts` forwards to the FastAPI service, which keeps the
 * API off the public internet and avoids cross-origin configuration entirely.
 */

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
