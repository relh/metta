import { FC } from 'react'

import { Card } from '@/components/Card'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'

import { MembershipHistoryTable } from './MembershipHistoryTable'

export const PolicyVersionTournamentMembershipsCard: FC<{ policyVersionId: string }> = async ({ policyVersionId }) => {
  const repo = await getRepo()
  const memberships = await repo.getPolicyMemberships(policyVersionId)

  return (
    <Card title="Tournament Memberships">
      <ServerDebugDrain />
      {memberships.length === 0 ? (
        <div className="text-foreground-muted text-sm">No tournament memberships found for this policy version.</div>
      ) : (
        <MembershipHistoryTable memberships={memberships} />
      )}
    </Card>
  )
}
