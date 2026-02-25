"use client";

import clsx from "clsx";
import { FC, use, useCallback, useState, useSyncExternalStore } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";
import {
  Dropdown,
  DropdownMenu,
  DropdownMenuItem,
} from "@observatory/components/Dropdown";
import {
  Table,
  TableBody,
  TableHeader,
  TD,
  TH,
  TR,
} from "@observatory/components/Table";
import type { RequestLogEntry } from "@observatory/lib/debug/request-log";
import {
  clearEntries,
  getServerSnapshot,
  getSnapshot,
  subscribe,
} from "@observatory/lib/debug/request-log";
import {
  getServerSnapshot as getOutageServerSnapshot,
  getSnapshot as getOutageSnapshot,
  setOutageSimulated,
  subscribe as subscribeOutage,
} from "@observatory/lib/debug/simulate-outage";
import { useDebugPanelVisible } from "@observatory/lib/debug/useDebugPanelVisible";

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const StatusBadge: FC<{ status: number }> = ({ status }) => {
  const color =
    status === 0
      ? "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200"
      : status < 300
        ? "bg-green-200 text-green-800 dark:bg-green-900 dark:text-green-200"
        : status < 400
          ? "bg-yellow-200 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200"
          : "bg-red-200 text-red-800 dark:bg-red-900 dark:text-red-200";

  return (
    <span className={clsx("rounded px-1.5 py-0.5 font-mono text-xs", color)}>
      {status || "ERR"}
    </span>
  );
};

const SourceBadge: FC<{ source: "server" | "client" }> = ({ source }) => {
  const color =
    source === "server"
      ? "bg-blue-200 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
      : "bg-purple-200 text-purple-800 dark:bg-purple-900 dark:text-purple-200";
  return (
    <span className={clsx("rounded px-1.5 py-0.5 text-xs", color)}>
      {source}
    </span>
  );
};

const EndpointCell: FC<{ entry: RequestLogEntry }> = ({ entry }) => {
  const { apiBaseUrl } = use(AppContext);

  const copyCurl = useCallback(() => {
    const parts = ["curl"];
    if (entry.method !== "GET") {
      parts.push(`-X ${entry.method}`);
    }
    // if (token) {
    //   parts.push(`-H "X-Auth-Token: ${token}"`);
    // }
    parts.push(`"${apiBaseUrl}${entry.endpoint}"`);
    navigator.clipboard.writeText(parts.join(" "));
  }, [entry, apiBaseUrl]);

  return (
    <Dropdown
      render={({ close }) => (
        <DropdownMenu>
          <DropdownMenuItem
            title="Copy as curl"
            onClick={() => {
              copyCurl();
              close();
            }}
          />
        </DropdownMenu>
      )}
    >
      <span className="text-foreground max-w-md cursor-pointer truncate font-mono hover:text-blue-600">
        {entry.endpoint}
      </span>
    </Dropdown>
  );
};

const RequestRow: FC<{ entry: RequestLogEntry }> = ({ entry }) => {
  return (
    <TR key={entry.id}>
      <TD className="text-foreground-muted font-mono">
        {formatTime(entry.timestamp)}
      </TD>
      <TD>
        <SourceBadge source={entry.source} />
      </TD>
      <TD className="text-foreground-muted font-mono">{entry.method}</TD>
      <TD>
        <EndpointCell entry={entry} />
      </TD>
      <TD>
        <StatusBadge status={entry.status} />
      </TD>
      <TD className="text-foreground-muted text-right font-mono">
        {entry.durationMs}ms
      </TD>
      {entry.error && (
        <TD className="max-w-xs truncate text-red-600" title={entry.error}>
          {entry.error}
        </TD>
      )}
    </TR>
  );
};

export const RequestDebugPanel: FC = () => {
  const entries = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerSnapshot,
  );
  const outageActive = useSyncExternalStore(
    subscribeOutage,
    getOutageSnapshot,
    getOutageServerSnapshot,
  );
  const [expanded, setExpanded] = useState(false);
  const { isVisible } = useDebugPanelVisible();

  const toggle = useCallback(() => setExpanded((e) => !e), []);

  if (!isVisible) return null;

  return (
    <div className="bg-surface border-border-strong fixed right-0 bottom-0 left-0 z-50 border-t shadow-lg">
      {/* Header bar */}
      <div
        className="bg-surface-alt flex cursor-pointer items-center justify-between px-3 py-1.5 select-none"
        onClick={toggle}
      >
        <div className="text-foreground-muted flex items-center gap-2 text-xs">
          <span className="font-semibold">API Requests</span>
          <span className="bg-border-strong text-foreground-subtle rounded-full px-1.5 py-0.5 font-mono text-xs">
            {entries.length}
          </span>
          {!expanded && entries.length > 0 && (
            <span className="text-foreground-muted ml-1">
              last: {entries[entries.length - 1].method}{" "}
              {entries[entries.length - 1].endpoint}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <div onClick={(e) => e.stopPropagation()}>
            <Button
              size="sm"
              theme="tertiary"
              onClick={() => setOutageSimulated(!outageActive)}
            >
              {outageActive ? (
                <span className="font-semibold text-red-600 dark:text-red-400">
                  API Outage: ON
                </span>
              ) : (
                "API Outage: OFF"
              )}
            </Button>
          </div>
          {entries.length > 0 && (
            <div onClick={(e) => e.stopPropagation()}>
              <Button size="sm" theme="tertiary" onClick={clearEntries}>
                Clear
              </Button>
            </div>
          )}
          <span className="text-foreground-muted text-xs">
            {expanded ? "▼" : "▲"}
          </span>
        </div>
      </div>

      {/* Expanded table */}
      {expanded && (
        <div className="max-h-64 overflow-y-auto">
          {entries.length === 0 ? (
            <div className="text-foreground-muted px-3 py-4 text-center text-xs">
              No requests captured yet
            </div>
          ) : (
            <Table theme="inner">
              <TableHeader>
                <TH>Time</TH>
                <TH>Source</TH>
                <TH>Method</TH>
                <TH>Endpoint</TH>
                <TH>Status</TH>
                <TH className="text-right">Duration</TH>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <RequestRow key={entry.id} entry={entry} />
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </div>
  );
};
