import { Card } from '@/components/Card'
import { CopyableUri } from '@/components/CopyableUri'
import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'
import { LinkButton } from '@/components/LinkButton'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatDate, formatRelativeTime } from '@/utils/datetime'

export default async function PolicyPage({ params }: PageProps<'/policies/[policyId]'>) {
  const { policyId } = await params
  const repo = await getRepo()
  const policyVersionsResponse = await repo.getVersionsForPolicy(policyId, { limit: 500 })
  const policyVersions = policyVersionsResponse.entries

  const policyName = policyVersions[0]?.name ?? 'Unknown Policy'
  const policyCreatedAt = policyVersions[0]?.policy_created_at ?? null
  const userId = policyVersions[0]?.user_id

  return (
    <StandardPageLayout>
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-gray-500 tracking-wide">Policy</p>
          <h1 className="text-2xl font-semibold text-gray-900">{policyName}</h1>
          <div className="flex flex-wrap gap-3 text-sm text-gray-600">
            {userId && <span className="text-gray-500">User: {userId}</span>}
            {policyCreatedAt && (
              <span className="text-gray-500" title={formatDate(policyCreatedAt)}>
                Created: {formatRelativeTime(policyCreatedAt)}
              </span>
            )}
            <span className="flex items-center gap-1 text-gray-500">
              Policy ID:
              <span className="font-mono text-xs text-gray-700">{policyId}</span>
            </span>
          </div>
        </div>
        <LinkButton href="/" theme="tertiary">
          ← Back to policies
        </LinkButton>
      </div>

      {policyVersions[0]?.name && <CopyableUri uri={`metta://policy/${policyVersions[0].name}`} />}

      <Card title="Versions">
        {policyVersions.length === 0 ? (
          <div className="text-gray-500 text-sm">No versions found for this policy.</div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TH>Version</TH>
                <TH>Version ID</TH>
                <TH>Created</TH>
              </TableHeader>
              <TableBody>
                {policyVersions.map((pv) => (
                  <TR key={pv.id}>
                    <TD>
                      <StyledLink href={`/policies/versions/${pv.id}`} className="font-medium">
                        v{pv.version}
                      </StyledLink>
                    </TD>
                    <TD>
                      <span className="font-mono text-xs text-gray-600">{pv.id}</span>
                    </TD>
                    <TD title={formatDate(pv.created_at)}>{formatRelativeTime(pv.created_at)}</TD>
                  </TR>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>
    </StandardPageLayout>
  )
}

export async function generateMetadata({ params }: PageProps<'/policies/[policyId]'>) {
  const { policyId } = await params
  const repo = await getRepo()
  const policyVersionsResponse = await repo.getVersionsForPolicy(policyId, { limit: 1 })
  const policyVersions = policyVersionsResponse.entries
  const policyName = policyVersions[0]?.name ?? 'Unknown Policy'
  return {
    title: `${policyName} | Observatory`,
  }
}
