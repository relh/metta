import clsx from "clsx";
import { FC } from "react";

import { EvalTask, TaskAttempt, TaskStatus } from "../lib/repo";
import { Tooltip } from "./Tooltip";

function getStatusColor(status: TaskStatus) {
  switch (status) {
    case "done":
      return "#28a745";
    case "error":
    case "system_error":
      return "#dc3545";
    case "unprocessed":
      return "#6c757d";
    case "running":
      return "#17a2b8";
    case "canceled":
      return "#ffc107";
    default:
      return "#6c757d";
  }
}

export const TaskBadge: FC<{
  task: EvalTask | TaskAttempt;
  size?: "small" | "medium";
}> = ({ task, size = "medium" }) => {
  const errorReason = task.status_details?.error_reason;
  const result = (
    <span
      className={clsx(
        size === "small"
          ? "rounded-sm px-1.5 py-0.5 text-xs"
          : "rounded-[3px] px-2 py-1 text-xs",
        "text-white",
        errorReason && "cursor-pointer",
      )}
      style={{
        backgroundColor: getStatusColor(task.status),
      }}
    >
      {task.status}
    </span>
  );
  if (errorReason) {
    return (
      <Tooltip
        render={() => <div className="max-w-md text-xs">{errorReason}</div>}
      >
        {result}
      </Tooltip>
    );
  } else {
    return result;
  }
};
