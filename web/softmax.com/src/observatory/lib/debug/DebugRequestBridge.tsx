"use client";

import type { RequestLogEntry } from "@observatory/lib/debug/request-log";
import { addEntries } from "@observatory/lib/debug/request-log";
import { FC, useEffect } from "react";

/**
 * Client component that bridges server-side request log entries into the client store.
 * Rendered by ServerDebugDrain with serialized entries from the server.
 * Renders nothing visible.
 */
export const DebugRequestBridge: FC<{ entries: RequestLogEntry[] }> = ({
  entries,
}) => {
  useEffect(() => {
    if (entries.length > 0) {
      addEntries(entries);
    }
  }, [entries]);

  return null;
};
