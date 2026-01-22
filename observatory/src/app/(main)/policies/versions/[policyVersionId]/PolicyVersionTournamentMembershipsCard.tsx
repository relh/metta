import clsx from 'clsx'
import { FC } from 'react'

import { Card } from '@/components/Card'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { getRepo } from '@/lib/repo/server'
import { formatRelativeTime } from '@/utils/datetime'

export const ActionBadge: FC<{ action: string }> = ({ action }) => {
  const colors: Record<string, string> = {
    add: 'bg-green-100 text-green-800',
    remove: 'bg-gray-100 text-gray-600',
  }
  return (
    <span className={clsx('px-2 py-1 rounded text-xs font-medium', colors[action] || 'bg-gray-100')}>{action}</span>
  )
}

export const PolicyVersionTournamentMembershipsCard: FC<{ policyVersionId: string }> = async ({ policyVersionId }) => {
  const repo = await getRepo()
  const memberships = await repo.getPolicyMemberships(policyVersionId)

  return (
    <Card title="Tournament Memberships">
      {memberships.length === 0 ? (
        <div className="text-gray-500 text-sm">No tournament memberships found for this policy version.</div>
      ) : (
        <Table>
          <TableHeader>
            <TH>Time</TH>
            <TH>Season</TH>
            <TH>Pool</TH>
            <TH>Action</TH>
            <TH>Notes</TH>
          </TableHeader>
          <TableBody>
            {memberships.map((entry, i) => (
              <TR key={i}>
                <TD className="text-gray-500 text-sm">{formatRelativeTime(entry.created_at)}</TD>
                <TD>
                  <StyledLink href={`/tournament/${entry.season_name}`}>{entry.season_name}</StyledLink>
                </TD>
                <TD className="capitalize">{entry.pool_name}</TD>
                <TD>
                  <ActionBadge action={entry.action} />
                </TD>
                <TD className="text-sm text-gray-600">{entry.notes || '-'}</TD>
              </TR>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  )
}
