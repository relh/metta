import clsx from 'clsx'
import { FC } from 'react'

import { JobStatus } from '@/lib/repo'

export const StatusBadge: FC<{ status: JobStatus }> = ({ status }) => {
  const colors: Record<JobStatus, string> = {
    pending: 'bg-gray-100 text-gray-800',
    dispatched: 'bg-blue-100 text-blue-800',
    running: 'bg-yellow-100 text-yellow-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }
  return <span className={clsx('px-2 py-1 rounded text-xs font-medium', colors[status])}>{status}</span>
}
