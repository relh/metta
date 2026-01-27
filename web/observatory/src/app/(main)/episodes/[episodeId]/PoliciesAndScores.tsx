import { FC, Suspense } from 'react'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { EpisodeWithTags, PolicyVersionWithName } from '@/lib/repo'
import { getRepo } from '@/lib/repo/server'
import { formatPolicyVersion } from '@/utils/format'

function formatScore(value: number | null | undefined): string {
  if (typeof value !== 'number') {
    return '—'
  }
  return value.toFixed(2)
}

const PolicyLink: FC<{ policy: PolicyVersionWithName }> = ({ policy }) => {
  const policyLabel = formatPolicyVersion(policy)
  return <StyledLink href={`/policies/versions/${policy.id}`}>{policyLabel}</StyledLink>
}

const InnerPolicyLinkById: FC<{ policyId: string }> = async ({ policyId }) => {
  const repo = await getRepo()
  const policy = await repo.getPolicyVersion(policyId)
  return <PolicyLink policy={policy} />
}

const PolicyLinkById: FC<{ policyId: string }> = ({ policyId }) => {
  return (
    <Suspense fallback={<Spinner />}>
      <InnerPolicyLinkById policyId={policyId} />
    </Suspense>
  )
}

export const PoliciesAndScores: FC<{ episode: EpisodeWithTags }> = async ({ episode }) => {
  return (
    <Card title="Policies & Scores">
      {Object.keys(episode.avg_rewards || {}).length === 0 ? (
        <div className="text-gray-500 text-sm">No policy metrics recorded for this episode.</div>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TH>Policy</TH>
              <TH>Policy ID</TH>
              <TH>Avg Reward</TH>
            </TableHeader>
            <TableBody>
              {Object.entries(episode.avg_rewards || {})
                .sort(([, a], [, b]) => (typeof b === 'number' && typeof a === 'number' ? b - a : 0))
                .map(([policyId, reward]) => {
                  return (
                    <TR key={policyId}>
                      <TD>
                        <div className="flex items-center gap-2">
                          <PolicyLinkById policyId={policyId} />
                        </div>
                      </TD>
                      <TD>
                        <span className="font-mono text-xs text-gray-700">{policyId}</span>
                      </TD>
                      <TD>
                        <span className="font-mono">{formatScore(reward)}</span>
                      </TD>
                    </TR>
                  )
                })}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  )
}
