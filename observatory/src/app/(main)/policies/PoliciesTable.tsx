import { FC } from 'react'

import { PaginatedControls } from '@/components/PaginatedControls'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
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
      <Table>
        <TableHeader>
          <TH>Name</TH>
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
                <span className="inline-flex items-center px-2 py-1 text-xs rounded bg-gray-100 border border-gray-200 text-nowrap">
                  {policy.version_count} version{policy.version_count !== 1 ? 's' : ''}
                </span>
              </TD>
              <TD title={formatDate(policy.created_at)}>{formatRelativeTime(policy.created_at)}</TD>
            </TR>
          ))}
        </TableBody>
      </Table>
      {policies.length === 0 && <div className="p-5 text-center text-gray-500">No policies found</div>}
      <PaginatedControls isLastPage={policies.length < pageSize} />
    </div>
  )
}
