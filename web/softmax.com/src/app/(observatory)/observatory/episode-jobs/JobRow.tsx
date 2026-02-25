"use client";
import { FC, useCallback, useEffect, useRef, useState } from "react";

import {
  normalizeReplayUrl,
  normalizeVibescopeUrl,
} from "@observatory/components/ReplayViewer";
import { StyledLink } from "@observatory/components/StyledLink";
import { TD, TR } from "@observatory/components/Table";
import {
  METTA_GITHUB_ORGANIZATION,
  METTA_GITHUB_REPO,
} from "@observatory/constants";
import { JobRequest } from "@observatory/lib/repo";
import { episodeRoute, seasonRoute } from "@observatory/lib/routes";
import {
  formatDurationBetween,
  formatDurationSince,
} from "@observatory/utils/datetime";

import { LabelRow, LabelValueTable } from "./LabelValueTable";
import { PolicyLink } from "./PolicyLink";
import { StatusBadge } from "./StatusBadge";
import { Timeline } from "./Timeline";

const MAX_VISIBLE_TAGS = 2;

const TagPill: FC<{ k: string; v: string; truncate?: boolean }> = ({
  k,
  v,
  truncate,
}) => (
  <span
    className={`bg-surface-alt text-foreground-muted rounded-full px-1 py-0.5 text-[10px] whitespace-nowrap ${truncate ? "inline-block max-w-[180px] truncate" : ""}`}
    title={`${k}: ${v}`}
  >
    {k}={v}
  </span>
);

const Tags: FC<{ tags: Record<string, string> }> = ({ tags }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const entries = Object.entries(tags);
  const visible = entries.slice(0, MAX_VISIBLE_TAGS);
  const overflow = entries.slice(MAX_VISIBLE_TAGS);

  return (
    <div className="relative" ref={ref}>
      <div className="flex flex-wrap items-center gap-0.5">
        {visible.map(([k, v]) => (
          <TagPill key={k} k={k} v={v} />
        ))}
        {overflow.length > 0 && (
          <button
            onClick={() => setOpen(!open)}
            className="text-foreground-muted hover:text-foreground cursor-pointer rounded-full border-none bg-transparent p-0 px-1 py-0.5 text-[10px] whitespace-nowrap"
          >
            +{overflow.length}
          </button>
        )}
      </div>
      {open && (
        <div className="bg-surface border-border absolute top-full left-0 z-10 mt-1 flex flex-col gap-0.5 rounded border p-1.5 shadow-lg">
          {entries.map(([k, v]) => (
            <TagPill key={k} k={k} v={v} truncate />
          ))}
        </div>
      )}
    </div>
  );
};

function normalizeRunnerImageRef(
  runnerImage: string | undefined,
): string | null {
  if (!runnerImage) return null;
  return runnerImage.replace(/^docker-pullable:\/\//, "");
}

function parseRequestedRunnerVersion(
  runnerImage: string | undefined,
): string | null {
  const normalized = normalizeRunnerImageRef(runnerImage);
  if (!normalized) return null;
  const digestIndex = normalized.lastIndexOf("@");
  if (digestIndex !== -1) return normalized.slice(digestIndex + 1);
  const lastSlash = normalized.lastIndexOf("/");
  const lastColon = normalized.lastIndexOf(":");
  if (lastColon <= lastSlash) return normalized.split("/").pop() ?? normalized;
  return normalized.slice(lastColon + 1);
}

const CopyButton: FC<{
  text: string;
  children: React.ReactNode;
  className?: string;
  title?: string;
}> = ({ text, children, className, title }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className={`cursor-pointer border-none bg-transparent p-0 ${className ?? ""}`}
      title={title ?? text}
    >
      {copied ? <span className="text-green-600">Copied!</span> : children}
    </button>
  );
};

function truncateValue(value: unknown, depth: number = 0): unknown {
  if (depth > 4) return "...";
  if (typeof value === "string" && value.length > 80)
    return value.slice(0, 80) + "...";
  if (Array.isArray(value)) {
    const truncated = value
      .slice(0, 10)
      .map((v) => truncateValue(v, depth + 1));
    if (value.length > 10) truncated.push(`... +${value.length - 10} more`);
    return truncated;
  }
  if (value && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      result[k] = truncateValue(v, depth + 1);
    }
    return result;
  }
  return value;
}

