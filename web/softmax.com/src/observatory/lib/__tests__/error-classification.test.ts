import { describe, expect, it } from "vitest";

import { ApiError } from "@observatory/lib/repo";
import {
  getDisplayMessage,
  isPermanent,
  isTransient,
  maxRetries,
  retryDelayMs,
} from "@observatory/lib/error-classification";

// ─── ApiError construction ───────────────────────────────────────────────────

describe("ApiError", () => {
  describe("transient=true", () => {
    const err = new ApiError("backend is down", true);

    it("sets transient flag", () => {
      expect(err.transient).toBe(true);
    });

    it("prefixes message with __transient__", () => {
      expect(err.message).toBe("__transient__backend is down");
    });

    it("has correct name", () => {
      expect(err.name).toBe("ApiError");
    });

    it("is an instanceof Error", () => {
      expect(err).toBeInstanceOf(Error);
    });
  });

  describe("transient=false", () => {
    const err = new ApiError("not found", false);

    it("sets transient flag", () => {
      expect(err.transient).toBe(false);
    });

    it("prefixes message with __permanent__", () => {
      expect(err.message).toBe("__permanent__not found");
    });
  });
});

// ─── isTransient ─────────────────────────────────────────────────────────────

describe("isTransient", () => {
  it("true when transient flag is set on the object (client-side path)", () => {
    expect(isTransient(new ApiError("msg", true))).toBe(true);
  });

  it("true from SSR-serialised error with __transient__ prefix", () => {
    // Simulate Next.js stripping custom properties, leaving only message.
    const serialised = Object.assign(
      new Error("__transient__backend is down"),
      {
        transient: undefined,
      },
    );
    expect(isTransient(serialised)).toBe(true);
  });

  it("false for permanent ApiError (client-side)", () => {
    expect(isTransient(new ApiError("not found", false))).toBe(false);
  });

  it("false for SSR-serialised permanent error", () => {
    const serialised = new Error("__permanent__not found");
    expect(isTransient(serialised)).toBe(false);
  });

  it("false for plain Error (no prefix, no flag)", () => {
    expect(isTransient(new Error("something exploded"))).toBe(false);
  });
});

// ─── isPermanent ─────────────────────────────────────────────────────────────

describe("isPermanent", () => {
  it("true when transient flag is false on the object (client-side path)", () => {
    expect(isPermanent(new ApiError("bad request", false))).toBe(true);
  });

  it("true from SSR-serialised error with __permanent__ prefix", () => {
    const serialised = new Error("__permanent__not found");
    expect(isPermanent(serialised)).toBe(true);
  });

  it("false for transient ApiError (client-side)", () => {
    expect(isPermanent(new ApiError("down", true))).toBe(false);
  });

  it("false for SSR-serialised transient error", () => {
    const serialised = new Error("__transient__down");
    expect(isPermanent(serialised)).toBe(false);
  });

  it("false for plain Error (no prefix, no flag)", () => {
    expect(isPermanent(new Error("unknown"))).toBe(false);
  });
});

// ─── getDisplayMessage ────────────────────────────────────────────────────────

describe("getDisplayMessage", () => {
  it("strips __transient__ prefix", () => {
    expect(getDisplayMessage(new ApiError("backend is down", true))).toBe(
      "backend is down",
    );
  });

  it("strips __permanent__ prefix", () => {
    expect(getDisplayMessage(new ApiError("not found", false))).toBe(
      "not found",
    );
  });

  it("strips prefix from SSR-serialised transient error", () => {
    expect(getDisplayMessage(new Error("__transient__backend is down"))).toBe(
      "backend is down",
    );
  });

  it("strips prefix from SSR-serialised permanent error", () => {
    expect(getDisplayMessage(new Error("__permanent__not found"))).toBe(
      "not found",
    );
  });

  it("leaves plain Error messages unchanged", () => {
    expect(getDisplayMessage(new Error("something exploded"))).toBe(
      "something exploded",
    );
  });

  it("does not double-strip if prefix appears mid-message", () => {
    const err = new Error("prefix here __transient__ not at start");
    expect(getDisplayMessage(err)).toBe(
      "prefix here __transient__ not at start",
    );
  });
});

