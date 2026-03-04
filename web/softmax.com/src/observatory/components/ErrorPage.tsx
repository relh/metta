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

const MAX_AUTO_RETRIES = 2;
const RETRY_DELAY_MS = 1000;

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

  const retryCount = useRef(0);
  const [autoRetrying, setAutoRetrying] = useState(
    () => retryCount.current < MAX_AUTO_RETRIES,
  );

  useEffect(() => {
    if (retryCount.current >= MAX_AUTO_RETRIES) {
      console.error(error);
      setAutoRetrying(false);
      return;
    }
    retryCount.current++;
    const timer = setTimeout(() => {
      (resetError ?? reset)();
    }, RETRY_DELAY_MS);
    return () => clearTimeout(timer);
  }, [error, reset, resetError]);

  if (autoRetrying) {
    return (
      <div className="flex items-center gap-2 p-4 text-zinc-500 dark:text-zinc-400">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
        Retrying...
      </div>
    );
  }

  return (
    <div className="rounded-md bg-red-100 p-4 dark:bg-red-900/30">
      <h2 className="mb-4 text-xl font-bold text-red-700 dark:text-red-400">
        Something went wrong!
      </h2>
      <pre className="wrap-break-word whitespace-pre-wrap">{error.message}</pre>
      <div className="mt-4 flex gap-2">
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
  );
}
