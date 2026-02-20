import clsx from 'clsx'
import Link from 'next/link'
import { createLoader, parseAsString } from 'nuqs/server'

import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getPlayerStages, getSeasonStageContext } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'
import { formatRelativeTime } from '@/utils/datetime'

import { matchesRoute } from '../matches/utils'
import { stageFlowLabel, stageLabel } from '../stageSelection'
import { formatPolicyDisplay } from '../utils'
import { SubmitForm } from './SubmitForm'

const parseSearchParams = createLoader({ stage: parseAsString })

export default async function PlayersPage({ params, searchParams }: PageProps<'/tournament/[seasonName]/players'>) {
  const { seasonName } = await params
  const parsed = await parseSearchParams(searchParams)
  const repo = await getRepo()
  const [season, policies, stageContext] = await Promise.all([
    repo.getSeason(seasonName),
    repo.getSeasonPolicies(seasonName),
    getSeasonStageContext(repo, seasonName, parsed.stage),
  ])
  const existingPolicyVersionIds = new Set(policies.map((p) => p.policy.id))
  const selectedStage = stageContext.selectedStage
  const selectedFlowStage = selectedStage
    ? stageContext.progress?.stage_flow.find((stage) => stage.input_pool === selectedStage)
    : null
  const selectedStageStatus = selectedFlowStage?.status ?? null
  const tournamentNotStarted = stageContext.progress?.started !== true
  const playerStages = getPlayerStages(stageContext.stages, stageContext.progress)
  const poolNames =
    stageContext.progress && playerStages.length > 0
      ? playerStages.map((stage) => stage.name)
      : selectedStage
        ? [selectedStage]
        : season.pools.map((pool) => pool.name)
  const stageFlowByPool = new Map((stageContext.progress?.stage_flow ?? []).map((stage) => [stage.input_pool, stage]))
  const selectedDisplayStage = selectedStage && poolNames.includes(selectedStage) ? selectedStage : null

  return (
    <div className="space-y-4">
      <ServerDebugDrain />
      {tournamentNotStarted && (
        <SubmitForm seasonName={seasonName} existingPolicyVersionIds={existingPolicyVersionIds} />
      )}
      {selectedStage && selectedStageStatus === 'pending' ? (
        <div className="text-foreground-muted py-4">This stage has not started yet.</div>
      ) : policies.length === 0 ? (
        <div className="text-foreground-muted py-4">No players submitted yet</div>
      ) : (
        <Table>
          <TableHeader>
            <TH>Player</TH>
            <TH>Entered</TH>
            {poolNames.map((poolName) => {
              const stageFlow = stageFlowByPool.get(poolName)
              return (
                <TH
                  key={poolName}
                  className={clsx(
                    selectedDisplayStage === poolName
                      ? 'bg-blue-100 dark:bg-blue-950/40 text-blue-800 dark:text-blue-200'
                      : ''
                  )}
                >
                  {stageFlow ? stageFlowLabel(stageFlow) : stageLabel(poolName)}
                </TH>
              )
            })}
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
                  <TD className="text-foreground-muted text-sm">{formatRelativeTime(policy.entered_at)}</TD>
                  {poolNames.map((poolName) => {
                    const pool = poolStatusMap[poolName]
                    if (!pool) {
                      return (
                        <TD
                          key={poolName}
                          className={clsx(
                            'text-foreground-muted',
                            selectedDisplayStage === poolName ? 'bg-blue-950/10' : ''
                          )}
                        >
                          -
                        </TD>
                      )
                    }
                    return (
                      <TD key={poolName} className={selectedDisplayStage === poolName ? 'bg-blue-950/10' : ''}>
                        <div className="flex flex-col gap-1.5 items-start">
                          <span
                            className={clsx(
                              'inline-block px-2 py-1 rounded text-xs font-medium',
                              pool.active
                                ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                                : 'bg-surface-alt text-foreground-muted'
                            )}
                          >
                            {pool.active ? 'active' : 'retired'}
                          </span>
                          <Link
                            href={matchesRoute(seasonName, {
                              stage: stageContext.progress ? poolName : undefined,
                              pool_names: stageContext.progress ? undefined : [poolName],
                              policy_version_ids: [policy.policy.id],
                            })}
                            className="no-underline text-sm text-foreground-muted hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer transition-colors"
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
