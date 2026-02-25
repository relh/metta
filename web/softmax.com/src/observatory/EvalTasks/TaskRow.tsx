import clsx from "clsx";
import { FC, Fragment, use, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { A } from "@observatory/components/A";
import { Spinner } from "@observatory/components/Spinner";
import { StyledLink } from "@observatory/components/StyledLink";
import { Table, TD, TH, TR } from "@observatory/components/Table";
import { TaskBadge } from "@observatory/components/TaskBadge";
import { UserDisplay } from "@observatory/components/UserDisplay";
import { EvalTask, PolicyVersionRow, TaskAttempt } from "@observatory/lib/repo";
import { formatDate, formatDurationBetween } from "@observatory/utils/datetime";

import { policyVersionRoute } from "../lib/routes";
import { TaskAttemptTimeline } from "./TaskAttemptTimeline";
import { parsePolicyVersionId } from "./TasksTable";

type DatadogLogsParams = {
  assignee: string | null;
  assigned_at: string | null;
  finished_at: string | null;
};

function getDatadogLogsUrl(params: DatadogLogsParams): string | null {
  if (!params.assignee || !params.assigned_at) {
    return null;
  }

  const assignedAt = new Date(params.assigned_at).getTime();
  const fromTs = assignedAt - 60 * 60 * 1000;
  const toTs = params.finished_at
    ? new Date(params.finished_at).getTime() + 60 * 60 * 1000
    : assignedAt + 3 * 60 * 60 * 1000;

  const urlParams = new URLSearchParams({
    query: `pod_name:${params.assignee}`,
    agg_m: "count",
    agg_m_source: "base",
    agg_t: "count",
    cols: "host,service",
    fromUser: "true",
    messageDisplay: "inline",
    refresh_mode: "sliding",
    storage: "hot",
    stream_sort: "time_ascending",
    viz: "stream",
    from_ts: fromTs.toString(),
    to_ts: toTs.toString(),
    live: "true",
  });

  return `https://app.datadoghq.com/logs?${urlParams.toString()}`;
}

type TaskRowProps = {
  task: EvalTask;
  policyInfoMap: Record<string, PolicyVersionRow>;
  attemptedPolicyIds: Set<string>;
};

function parseRecipe(command: string): string | null {
  const match = command.match(/run\.py\s+(\S+)/);
  if (match) {
    return match[1].replace(/^recipes\.(experiment|prod)\./, "");
  }
  return null;
}

export const TaskRow: FC<TaskRowProps> = ({
  task,
  policyInfoMap,
  attemptedPolicyIds,
}) => {
  const { repo } = use(AppContext);
  const [isExpanded, setIsExpanded] = useState(false);

  // UI state
  const [attempts, setAttempts] = useState<TaskAttempt[]>([]);
  const [isLoadingAttempts, setIsLoadingAttempts] = useState(false);

  const toggleTaskExpansion = async () => {
    if (isExpanded) {
      setIsExpanded(false);
    } else {
      if (attempts.length === 0 && !isLoadingAttempts) {
        setIsLoadingAttempts(true);
        try {
          const response = await repo.getTaskAttempts(task.id);
          setAttempts(response.attempts);
        } catch (err) {
          console.error("Failed to load attempts:", err);
        } finally {
          setIsLoadingAttempts(false);
        }
      }
      setIsExpanded(true);
    }
  };

  const taskDatadogUrl = getDatadogLogsUrl(task);
  const policyVersionId = parsePolicyVersionId(task.command);
  const policyInfo = policyVersionId ? policyInfoMap[policyVersionId] : null;
  const hasAttemptedPolicy = policyVersionId
    ? attemptedPolicyIds.has(policyVersionId)
    : true;

  return (
    <Fragment>
      <TR
        className={clsx("cursor-pointer", "hover:bg-surface-alt")}
        onClick={() => toggleTaskExpansion()}
      >
        <TD>
          <span className="text-foreground-muted group-hover:text-foreground-muted mr-2 text-base">
            {isExpanded ? "▾" : isLoadingAttempts ? <Spinner size="sm" /> : "▸"}
          </span>
          {policyInfo ? (
            <StyledLink href={policyVersionRoute(policyVersionId!)}>
              {policyInfo.name}:v{policyInfo.version}
            </StyledLink>
          ) : policyVersionId && !hasAttemptedPolicy ? (
            <span className="text-foreground-muted text-xs">Loading...</span>
          ) : (
            "-"
          )}
        </TD>
        <TD>
          <UserDisplay user={task.user} userId={task.user_id} />
        </TD>
        <TD className="truncate" title={task.command}>
          {parseRecipe(task.command) || "-"}
        </TD>
        <TD>
          <TaskBadge task={task} />
        </TD>
        <TD>{formatDate(task.created_at)}</TD>
        <TD>
          {formatDurationBetween(task.created_at, task.finished_at) || "-"}
        </TD>
        <TD>
          <div className="flex items-center gap-1">
            {taskDatadogUrl ? (
              <A
                href={taskDatadogUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Datadog
              </A>
            ) : null}
            {taskDatadogUrl && task.output_log_path ? (
              <span className="text-foreground-muted">|</span>
            ) : null}
            {task.output_log_path ? (
              <A
                href={repo.getTaskLogUrl(task.id, "output")}
                target="_blank"
                rel="noopener noreferrer"
              >
                Output
              </A>
            ) : null}
            {!task.output_log_path && !taskDatadogUrl ? "-" : null}
          </div>
        </TD>
      </TR>
      {isExpanded && (
        <TR>
          <TD colSpan={7} className="bg-surface-alt p-4">
            <div className="text-foreground-muted mb-2 text-xs">
              Task ID: {task.id}
            </div>
            <div className="text-foreground-subtle mb-3 font-mono text-xs break-all">
              {task.command}
            </div>
            {isLoadingAttempts ? (
              <div>Loading attempts...</div>
            ) : (
              <Table theme="light">
                <Table.Header>
                  <TH>Attempt</TH>
                  <TH>Status</TH>
                  <TH>Assignee</TH>
                  <TH>Timeline</TH>
                  <TH>Logs</TH>
                </Table.Header>
                <Table.Body>
                  {attempts.map((attempt) => {
                    const ddUrl = getDatadogLogsUrl(attempt);
                    return (
                      <TR key={attempt.id}>
                        <TD>{attempt.attempt_number + 1}</TD>
                        <TD>
                          <TaskBadge task={attempt} size="small" />
                        </TD>
                        <TD>{attempt.assignee || "-"}</TD>
                        <TD>
                          <TaskAttemptTimeline task={task} attempt={attempt} />
                        </TD>
                        <TD>
                          <div className="flex items-center gap-1">
                            {ddUrl ? (
                              <A
                                href={ddUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Datadog
                              </A>
                            ) : null}
                            {ddUrl && attempt.output_log_path ? (
                              <span className="text-foreground-muted">|</span>
                            ) : null}
                            {attempt.output_log_path ? (
                              <A
                                href={repo.getTaskLogUrl(task.id, "output")}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                Output
                              </A>
                            ) : null}
                            {!attempt.output_log_path && !ddUrl ? "-" : null}
                          </div>
                        </TD>
                      </TR>
                    );
                  })}
                </Table.Body>
              </Table>
            )}
          </TD>
        </TR>
      )}
    </Fragment>
  );
};
