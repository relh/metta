import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatDate, formatRelativeTime } from '@/utils/datetime'

import { DeleteServiceAccountButton } from './DeleteServiceAccountButton'

export const ServiceAccountsTable = async () => {
  const repo = await getRepo()
  const serviceAccounts = await repo.listServiceAccounts()

  return (
    <div className="overflow-x-auto">
      <ServerDebugDrain />
      <Table>
        <TableHeader>
          <TH className="w-4/12">Name</TH>
          <TH className="w-3/12">Token Preview</TH>
          <TH className="w-3/12">Created</TH>
          <TH className="w-2/12">Actions</TH>
        </TableHeader>
        <TableBody>
          {serviceAccounts.map((sa) => (
            <TR key={sa.id}>
              <TD className="align-middle font-medium">{sa.name}</TD>
              <TD className="align-middle">
                <code className="text-xs font-mono text-foreground-muted bg-surface-alt px-1 py-0.5 rounded">
                  {sa.token_preview}
                </code>
              </TD>
              <TD className="align-middle">
                <span title={formatDate(sa.created_at)}>{formatRelativeTime(sa.created_at)}</span>
              </TD>
              <TD className="align-middle">
                <DeleteServiceAccountButton id={sa.id} name={sa.name} />
              </TD>
            </TR>
          ))}
        </TableBody>
      </Table>
      {serviceAccounts.length === 0 && (
        <div className="p-5 text-center text-foreground-muted">No service accounts found</div>
      )}
    </div>
  )
}
