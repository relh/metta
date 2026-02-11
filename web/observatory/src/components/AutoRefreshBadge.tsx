'use client'
import { FC } from 'react'

import { useAutoRefreshInterval } from './AutoRefreshProvider'

export const AutoRefreshBadge: FC = () => {
  const intervalMs = useAutoRefreshInterval()

  if (intervalMs === null) return null

  const label = `${intervalMs / 1000}s`

  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300 font-mono">
      ↻ {label}
    </span>
  )
}
