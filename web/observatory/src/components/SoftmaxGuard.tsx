'use client'
import { FC, PropsWithChildren, use } from 'react'

import { AppContext } from '@/app/(main)/AppContext'

export const AccessDenied: FC = () => {
  return (
    <div className="flex items-center justify-center min-h-[60vh]">
      <div className="text-center max-w-md">
        <h1 className="text-2xl font-semibold text-foreground mb-3">Access Restricted</h1>
        <p className="text-foreground-muted">This page is only available to Softmax team members.</p>
      </div>
    </div>
  )
}

export const SoftmaxGuard: FC<PropsWithChildren> = ({ children }) => {
  const { isSoftmaxTeamMember } = use(AppContext)

  if (!isSoftmaxTeamMember) {
    return <AccessDenied />
  }

  return children
}
