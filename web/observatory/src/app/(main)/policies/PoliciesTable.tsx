import { FC } from 'react'

import { PaginatedControls } from '@/components/PaginatedControls'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { UserDisplay } from '@/components/UserDisplay'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatDate, formatRelativeTime } from '@/utils/datetime'

export const PoliciesTable: FC<{ nameFilter?: string; page?: number }> = async ({ nameFilter, page = 0 }) => {
  const repo = await getRepo()

  const pageSize = 50
  const response = await repo.getPolicies({
    limit: pageSize,
    offset: page * pageSize,
    name_fuzzy: nameFilter || undefined,
  })
  const policies = response.entries

  return (
    <div className="overflow-x-auto">
      <ServerDebugDrain />
      <Table>
        <TableHeader>
          <TH>Name</TH>
          <TH>User</TH>
          <TH>Versions</TH>
          <TH>Created</TH>
        </TableHeader>
        <TableBody>
          {policies.map((policy) => (
            <TR key={policy.id}>
              <TD>
                <StyledLink href={`/policies/${policy.id}`} className="font-medium">
                  {policy.name}
                </StyledLink>
              </TD>
              <TD>
                <UserDisplay user={policy.user} userId={policy.user_id} />
              </TD>
              <TD>
                <span className="inline-flex items-center px-2 py-1 text-xs rounded bg-surface-alt border border-border text-nowrap">
                  {policy.version_count} version{policy.version_count !== 1 ? 's' : ''}
                </span>
              </TD>
              <TD title={formatDate(policy.created_at)}>{formatRelativeTime(policy.created_at)}</TD>
            </TR>
          ))}
        </TableBody>
      </Table>
      {policies.length === 0 && <div className="p-5 text-center text-foreground-muted">No policies found</div>}
      <PaginatedControls isLastPage={policies.length < pageSize} />
    </div>
  )
}
