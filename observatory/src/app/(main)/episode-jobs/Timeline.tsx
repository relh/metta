import clsx from 'clsx'
import { FC } from 'react'

import { JobRequest } from '@/lib/repo'
import { formatDate, formatDurationBetween } from '@/utils/datetime'

function getTimeDiffColor(from: string | null, to: string | null): string {
  if (!from || !to) return ''
  const fromTs = new Date(from).getTime()
  const toTs = new Date(to).getTime()
  const seconds = Math.floor((toTs - fromTs) / 1000)
  if (seconds < 10) return 'text-green-600'
  if (seconds < 60) return 'text-yellow-600'
  return 'text-red-500'
}

// TODO - consolidate with TaskAttemptTimeline
export const Timeline: FC<{ job: JobRequest }> = ({ job }) => {
  const dispatchedDiff = formatDurationBetween(job.created_at, job.dispatched_at)
  const runningDiff = formatDurationBetween(job.dispatched_at, job.running_at)
  const completedDiff = formatDurationBetween(job.running_at, job.completed_at)

  return (
    <table className="text-xs">
      <tbody>
        <tr>
          <td className="pr-2 text-gray-600">Created:</td>
          <td className="text-right">{formatDate(job.created_at)}</td>
          <td className="pl-2 w-16"></td>
        </tr>
        <tr>
          <td className="pr-2 text-gray-600">Dispatched:</td>
          <td className="text-right">{formatDate(job.dispatched_at)}</td>
          <td className={clsx('pl-2 text-right', getTimeDiffColor(job.created_at, job.dispatched_at))}>
            {dispatchedDiff ? `+${dispatchedDiff}` : ''}
          </td>
        </tr>
        <tr>
          <td className="pr-2 text-gray-600">Running:</td>
          <td className="text-right">{formatDate(job.running_at)}</td>
          <td className={clsx('pl-2 text-right', getTimeDiffColor(job.dispatched_at, job.running_at))}>
            {runningDiff ? `+${runningDiff}` : ''}
          </td>
        </tr>
        <tr>
          <td className="pr-2 text-gray-600">Completed:</td>
          <td className="text-right">{formatDate(job.completed_at)}</td>
          <td className={clsx('pl-2 text-right', getTimeDiffColor(job.running_at, job.completed_at))}>
            {completedDiff ? `+${completedDiff}` : ''}
          </td>
        </tr>
      </tbody>
    </table>
  )
}
