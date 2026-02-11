'use client'
import clsx from 'clsx'
import { FC } from 'react'

import { useAutoRefreshInterval } from './AutoRefreshProvider'

export const AutoRefreshBadge: FC = () => {
  const intervalMs = useAutoRefreshInterval()

  const label = intervalMs !== null ? `${intervalMs / 1000}s` : null

  return (
    <span
      className={clsx(
        'text-xs px-1.5 py-0.5 rounded font-mono min-w-10 text-center',
        label !== null ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300' : 'invisible'
      )}
    >
      {label !== null && `↻ ${label}`}
    </span>
  )
}
