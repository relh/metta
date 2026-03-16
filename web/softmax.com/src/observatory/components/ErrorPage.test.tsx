// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ErrorPage,
  _resetRetryRegistry,
} from "@observatory/components/ErrorPage";
import { ApiError } from "@observatory/lib/repo";

describe("ErrorPage", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, "error").mockImplementation(() => {});
    _resetRetryRegistry();
  });

  it("backs off between repeated transient retries", async () => {
    const reset = vi.fn();
    const { rerender } = render(
      <ErrorPage error={new ApiError("backend is down", true)} reset={reset} />,
    );

    expect(screen.getByText("Retrying...")).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(reset).toHaveBeenCalledTimes(1);

    rerender(
      <ErrorPage error={new ApiError("backend is down", true)} reset={reset} />,
    );

    await act(async () => {
      vi.advanceTimersByTime(1999);
    });
    expect(reset).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(reset).toHaveBeenCalledTimes(2);
  });

  it("stops auto-retrying once the transient retry budget is exhausted", async () => {
    const reset = vi.fn();
    const { rerender } = render(
      <ErrorPage error={new ApiError("backend is down", true)} reset={reset} />,
    );

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    rerender(
      <ErrorPage error={new ApiError("backend is down", true)} reset={reset} />,
    );

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    rerender(
      <ErrorPage error={new ApiError("backend is down", true)} reset={reset} />,
    );

    expect(
      screen.getByText("Observatory is temporarily unavailable"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    expect(reset).toHaveBeenCalledTimes(2);
  });

  it("does not auto-retry permanent errors", async () => {
    const reset = vi.fn();

    render(
      <ErrorPage error={new ApiError("Not found", false)} reset={reset} />,
    );

    expect(screen.getByText("Something went wrong")).toBeTruthy();
    expect(screen.getByText("Not found")).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    expect(reset).not.toHaveBeenCalled();
  });
});
