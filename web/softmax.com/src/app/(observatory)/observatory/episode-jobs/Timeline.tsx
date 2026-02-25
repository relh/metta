import clsx from "clsx";
import { FC } from "react";

import { JobRequest } from "@observatory/lib/repo";
import { formatDate, formatDurationBetween } from "@observatory/utils/datetime";

import { LabelRow, LabelValueTable } from "./LabelValueTable";

function getTimeDiffColor(from: string | null, to: string | null): string {
  if (!from || !to) return "";
  const fromTs = new Date(from).getTime();
  const toTs = new Date(to).getTime();
  const seconds = Math.floor((toTs - fromTs) / 1000);
  if (seconds < 10) return "text-green-600";
  if (seconds < 60) return "text-yellow-600";
  return "text-red-500";
}

const TimeDiff: FC<{ from: string | null; to: string | null }> = ({
  from,
  to,
}) => {
  const diff = formatDurationBetween(from, to);
  return (
    <span className={clsx(getTimeDiffColor(from, to))}>
      {diff ? `+${diff}` : ""}
    </span>
  );
};

export const Timeline: FC<{ job: JobRequest }> = ({ job }) => (
  <LabelValueTable>
    <LabelRow label="Created" extra="">
      {formatDate(job.created_at)}
    </LabelRow>
    <LabelRow
      label="Dispatched"
      extra={<TimeDiff from={job.created_at} to={job.dispatched_at} />}
    >
      {formatDate(job.dispatched_at)}
    </LabelRow>
    <LabelRow
      label="Running"
      extra={<TimeDiff from={job.dispatched_at} to={job.running_at} />}
    >
      {formatDate(job.running_at)}
    </LabelRow>
    <LabelRow
      label="Completed"
      extra={<TimeDiff from={job.running_at} to={job.completed_at} />}
    >
      {formatDate(job.completed_at)}
    </LabelRow>
  </LabelValueTable>
);
