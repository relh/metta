"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/Button";
import {
  useRegisterErrorReset,
  useResetError,
} from "@observatory/components/ResetErrorContext";
import {
  getServerSnapshot as getOutageServerSnapshot,
  getSnapshot as getOutageSnapshot,
  setOutageSimulated,
  subscribe as subscribeOutage,
} from "@observatory/lib/debug/simulate-outage";
import {
  getDisplayMessage,
  isTransient,
  maxRetries,
  retryDelayMs,
} from "@observatory/lib/error-classification";

// Persists retry counts across component remounts (which happen on each reset()).
// Keyed by errorKey so switching to a new error resets the budget.
const retryRegistry = new Map<string, number>();

/** Clear the retry registry — for use in tests only. */
export function _resetRetryRegistry() {
  retryRegistry.clear();
}

export function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useRegisterErrorReset(reset);
  const resetError = useResetError();
  const outageActive = useSyncExternalStore(
    subscribeOutage,
    getOutageSnapshot,
    getOutageServerSnapshot,
  );

  const maxAutoRetries = maxRetries(error);
  // Stable key for this error — persists retry count across remounts.
  const errorKey = `${maxAutoRetries}:${error.message}`;
  if (!retryRegistry.has(errorKey)) {
    retryRegistry.set(errorKey, 0);
  }
  const retryCount = useRef(retryRegistry.get(errorKey)!);
  retryCount.current = retryRegistry.get(errorKey)!;

  const [autoRetrying, setAutoRetrying] = useState(
    () => retryCount.current < maxAutoRetries,
  );

  useEffect(() => {
    setAutoRetrying(retryCount.current < maxAutoRetries);
    if (retryCount.current >= maxAutoRetries) {
      console.error(error);
      return;
    }
    retryCount.current++;
    retryRegistry.set(errorKey, retryCount.current);
    const timer = setTimeout(() => {
      (resetError ?? reset)();
    }, retryDelayMs(retryCount.current));
    return () => clearTimeout(timer);
  }, [error, reset, resetError, maxAutoRetries, errorKey]);

  if (autoRetrying) {
    return (
      <div className="flex h-64 items-center justify-center gap-3 text-zinc-500 dark:text-zinc-400">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        <span className="text-sm">Retrying...</span>
      </div>
    );
  }

  const transient = isTransient(error);
  const displayMessage = getDisplayMessage(error);

  if (transient) {
    return (
      <div className="flex min-h-96 items-center justify-center p-8">
        <div className="w-full max-w-md rounded-2xl border border-blue-100 bg-white p-8 shadow-lg dark:border-blue-800 dark:bg-zinc-900">
          <div className="mb-6 flex flex-col items-center text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/40">
              <svg
                className="h-7 w-7 text-blue-500"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={1.5}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
                />
              </svg>
            </div>
            <h2 className="mb-2 text-xl font-semibold text-zinc-800 dark:text-zinc-100">
              Observatory is temporarily unavailable
            </h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">
              {displayMessage}. Please try again in a moment.
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <Button onClick={() => (resetError ?? reset)()}>Try again</Button>
            {outageActive && (
              <Button
                theme="primary"
                onClick={() => {
                  setOutageSimulated(false);
                  (resetError ?? reset)();
                }}
              >
                Disable Simulated Outage & Retry
              </Button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-96 items-center justify-center p-8">
      <div className="w-full max-w-md rounded-2xl border border-red-100 bg-white p-8 shadow-lg dark:border-red-800 dark:bg-zinc-900">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/40">
            <svg
              className="h-7 w-7 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
              />
            </svg>
          </div>
          <h2 className="mb-2 text-xl font-semibold text-zinc-800 dark:text-zinc-100">
            Something went wrong
          </h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {displayMessage}
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <Button onClick={() => (resetError ?? reset)()}>Try again</Button>
          {outageActive && (
            <Button
              theme="primary"
              onClick={() => {
                setOutageSimulated(false);
                (resetError ?? reset)();
              }}
            >
              Disable Simulated Outage & Retry
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
