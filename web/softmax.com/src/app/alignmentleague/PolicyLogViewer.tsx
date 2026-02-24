"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type PolicyLogViewerProps = {
  jobId: string;
};

type LogState = {
  status: "idle" | "loading" | "loaded" | "error";
  files: string[];
  error?: string;
};

export function PolicyLogViewer({ jobId }: PolicyLogViewerProps) {
  const [logState, setLogState] = useState<LogState>({
    status: "idle",
    files: [],
  });
  const [isOpen, setIsOpen] = useState(false);
  const [selectedLog, setSelectedLog] = useState<{
    idx: number;
    content: string;
  } | null>(null);
  const [loadingLog, setLoadingLog] = useState<number | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const logStateRef = useRef(logState);
  logStateRef.current = logState;

  const fetchLogs = useCallback(async () => {
    const status = logStateRef.current.status;
    if (status === "loading" || status === "loaded") return;
    setLogState({ status: "loading", files: [] });
    try {
      const res = await fetch(`/api/jobs/${jobId}/policy-logs`);
      if (!res.ok) {
        throw new Error("Failed to fetch logs");
      }
      const files: string[] = await res.json();
      setLogState({ status: "loaded", files });
    } catch (err) {
      setLogState({
        status: "error",
        files: [],
        error: err instanceof Error ? err.message : "Failed to load",
      });
    }
  }, [jobId]);

  const handleClick = useCallback(() => {
    setIsOpen((prev) => {
      if (!prev) {
        fetchLogs();
      }
      return !prev;
    });
  }, [fetchLogs]);

  const fetchLogContent = useCallback(
    async (idx: number) => {
      setLoadingLog(idx);
      try {
        const res = await fetch(`/api/jobs/${jobId}/policy-logs/${idx}`);
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.error || "Failed to fetch log");
        }
        const content = await res.text();
        setSelectedLog({ idx, content });
      } catch (err) {
        console.error("Failed to fetch log:", err);
      } finally {
        setLoadingLog(null);
      }
    },
    [jobId],
  );

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen]);

  const parseAgentIdx = (filename: string): number | null => {
    const match = filename.match(/policy_agent_(\d+)\.txt/);
    return match ? parseInt(match[1], 10) : null;
  };

  return (
    <div ref={dropdownRef} className="relative">
      <button
        onClick={handleClick}
        className="text-sm text-[#4a5f8c] underline hover:text-[#0e2758]"
      >
        Logs
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 z-20 mt-1 min-w-[140px] rounded-lg border border-[#d8d2bf] bg-[#fffef8] p-2 shadow-lg">
          {logState.status === "loading" && (
            <p className="text-xs text-[#4a5f8c]">Loading...</p>
          )}
          {logState.status === "error" && (
            <p className="text-xs text-red-500">{logState.error}</p>
          )}
          {logState.status === "loaded" && logState.files.length === 0 && (
            <p className="text-xs text-[#8a9bb8]">No logs available</p>
          )}
          {logState.status === "loaded" && logState.files.length > 0 && (
            <ul className="space-y-1">
              {logState.files.map((file) => {
                const agentIdx = parseAgentIdx(file);
                return (
                  <li key={file}>
                    <button
                      onClick={() =>
                        agentIdx !== null && fetchLogContent(agentIdx)
                      }
                      disabled={loadingLog !== null}
                      className="w-full text-left text-xs text-[#4a5f8c] hover:text-[#0e2758] disabled:opacity-50"
                    >
                      {loadingLog === agentIdx
                        ? "Loading..."
                        : `Agent ${agentIdx}`}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

      {selectedLog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setSelectedLog(null)}
        >
          <div
            className="relative max-h-[80vh] w-full max-w-4xl overflow-auto rounded-lg bg-white p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold">
                Agent {selectedLog.idx} Log
              </h3>
              <button
                onClick={() => setSelectedLog(null)}
                className="rounded px-2 py-1 text-gray-500 hover:bg-gray-100"
              >
                Close
              </button>
            </div>
            <pre className="overflow-auto rounded bg-gray-50 p-4 text-xs">
              {selectedLog.content}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
