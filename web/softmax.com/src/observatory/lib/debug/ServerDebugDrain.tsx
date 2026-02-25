import { DebugRequestBridge } from "@observatory/lib/debug/DebugRequestBridge";
import { drainServerRequests } from "@observatory/lib/repo/server";
import { FC } from "react";

/**
 * Server component that drains accumulated server-side request log entries
 * and passes them to the client via DebugRequestBridge.
 *
 * Place this in any server component (or layout) that calls getRepo()
 * to capture those requests in the debug panel.
 */
export const ServerDebugDrain: FC = () => {
  const entries = drainServerRequests();
  if (entries.length === 0) return null;
  return <DebugRequestBridge entries={entries} />;
};
