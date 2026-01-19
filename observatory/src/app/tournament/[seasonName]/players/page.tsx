import clsx from 'clsx'
import Link from 'next/link'

import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { getRepo } from '@/lib/repo/server'
import { formatRelativeTime } from '@/utils/datetime'

import { matchesRoute } from '../matches/utils'
import { formatPolicyDisplay } from '../utils'
import { SubmitForm } from './SubmitForm'

export default async function PlayersPage(params: PageProps<'/tournament/[seasonName]/players'>) {
  const { seasonName } = await params.params
  const repo = await getRepo()
  const policies = await repo.getSeasonPolicies(seasonName)
  const existingPolicyVersionIds = new Set(policies.map((p) => p.policy.id))
  const poolNames = policies[0]?.pools.map((p) => p.pool_name) || []

  return (
    <div className="space-y-4">
      <SubmitForm seasonName={seasonName} existingPolicyVersionIds={existingPolicyVersionIds} />
      {policies.length === 0 ? (
        <div className="text-gray-500 py-4">No players submitted yet</div>
      ) : (
        <Table>
          <TableHeader>
            <TH>Player</TH>
            <TH>Entered</TH>
            {poolNames.map((poolName) => (
              <TH key={poolName} className="capitalize">
                {poolName}
              </TH>
            ))}
          </TableHeader>
          <TableBody>
            {policies.map((policy) => {
              const poolStatusMap = Object.fromEntries(policy.pools.map((p) => [p.pool_name, p]))
              return (
                <TR key={policy.policy.id}>
                  <TD>
                    <StyledLink href={`/policies/versions/${policy.policy.id}`} className="font-medium">
                      {formatPolicyDisplay(policy)}
                    </StyledLink>
                  </TD>
                  <TD className="text-gray-500 text-sm">{formatRelativeTime(policy.entered_at)}</TD>
                  {poolNames.map((poolName) => {
                    const pool = poolStatusMap[poolName]
                    if (!pool) {
                      return (
                        <TD key={poolName} className="text-gray-400">
                          -
                        </TD>
                      )
                    }
                    return (
                      <TD key={poolName}>
                        <div className="flex flex-col gap-1.5 items-start">
                          <span
                            className={clsx(
                              'inline-block px-2 py-1 rounded text-xs font-medium',
                              pool.active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
                            )}
                          >
                            {pool.active ? 'active' : 'retired'}
                          </span>
                          <Link
                            href={matchesRoute(seasonName, {
                              pool_names: [poolName],
                              policy_version_ids: [policy.policy.id],
                            })}
                            className="no-underline text-sm text-gray-400 hover:text-blue-600 cursor-pointer transition-colors"
                          >
                            ({pool.completed} matches
                            {pool.failed > 0 && `, ${pool.failed} failed`}
                            {pool.pending > 0 && `, ${pool.pending} pending`})
                          </Link>
                        </div>
                      </TD>
                    )
                  })}
                </TR>
              )
            })}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
