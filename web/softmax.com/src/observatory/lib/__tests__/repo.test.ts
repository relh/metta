import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, Repo } from "@observatory/lib/repo";

async function expectApiError(
  promise: Promise<unknown>,
  expectedMessage: string,
) {
  try {
    await promise;
    throw new Error("Expected promise to reject");
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe(expectedMessage);
  }
}

describe("Repo error handling", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("wraps fetch TypeError failures as transient outages", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed")),
    );

    const repo = new Repo("https://example.invalid");

    await expectApiError(
      repo.listTables(),
      "__transient__Observatory is temporarily unreachable — please try again in a moment.",
    );
  });

  it("preserves non-network fetch errors", async () => {
    const originalError = new Error("invalid header value");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(originalError));

    const repo = new Repo("https://example.invalid");

    await expect(repo.listTables()).rejects.toBe(originalError);
  });

  it("extracts a short JSON error message from 502 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: "upstream timed out" }), {
          status: 502,
          statusText: "Bad Gateway",
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const repo = new Repo("https://example.invalid");

    await expectApiError(repo.listTables(), "__transient__upstream timed out");
  });

  it("falls back to a generic message for HTML 502 responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html><body>bad gateway</body></html>", {
          status: 502,
          statusText: "Bad Gateway",
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    const repo = new Repo("https://example.invalid");

    await expectApiError(
      repo.listTables(),
      "__transient__Observatory API is temporarily unavailable.",
    );
  });

  it("falls back to a generic message for oversized 502 bodies", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("x".repeat(501), {
          status: 502,
          statusText: "Bad Gateway",
        }),
      ),
    );

    const repo = new Repo("https://example.invalid");

    await expectApiError(
      repo.listTables(),
      "__transient__Observatory API is temporarily unavailable.",
    );
  });

  it("treats 429 responses as transient", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("", {
          status: 429,
          statusText: "Too Many Requests",
        }),
      ),
    );

    const repo = new Repo("https://example.invalid");

    await expectApiError(
      repo.listTables(),
      "__transient__Too many requests — please try again soon.",
    );
  });
});
