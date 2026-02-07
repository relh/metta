'use client'
import { FC } from 'react'

import { UserRow } from '@/lib/repo'

import { Tooltip } from './Tooltip'

export const UserDisplay: FC<{ user: UserRow | null; userId: string }> = ({ user, userId }) => {
  const displayName = user?.name ?? userId

  return (
    <Tooltip
      placement="bottom-start"
      render={() => (
        <div className="flex flex-col gap-1 text-xs min-w-[160px]">
          <div className="font-mono text-gray-500">{userId}</div>
          {user?.name && <div className="font-medium text-gray-900">{user.name}</div>}
          {user?.email && <div className="text-gray-600">{user.email}</div>}
          {user?.is_softmax_team_member && (
            <span className="inline-flex items-center self-start px-1.5 py-0.5 rounded bg-blue-50 border border-blue-200 text-blue-700 text-[10px] font-medium">
              Softmax Team
            </span>
          )}
        </div>
      )}
    >
      <span className="text-gray-700 cursor-default">{displayName}</span>
    </Tooltip>
  )
}