function fmt(v: number | null | undefined): string {
  if (v == null) return "-";
  return v.toFixed(4);
}

function formatCost(cost: number): string {
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  return `$${cost.toFixed(2)}`;
}

const ExpandDownloadRow: FC<{
  label: string;
  data: unknown;
  show: boolean;
  onToggle: () => void;
}> = ({ label, data, show, onToggle }) => (
  <LabelRow label={label}>
    <span className="flex justify-end gap-1.5">
      <button
        onClick={onToggle}
        className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
      >
        {show ? "Collapse" : "Expand"}
      </button>
      <button
        onClick={() => {
          const blob = new Blob([JSON.stringify(data, null, 2)], {
            type: "application/json",
          });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `${label.toLowerCase().replace(/\s+/g, "-")}.json`;
          a.click();
          URL.revokeObjectURL(url);
        }}
        className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
      >
        Download
      </button>
    </span>
  </LabelRow>
);

const ExpansionPanel: FC<{
  label: string;
  content: string;
  copyContent?: string;
  onClose: () => void;
}> = ({ label, content, copyContent, onClose }) => {
  const [copied, setCopied] = useState(false);
  return (
    <div className="max-w-0 min-w-full overflow-hidden">
      <div className="bg-surface-alt border-border flex items-center justify-between rounded-t border border-b-0 px-3 py-1.5">
        <span className="text-foreground-muted text-xs font-semibold">
          {label}
        </span>
        <span className="flex gap-2">
          <button
            onClick={() => {
              navigator.clipboard.writeText(copyContent ?? content);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="cursor-pointer border-none bg-transparent p-0 text-xs text-blue-600 hover:underline"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
          <button
            onClick={onClose}
            className="text-foreground-muted hover:text-foreground cursor-pointer border-none bg-transparent p-0 text-xs"
          >
            Close
          </button>
        </span>
      </div>
      <pre className="bg-surface-alt border-border text-foreground m-0 max-h-[500px] overflow-auto rounded-b border p-3 text-[11px] break-all whitespace-pre-wrap">
        {content}
      </pre>
    </div>
  );
};

function getTimeDisplay(job: JobRequest): {
  primary: string;
  secondary?: string;
} {
  if (job.status === "completed" || job.status === "failed") {
    const runDur = formatDurationBetween(job.running_at, job.completed_at);
    const overallDur = formatDurationBetween(job.created_at, job.completed_at);
    if (runDur && overallDur && runDur !== overallDur) {
      return { primary: `${runDur} running`, secondary: `${overallDur} total` };
    }
    if (runDur) return { primary: `${runDur} running` };
    if (overallDur) return { primary: overallDur };
    return { primary: "—" };
  }
  if (job.status === "running") {
    const dur = formatDurationSince(job.running_at);
    return dur ? { primary: `${dur} running` } : { primary: "—" };
  }
  if (job.status === "dispatched") {
    const dur = formatDurationSince(job.dispatched_at);
    return dur ? { primary: `${dur} waiting` } : { primary: "—" };
  }
  return { primary: "—" };
}

function computeAgentCounts(
  assignments: number[] | undefined,
): Map<number, number> {
  const counts = new Map<number, number>();
  if (!assignments) return counts;
  for (const policyIdx of assignments) {
    counts.set(policyIdx, (counts.get(policyIdx) ?? 0) + 1);
  }
  return counts;
}

export const JobRow: FC<{ job: JobRequest }> = ({ job }) => {
  const policyUris = job.job?.policy_uris as string[] | undefined;
  const assignments = job.job?.assignments as number[] | undefined;
  const agentCountsByPosition = computeAgentCounts(assignments);
  const policyVersionEntries = job.policy_versions;
  const episodeTags = job.job?.episode_tags as
    | Record<string, string>
    | undefined;
  const episodeId = job.result?.episode_id as string | undefined;
  const requestedRunnerImage = job.job?.episode_runner_image as
    | string
    | undefined;
  const actualRunnerImage = job.result?.runner_image as string | undefined;
  const actualRunnerImageId = job.result?.runner_image_id as string | undefined;
  const requestedRunnerVersion =
    parseRequestedRunnerVersion(requestedRunnerImage);
  const actualRunnerVersion = normalizeRunnerImageRef(
    actualRunnerImageId ?? actualRunnerImage,
  );
  const gitCommit = job.result?.git_commit as string | undefined;
  const instanceType = job.result?.instance_type as string | undefined;
  const capacityType = job.result?.capacity_type as string | undefined;
  const rawCost = job.result?.cost_usd;
  const costUsd = typeof rawCost === "number" ? rawCost : undefined;
  const lifecycleError = job.error;
  const [expanded, setExpanded] = useState(false);
  const [showSpec, setShowSpec] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [logs, setLogs] = useState<string | null>(null);
  const [showGameStats, setShowGameStats] = useState(false);
  const [showAgentStats, setShowAgentStats] = useState(false);
  const [traceLoading, setTraceLoading] = useState(false);
  const [setupTraceLoading, setSetupTraceLoading] = useState(false);
  const [policyLogAgentIndices, setPolicyLogAgentIndices] = useState<number[]>(
    [],
  );
  const [policyLogsLoaded, setPolicyLogsLoaded] = useState(false);
  const [expandedPolicyLogs, setExpandedPolicyLogs] = useState<
    Record<number, string>
  >({});
  const [loadingPolicyLogs, setLoadingPolicyLogs] = useState<
    Record<number, boolean>
  >({});
  const loadingPolicyLogsRef = useRef<Record<number, boolean>>({});

  const policyStatsMap = new Map(
    (job.episode?.policy_stats ?? []).map((s) => [s.policy_version_id, s]),
  );
  const attrs = job.episode?.attributes;
  const gameStats = attrs?.stats?.game;
  const agentStats = attrs?.stats?.agent;

  const timeDisplay = getTimeDisplay(job);

  // Load policy log file list when expanded
  useEffect(() => {
    if (
      expanded &&
      !policyLogsLoaded &&
      (job.status === "completed" || job.status === "failed")
    ) {
      fetch(`/api/observatory/jobs/${job.id}/policy-logs`)
        .then((r) => r.json())
        .then((files: string[]) => {
          // Parse agent indices from filenames like "policy_agent_0.txt"
          const indices = files
            .map((f) => {
              const match = f.match(/policy_agent_(\d+)\.txt/);
              return match ? parseInt(match[1], 10) : null;
            })
            .filter((i): i is number => i !== null)
            .sort((a, b) => a - b);
          setPolicyLogAgentIndices(indices);
          setPolicyLogsLoaded(true);
        })
        .catch(() => setPolicyLogsLoaded(true));
    }
  }, [expanded, policyLogsLoaded, job.id, job.status]);

  const loadPolicyLog = useCallback(
    async (agentIdx: number) => {
      if (loadingPolicyLogsRef.current[agentIdx]) return;
      loadingPolicyLogsRef.current[agentIdx] = true;
      setLoadingPolicyLogs((prev) => ({ ...prev, [agentIdx]: true }));
      try {
        const response = await fetch(
          `/api/observatory/jobs/${job.id}/policy-logs/${agentIdx}`,
        );
        if (response.ok) {
          const logContent = await response.text();
          setExpandedPolicyLogs((prev) => ({
            ...prev,
            [agentIdx]: logContent,
          }));
        }
      } finally {
        loadingPolicyLogsRef.current[agentIdx] = false;
        setLoadingPolicyLogs((prev) => ({ ...prev, [agentIdx]: false }));
      }
    },
    [job.id],
  );

  const openTraceViewer = useCallback(async () => {
    setTraceLoading(true);
    const handle = window.open("https://ui.perfetto.dev");
    if (!handle) {
      setTraceLoading(false);
      return;
    }

    const response = await fetch(`/api/jobs/${job.id}/trace`);
    if (!response.ok) {
      handle.close();
      setTraceLoading(false);
      return;
    }
    const buffer = await response.arrayBuffer();

    await new Promise<void>((resolve) => {
      const interval = setInterval(() => handle.postMessage("PING", "*"), 100);
      const cleanup = () => {
        clearInterval(interval);
        clearTimeout(timeout);
        window.removeEventListener("message", onMessage);
        resolve();
      };
      const onMessage = (e: MessageEvent) => {
        if (e.data === "PONG") cleanup();
      };
      const timeout = setTimeout(cleanup, 10000);
      window.addEventListener("message", onMessage);
    });

    handle.postMessage(
      {
        perfetto: {
          buffer,
          title: `Job ${job.id}`,
          fileName: `job-${job.id}-trace.pftrace`,
        },
      },
      "*",
    );
    setTraceLoading(false);
  }, [job.id]);

  const downloadTrace = useCallback(() => {
    fetch(`/api/jobs/${job.id}/trace`)
      .then((response) => {
        if (!response.ok) return null;
        return response.text();
      })
      .then((trace) => {
        if (!trace) return;
        const blob = new Blob([trace], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `job-${job.id}-trace.json`;
        a.click();
        URL.revokeObjectURL(url);
      });
  }, [job.id]);

  const openSetupTraceViewer = useCallback(async () => {
    setSetupTraceLoading(true);
    const handle = window.open("https://ui.perfetto.dev");
    if (!handle) {
      setSetupTraceLoading(false);
      return;
    }

    const response = await fetch(`/api/jobs/${job.id}/setup-trace`);
    if (!response.ok) {
      handle.close();
      setSetupTraceLoading(false);
      return;
    }
    const buffer = await response.arrayBuffer();

    await new Promise<void>((resolve) => {
      const interval = setInterval(() => handle.postMessage("PING", "*"), 100);
      const cleanup = () => {
        clearInterval(interval);
        clearTimeout(timeout);
        window.removeEventListener("message", onMessage);
        resolve();
      };
      const onMessage = (e: MessageEvent) => {
        if (e.data === "PONG") cleanup();
      };
      const timeout = setTimeout(cleanup, 10000);
      window.addEventListener("message", onMessage);
    });

    handle.postMessage(
      {
        perfetto: {
          buffer,
          title: `Job ${job.id} (setup)`,
          fileName: `job-${job.id}-setup-trace.pftrace`,
        },
      },
      "*",
    );
    setSetupTraceLoading(false);
  }, [job.id]);

  const downloadSetupTrace = useCallback(() => {
    fetch(`/api/jobs/${job.id}/setup-trace`)
      .then((response) => {
        if (!response.ok) return null;
        return response.text();
      })
      .then((trace) => {
        if (!trace) return;
        const blob = new Blob([trace], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `job-${job.id}-setup-trace.json`;
        a.click();
        URL.revokeObjectURL(url);
      });
  }, [job.id]);

  return (
    <>
      {/* Compact row */}
      <TR>
        <TD
          className="cursor-pointer !px-1 !py-2 text-center select-none"
          onClick={() => setExpanded(!expanded)}
        >
          <span className="text-foreground-muted text-xs">
            {expanded ? "\u25BC" : "\u25B6"}
          </span>
        </TD>
        <TD>
          <StatusBadge status={job.status} />
          {lifecycleError &&
            job.status === "failed" &&
            lifecycleError !== "Error" && (
              <div
                className="mt-0.5 max-w-[130px] truncate text-[10px] text-red-600"
                title={lifecycleError}
              >
                {lifecycleError}
              </div>
            )}
        </TD>
        <TD>
          {policyVersionEntries.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyVersionEntries.map((entry, i) => {
                const uri =
                  policyUris?.[i] ?? `metta://policy/${entry.policy.id}`;
                return (
                  <div key={`${entry.policy.id}-${entry.position}`}>
                    <PolicyLink uri={uri} policy={entry.policy} />
                  </div>
                );
              })}
            </div>
          ) : policyUris && policyUris.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyUris.map((uri, i) => (
                <div
                  key={`${uri}-${i}`}
                  className="font-mono text-xs text-wrap break-all"
                >
                  {uri}
                </div>
              ))}
            </div>
          ) : (
            <span className="text-foreground-muted">-</span>
          )}
        </TD>
        <TD>
          {policyVersionEntries.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyVersionEntries.map((entry) => {
                const stat = policyStatsMap.get(entry.policy.id);
                const specAgents = agentCountsByPosition.get(entry.position);
                const numAgents = stat?.num_agents ?? specAgents;
                return (
                  <div
                    key={`${entry.policy.id}-${entry.position}`}
                    className="font-mono text-xs"
                  >
                    {numAgents != null ? numAgents : "-"}
                  </div>
                );
              })}
            </div>
          ) : (
            <span className="text-foreground-muted">-</span>
          )}
        </TD>
        <TD>
          {policyVersionEntries.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyVersionEntries.map((entry) => {
                const stat = policyStatsMap.get(entry.policy.id);
                return (
                  <div
                    key={`${entry.policy.id}-${entry.position}`}
                    className="font-mono text-xs"
                  >
                    {stat ? fmt(stat.avg_reward) : "-"}
                  </div>
                );
              })}
            </div>
          ) : (
            <span className="text-foreground-muted">-</span>
          )}
        </TD>
        <TD>
          <div className="flex flex-col gap-0.5">
            {job.match?.season_name && (
              <StyledLink
                href={seasonRoute(job.match.season_name)}
                className="text-xs"
              >
                {job.match.season_name}
              </StyledLink>
            )}
            {job.match?.pool_name && (
              <span className="text-foreground-muted text-[10px]">
                {job.match.pool_name}
              </span>
            )}
            {episodeTags && Object.keys(episodeTags).length > 0 && (
              <Tags tags={episodeTags} />
            )}
          </div>
        </TD>
        <TD>
          <div className="text-xs">{timeDisplay.primary}</div>
          {timeDisplay.secondary && (
            <div className="text-foreground-muted text-[10px]">
              {timeDisplay.secondary}
            </div>
          )}
          {costUsd != null && costUsd > 0 && (
            <div className="text-foreground-muted text-[10px]">
              {formatCost(costUsd)} cost
            </div>
          )}
        </TD>
        <TD>
          <div className="flex flex-wrap items-center gap-0 text-xs">
            {episodeId && (
              <StyledLink href={episodeRoute(episodeId)}>Episode</StyledLink>
            )}
            {job.episode?.replay_url &&
              normalizeVibescopeUrl(job.episode.replay_url) && (
                <>
                  {episodeId && (
                    <span className="text-foreground-muted mx-1">&middot;</span>
                  )}
                  <a
                    href={normalizeVibescopeUrl(job.episode.replay_url)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    VS
                  </a>
                </>
              )}
            {job.episode?.replay_url &&
              normalizeReplayUrl(job.episode.replay_url) && (
                <>
                  <span className="text-foreground-muted mx-1">&middot;</span>
                  <a
                    href={normalizeReplayUrl(job.episode.replay_url)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 hover:underline"
                  >
                    MS
                  </a>
                </>
              )}
          </div>
        </TD>
      </TR>

      {/* Expanded detail panel */}
      {expanded && (
        <TR>
          <TD colSpan={8} className="!p-0">
            <div className="bg-surface-alt border-border grid grid-cols-[1fr_auto_1fr_auto_1fr] gap-0 border-t px-4 py-3">
              {/* Job */}
              <div className="px-3">
                <div className="text-foreground-muted mb-1.5 text-xs font-semibold tracking-wide uppercase">
                  Job
                </div>
                <LabelValueTable>
                  <LabelRow label="Job ID">
                    <CopyButton
                      text={job.id}
                      className="hover:text-foreground font-mono text-xs"
                    >
                      <span>{job.id}</span>
                    </CopyButton>
                  </LabelRow>
                  {gitCommit && (
                    <LabelRow label="Actual Runner Commit">
                      <a
                        href={`https://github.com/${METTA_GITHUB_ORGANIZATION}/${METTA_GITHUB_REPO}/commit/${gitCommit}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-xs text-blue-600 hover:underline"
                      >
                        {gitCommit.slice(0, 7)}
                      </a>
                    </LabelRow>
                  )}
                  {instanceType && (
                    <LabelRow label="Instance">
                      <span className="font-mono text-xs">
                        {instanceType}
                        {capacityType && (
                          <span className="text-foreground-muted">
                            {" "}
                            ({capacityType})
                          </span>
                        )}
                      </span>
                    </LabelRow>
                  )}
                  {costUsd != null && costUsd > 0 && (
                    <LabelRow label="Cost">
                      <span className="font-mono text-xs">
                        {formatCost(costUsd)}
                      </span>
                    </LabelRow>
                  )}
                  {requestedRunnerVersion && (
                    <LabelRow label="Requested Runner Version">
                      <CopyButton
                        text={requestedRunnerVersion}
                        className="hover:text-foreground font-mono text-xs"
                      >
                        <span>{requestedRunnerVersion}</span>
                      </CopyButton>
                    </LabelRow>
                  )}
                  {actualRunnerVersion && (
                    <LabelRow label="Actual Runner Version">
                      <CopyButton
                        text={actualRunnerVersion}
                        className="hover:text-foreground font-mono text-xs"
                      >
                        <span className="break-all">{actualRunnerVersion}</span>
                      </CopyButton>
                    </LabelRow>
                  )}
                  {job.job && (
                    <LabelRow label="Episode Spec">
                      <span className="flex justify-end gap-1.5">
                        <button
                          onClick={() => setShowSpec(!showSpec)}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
                        >
                          {showSpec ? "Collapse" : "Expand"}
                        </button>
                        <button
                          onClick={() => {
                            const blob = new Blob(
                              [JSON.stringify(job.job, null, 2)],
                              { type: "application/json" },
                            );
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `job-${job.id}.json`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  <LabelRow label="Local reproduce command">
                    <CopyButton
                      text={`./tools/run.py recipes.experiment.episode_runner.repro source=${job.id}`}
                      className="text-blue-600 hover:underline"
                      title="Copy local repro command"
                    >
                      <span>Copy</span>
                    </CopyButton>
                  </LabelRow>
                </LabelValueTable>
              </div>
              <div className="bg-border w-px" />
              {/* Timing */}
              <div className="px-3">
                <div className="text-foreground-muted mb-1.5 text-xs font-semibold tracking-wide uppercase">
                  Timing
                </div>
                <Timeline job={job} />
              </div>
              <div className="bg-border w-px" />
              {/* Results */}
              <div className="px-3">
                <div className="text-foreground-muted mb-1.5 text-xs font-semibold tracking-wide uppercase">
                  Results
                </div>
                <LabelValueTable>
                  {gameStats && (
                    <ExpandDownloadRow
                      label="Game Stats"
                      data={gameStats}
                      show={showGameStats}
                      onToggle={() => setShowGameStats(!showGameStats)}
                    />
                  )}
                  {agentStats && (
                    <ExpandDownloadRow
                      label="Agent Stats"
                      data={agentStats}
                      show={showAgentStats}
                      onToggle={() => setShowAgentStats(!showAgentStats)}
                    />
                  )}
                  {(job.status === "completed" || job.status === "failed") && (
                    <LabelRow label="Trace">
                      <span className="flex justify-end gap-1.5">
                        <button
                          onClick={openTraceViewer}
                          disabled={traceLoading}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline disabled:cursor-default disabled:opacity-50"
                        >
                          {traceLoading ? (
                            <span className="inline-flex items-center gap-1">
                              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
                              Loading
                            </span>
                          ) : (
                            "View"
                          )}
                        </button>
                        <button
                          onClick={downloadTrace}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  {(job.status === "completed" || job.status === "failed") && (
                    <LabelRow label="Setup Trace">
                      <span className="flex justify-end gap-1.5">
                        <button
                          onClick={openSetupTraceViewer}
                          disabled={setupTraceLoading}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline disabled:cursor-default disabled:opacity-50"
                        >
                          {setupTraceLoading ? (
                            <span className="inline-flex items-center gap-1">
                              <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
                              Loading
                            </span>
                          ) : (
                            "View"
                          )}
                        </button>
                        <button
                          onClick={downloadSetupTrace}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  {(job.status === "completed" || job.status === "failed") && (
                    <LabelRow label="Logs">
                      <span className="flex justify-end gap-1.5">
                        <button
                          onClick={() => {
                            if (!showLogs && logs === null) {
                              fetch(`/api/jobs/${job.id}/logs`)
                                .then((r) => r.text())
                                .then((text) => {
                                  setLogs(text);
                                  setShowLogs(true);
                                });
                            } else {
                              setShowLogs(!showLogs);
                            }
                          }}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
                        >
                          {showLogs ? "Collapse" : "Expand"}
                        </button>
                        <button
                          onClick={() => {
                            const doDownload = (text: string) => {
                              const blob = new Blob([text], {
                                type: "text/plain",
                              });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement("a");
                              a.href = url;
                              a.download = `job-${job.id}-logs.txt`;
                              a.click();
                              URL.revokeObjectURL(url);
                            };
                            if (logs !== null) {
                              doDownload(logs);
                            } else {
                              fetch(`/api/jobs/${job.id}/logs`)
                                .then((r) => r.text())
                                .then((text) => {
                                  setLogs(text);
                                  doDownload(text);
                                });
                            }
                          }}
                          className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  {policyLogAgentIndices.map((agentIdx) => {
                    const isExpanded =
                      expandedPolicyLogs[agentIdx] !== undefined;
                    const isLoading = loadingPolicyLogs[agentIdx];
                    return (
                      <LabelRow
                        key={`policy-logs-${agentIdx}`}
                        label={`Agent ${agentIdx} Log`}
                      >
                        <span className="flex justify-end gap-1.5">
                          <button
                            onClick={() => {
                              if (!isExpanded) {
                                loadPolicyLog(agentIdx);
                              } else {
                                setExpandedPolicyLogs((prev) => {
                                  const next = { ...prev };
                                  delete next[agentIdx];
                                  return next;
                                });
                              }
                            }}
                            disabled={isLoading}
                            className="cursor-pointer border-none bg-transparent p-0 text-blue-600 hover:underline disabled:opacity-50"
                          >
                            {isLoading
                              ? "Loading..."
                              : isExpanded
                                ? "Collapse"
                                : "Expand"}
                          </button>
                        </span>
                      </LabelRow>
                    );
                  })}
                  {lifecycleError && (
                    <LabelRow label="Error">
                      <span
                        className="text-xs text-red-600"
                        title={lifecycleError}
                      >
                        {lifecycleError}
                      </span>
                    </LabelRow>
                  )}
                </LabelValueTable>
              </div>
            </div>
          </TD>
        </TR>
      )}

      {/* Expansion rows */}
      {expanded && showLogs && logs !== null && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Logs"
              content={logs}
              onClose={() => setShowLogs(false)}
            />
          </TD>
        </TR>
      )}
      {expanded && showSpec && job.job && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Episode Spec"
              content={JSON.stringify(truncateValue(job.job), null, 2)}
              copyContent={JSON.stringify(job.job, null, 2)}
              onClose={() => setShowSpec(false)}
            />
          </TD>
        </TR>
      )}
      {expanded && showGameStats && gameStats && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Game Stats"
              content={JSON.stringify(gameStats, null, 2)}
              onClose={() => setShowGameStats(false)}
            />
          </TD>
        </TR>
      )}
      {expanded && showAgentStats && agentStats && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Agent Stats"
              content={JSON.stringify(agentStats, null, 2)}
              onClose={() => setShowAgentStats(false)}
            />
          </TD>
        </TR>
      )}
      {expanded &&
        Object.entries(expandedPolicyLogs).map(([agentIdxStr, logContent]) => {
          const agentIdx = parseInt(agentIdxStr, 10);
          return (
            <TR key={`policy-logs-panel-${agentIdx}`}>
              <TD colSpan={8} className="!p-2">
                <ExpansionPanel
                  label={`Agent ${agentIdx} Log`}
                  content={logContent || "<empty>"}
                  onClose={() =>
                    setExpandedPolicyLogs((prev) => {
                      const next = { ...prev };
                      delete next[agentIdx];
                      return next;
                    })
                  }
                />
              </TD>
            </TR>
          );
        })}
    </>
  );
};