// ─── maxRetries ───────────────────────────────────────────────────────────────

describe("maxRetries", () => {
  it("returns 2 for transient ApiError (client-side)", () => {
    expect(maxRetries(new ApiError("down", true))).toBe(2);
  });

  it("returns 2 for SSR-serialised transient error", () => {
    expect(maxRetries(new Error("__transient__down"))).toBe(2);
  });

  it("returns 0 for permanent ApiError (client-side)", () => {
    expect(maxRetries(new ApiError("not found", false))).toBe(0);
  });

  it("returns 0 for SSR-serialised permanent error", () => {
    expect(maxRetries(new Error("__permanent__not found"))).toBe(0);
  });

  it("returns 1 for plain unknown Error (hedge retry)", () => {
    expect(maxRetries(new Error("something unexpected"))).toBe(1);
  });
});

describe("retryDelayMs", () => {
  it("uses a 1 second delay for the first retry", () => {
    expect(retryDelayMs(1)).toBe(1000);
  });

  it("backs off exponentially on later retries", () => {
    expect(retryDelayMs(2)).toBe(2000);
    expect(retryDelayMs(3)).toBe(4000);
  });
});

// ─── Specific status-code scenarios ──────────────────────────────────────────
// These document the expected ApiError shape for each HTTP status the Repo
// class handles, without instantiating Repo or mocking fetch.

describe("status-code classification contracts", () => {
  it("network failure → transient", () => {
    const err = new ApiError(
      "Observatory is temporarily unreachable — please try again in a moment.",
      true,
    );
    expect(isTransient(err)).toBe(true);
    expect(isPermanent(err)).toBe(false);
    expect(maxRetries(err)).toBe(2);
  });

  it("502 → transient", () => {
    const err = new ApiError("Failed to reach Observatory API upstream.", true);
    expect(isTransient(err)).toBe(true);
    expect(maxRetries(err)).toBe(2);
  });

  it("503 → transient", () => {
    const err = new ApiError(
      "Service temporarily unavailable — please try again",
      true,
    );
    expect(isTransient(err)).toBe(true);
    expect(maxRetries(err)).toBe(2);
  });

  it("simulated outage → transient", () => {
    const err = new ApiError("Simulated API outage", true);
    expect(isTransient(err)).toBe(true);
    expect(maxRetries(err)).toBe(2);
  });

  it("404 client-side → permanent, no retry", () => {
    const err = new ApiError("Not found", false);
    expect(isPermanent(err)).toBe(true);
    expect(maxRetries(err)).toBe(0);
  });

  it("generic HTTP error (e.g. 500) → permanent, no retry", () => {
    const err = new ApiError(
      "API call failed: 500 Internal Server Error",
      false,
    );
    expect(isPermanent(err)).toBe(true);
    expect(maxRetries(err)).toBe(0);
  });

  it("SSR-serialised permanent error loses flag but retains prefix", () => {
    // Simulate Next.js serialisation of a permanent ApiError
    const original = new ApiError("Not found", false);
    const serialised = new Error(original.message); // only message survives
    expect(isPermanent(serialised)).toBe(true);
    expect(maxRetries(serialised)).toBe(0);
    expect(getDisplayMessage(serialised)).toBe("Not found");
  });

  it("SSR-serialised transient error loses flag but retains prefix", () => {
    const original = new ApiError("backend is down", true);
    const serialised = new Error(original.message);
    expect(isTransient(serialised)).toBe(true);
    expect(maxRetries(serialised)).toBe(2);
    expect(getDisplayMessage(serialised)).toBe("backend is down");
  });
});
