'use client'
import { FC } from 'react'

export const MatchStatusBadge: FC<{ status: string }> = ({ status }) => {
  const colors: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-800 dark:bg-gray-800/50 dark:text-gray-300',
    scheduled: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
    running: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
    completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    failed: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
  }
  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || 'bg-gray-100 dark:bg-gray-800/50'}`}>
      {status}
    </span>
  )
}
