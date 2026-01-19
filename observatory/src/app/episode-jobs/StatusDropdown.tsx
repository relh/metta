'use client'
import { parseAsString, useQueryState } from 'nuqs'
import { FC, useTransition } from 'react'

import { Spinner } from '@/components/Spinner'
import { ALL_JOB_STATUSES, JobStatus } from '@/lib/repo'

export const StatusDropdown: FC = () => {
  const [isPending, startTransition] = useTransition()

  const [status, setStatus] = useQueryState(
    'status',
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )
  return (
    <div className="flex items-center gap-3">
      <select
        value={status}
        onChange={(e) => setStatus(e.target.value as JobStatus | '')}
        className="rounded border h-8 border-gray-300 bg-white text-gray-800 text-sm py-1 px-2"
      >
        <option value="">All Statuses</option>
        {ALL_JOB_STATUSES.map((status) => (
          <option key={status} value={status}>
            {status}
          </option>
        ))}
      </select>
      {isPending && <Spinner />}
    </div>
  )
}
