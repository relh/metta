'use client'
import { FC } from 'react'

export const MatchStatusBadge: FC<{ status: string }> = ({ status }) => {
  const colors: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-800',
    scheduled: 'bg-blue-100 text-blue-800',
    running: 'bg-yellow-100 text-yellow-800',
    completed: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
  }
  return <span className={`px-2 py-1 rounded text-xs font-medium ${colors[status] || 'bg-gray-100'}`}>{status}</span>
}
