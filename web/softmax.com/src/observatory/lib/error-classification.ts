const TRANSIENT_PREFIX = "__transient__";
const PERMANENT_PREFIX = "__permanent__";
const BASE_RETRY_DELAY_MS = 1000;

// Pure helpers for classifying errors by transience.
//
// ApiError encodes its `transient` flag as a message prefix so the
// classification survives Next.js SSR serialisation, which strips all
// custom Error properties and preserves only `message` and `digest`.
//
//   __transient__  → recoverable outage, retry automatically
//   __permanent__  → definitive error (404, bad request…), no retry
//   (no prefix)    → unknown origin, hedge with one retry

export function isTransient(error: Error): boolean {
  return (
    (error as any).transient === true ||
    error.message.startsWith(TRANSIENT_PREFIX)
  );
}

export function isPermanent(error: Error): boolean {
  return (
    (error as any).transient === false ||
    error.message.startsWith(PERMANENT_PREFIX)
  );
}

export function getDisplayMessage(error: Error): string {
  return error.message.replace(/^__(transient|permanent)__/, "");
}

/** Returns how many auto-retries should be attempted for this error. */
export function maxRetries(error: Error): number {
  if (isTransient(error)) return 2;
  if (isPermanent(error)) return 0;
  return 1; // unknown / framework errors: one hedge retry
}

/** Returns the auto-retry delay in milliseconds for the given attempt number. */
export function retryDelayMs(attempt: number): number {
  return BASE_RETRY_DELAY_MS * 2 ** Math.max(attempt - 1, 0);
}
