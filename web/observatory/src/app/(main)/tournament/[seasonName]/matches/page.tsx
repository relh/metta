import Link from 'next/link'
import { createLoader } from 'nuqs/server'

import { PaginatedControls } from '@/components/PaginatedControls'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getSeasonStageContext } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'
import { formatRelativeTime } from '@/utils/datetime'

import { MatchStatusBadge } from '../MatchStatusBadge'
import { stageFlowLabel } from '../stageSelection'
import { formatPolicyDisplay } from '../utils'
import { MatchFilters } from './MatchFilters'
import { nuqsParams } from './searchParams'
import { matchesRoute } from './utils'

const parseSearchParams = createLoader(nuqsParams)
const MATCHES_PAGE_SIZE = 50

export default async function MatchesPage(params: PageProps<'/tournament/[seasonName]/matches'>) {
  const { seasonName } = await params.params
  const repo = await getRepo()
  const parsed = await parseSearchParams(params.searchParams)

  const [policies, stageContext] = await Promise.all([
    repo.getSeasonPolicies(seasonName),
    getSeasonStageContext(repo, seasonName, parsed.stage),
  ])
  const selectedStage = stageContext.selectedStage
  const selectedFlowStage = selectedStage
    ? stageContext.progress?.stage_flow.find((stage) => stage.input_pool === selectedStage)
    : null
  const selectedStageTitle = selectedFlowStage ? stageFlowLabel(selectedFlowStage) : null
  const selectedStageStatus = selectedStage ? selectedFlowStage?.status : null
  const poolNames = selectedStage ? [selectedStage] : parsed.pool_names.length > 0 ? parsed.pool_names : undefined

  if (selectedStage && selectedStageStatus === 'pending') {
    return (
      <div>
        <ServerDebugDrain />
        <MatchFilters policies={policies} />
        <div className="text-foreground-muted py-4">This stage has not started yet.</div>
      </div>
    )
  }

  const filteredMatches = await repo.getSeasonMatches(seasonName, {
    limit: MATCHES_PAGE_SIZE,
    offset: parsed.match_page * MATCHES_PAGE_SIZE,
    pool_names: poolNames,
    policy_version_ids: parsed.policy_version_ids.length > 0 ? parsed.policy_version_ids : undefined,
  })

  const selectedStageStats = selectedStage ? stageContext.stages.find((stage) => stage.name === selectedStage) : null
  const hasMatchPhase = selectedStageStats ? selectedStageStats.match_count > 0 : false

  return (
    <div>
      <ServerDebugDrain />
      <MatchFilters policies={policies} />
      {filteredMatches.length === 0 ? (
        selectedStage && !hasMatchPhase ? (
          <div className="py-4">
            <div className="text-foreground-muted">
              No matches in this phase ({selectedStageTitle ?? selectedStage}).
            </div>
          </div>
        ) : (
          <div className="text-foreground-muted py-4">No matches</div>
        )
      ) : (
        <Table>
          <TableHeader>
            <TH className="w-24">Created</TH>
            <TH className="w-20">Status</TH>
            <TH className="w-24">Pool</TH>
            <TH className="text-right">Players</TH>
            <TH className="w-16">Agents</TH>
            <TH className="w-20">Score</TH>
          </TableHeader>
          <TableBody>
            {filteredMatches.map((match) => {
              return (
                <TR key={match.id}>
                  <TD className="text-foreground-muted text-sm">{formatRelativeTime(match.created_at)}</TD>
                  <TD>
                    <div className="flex justify-between gap-1">
                      {match.status === 'completed' && match.episode_id ? (
                        <Link
                          href={`/episodes/${match.episode_id}`}
                          className="px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-900/50 transition-colors"
                        >
                          Results
                        </Link>
                      ) : (
                        <MatchStatusBadge status={match.status} />
                      )}
                    </div>
                  </TD>
                  <TD>
                    {selectedStage ? (
                      <span className="text-foreground-muted">{match.pool_name}</span>
                    ) : (
                      <StyledLink
                        href={matchesRoute(seasonName, {
                          stage: parsed.stage || undefined,
                          pool_names: [match.pool_name],
                          policy_version_ids: parsed.policy_version_ids,
                          match_page: 0,
                        })}
                        theme="muted"
                      >
                        {match.pool_name}
                      </StyledLink>
                    )}
                  </TD>
                  <TD className="text-right">
                    <div className="flex flex-col gap-1 items-end">
                      {match.players.map((p, i) => (
                        <StyledLink
                          key={i}
                          href={matchesRoute(seasonName, {
                            stage: selectedStage ?? (parsed.stage || undefined),
                            pool_names: selectedStage ? undefined : parsed.pool_names,
                            policy_version_ids: [p.policy.id],
                            match_page: 0,
                          })}
                          theme="muted"
                          className="font-mono text-xs"
                        >
                          {formatPolicyDisplay(p)}
                        </StyledLink>
                      ))}
                    </div>
                  </TD>
                  <TD>
                    <div className="flex flex-col gap-1 font-mono text-xs">
                      {match.players.map((p, i) => (
                        <span key={i}>{p.num_agents}</span>
                      ))}
                    </div>
                  </TD>
                  <TD>
                    <div className="flex flex-col gap-1 font-mono text-xs">
                      {match.players.map((p, i) => (
                        <span key={i}>{p.score !== null ? p.score.toPrecision(3) : '-'}</span>
                      ))}
                    </div>
                  </TD>
                </TR>
              )
            })}
          </TableBody>
        </Table>
      )}
      {filteredMatches.length > 0 && (
        <PaginatedControls paramName="match_page" isLastPage={filteredMatches.length < MATCHES_PAGE_SIZE} />
      )}
    </div>
  )
}
