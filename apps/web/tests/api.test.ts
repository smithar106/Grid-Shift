import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";

function mockFetch(response: Response) {
  const spy = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", spy);
  return spy;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("prefixes requests with the same-origin API path", async () => {
    const spy = mockFetch(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await apiFetch("/health");

    expect(spy).toHaveBeenCalledOnce();
    expect(spy.mock.calls[0][0]).toBe("/api/v1/health");
  });

  it("serializes JSON bodies and sets the content type", async () => {
    const spy = mockFetch(
      new Response(JSON.stringify({ id: "abc" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      }),
    );

    await apiFetch("/scenarios", { method: "POST", body: { objective: "cost" } });

    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ objective: "cost" }));
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("throws ApiError with the server-provided detail", async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: "Deadline cannot be met" }), {
        status: 422,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(apiFetch("/scenarios/1/optimize", { method: "POST" })).rejects.toMatchObject({
      name: "ApiError",
      message: "Deadline cannot be met",
      status: 422,
    });
  });

  it("surfaces FastAPI validation message arrays", async () => {
    mockFetch(
      new Response(JSON.stringify({ detail: [{ msg: "value is not a valid datetime" }] }), {
        status: 422,
        headers: { "content-type": "application/json" },
      }),
    );

    await expect(apiFetch("/datasets")).rejects.toThrowError("value is not a valid datetime");
  });
});
