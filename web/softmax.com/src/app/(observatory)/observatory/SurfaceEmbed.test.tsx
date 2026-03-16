// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SurfaceEmbed } from "./SurfaceEmbed";

describe("SurfaceEmbed", () => {
  beforeEach(() => {
    document.documentElement.className = "dark";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders the themed iframe once the session token is ready", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        token: "abc123",
        expiresAt: "2030-01-01T00:00:00.000Z",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <SurfaceEmbed
        src="https://surface.example.dev/path?foo=bar"
        serviceName="Bardo"
        iframeTitle="Policy Bardo"
      />,
    );

    const iframe = await screen.findByTitle("Policy Bardo");

    expect(fetchMock).toHaveBeenCalledWith("/api/observatory/session-token", {
      method: "POST",
      cache: "no-store",
    });
    expect(iframe.getAttribute("src")).toBe(
      "https://surface.example.dev/path?foo=bar&theme=dark#abc123",
    );
  });

  it("fails closed when the session token bootstrap fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
      }),
    );

    render(
      <SurfaceEmbed
        src="https://surface.example.dev/path"
        serviceName="Bardo"
        iframeTitle="Policy Bardo"
      />,
    );

    expect(
      await screen.findByText(
        "Unable to prepare bardo authentication: Failed to create bardo token (403)",
      ),
    ).toBeTruthy();
    expect(screen.queryByTitle("Policy Bardo")).toBeNull();
  });
});
