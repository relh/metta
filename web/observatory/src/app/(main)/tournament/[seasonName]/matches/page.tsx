import Link from 'next/link'
import { createLoader } from 'nuqs/server'

import { PaginatedControls } from '@/components/PaginatedControls'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatRelativeTime } from '@/utils/datetime'

import { MatchStatusBadge } from '../MatchStatusBadge'
import { formatPolicyDisplay } from '../utils'
import { MatchFilters } from './MatchFilters'
import { nuqsParams } from './searchParams'
import { matchesRoute } from './utils'

const parseSearchParams = createLoader(nuqsParams)

export default async function MatchesPage(params: PageProps<'/tournament/[seasonName]/matches'>) {
  const { seasonName } = await params.params
  const repo = await getRepo()

  const season = await repo.getSeason(seasonName)
  const policies = await repo.getSeasonPolicies(seasonName)

  const searchParams = await parseSearchParams(params.searchParams)

  const MATCHES_PAGE_SIZE = 50

  const filteredMatches = await repo.getSeasonMatches(seasonName, {
    limit: MATCHES_PAGE_SIZE,
    offset: searchParams.match_page * MATCHES_PAGE_SIZE,
    pool_names: searchParams.pool_names.length > 0 ? searchParams.pool_names : undefined,
    policy_version_ids: searchParams.policy_version_ids.length > 0 ? searchParams.policy_version_ids : undefined,
  })

  return (
    <div>
      <ServerDebugDrain />
      <MatchFilters season={season} policies={policies} />
      {filteredMatches.length === 0 ? (
        <div className="text-foreground-muted py-4">No matches</div>
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
              const agentCounts = match.players.map((p) => match.assignments.filter((a) => a === p.policy_index).length)
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
                      {match.job_id && (
                        <Link
                          href={`/episode-jobs?jobId=${match.job_id}`}
                          className="px-2 py-1 rounded text-xs font-medium bg-surface-alt text-foreground-subtle hover:bg-border-strong transition-colors"
                        >
                          Job
                        </Link>
                      )}
                    </div>
                  </TD>
                  <TD>
                    <StyledLink
                      href={matchesRoute(seasonName, {
                        ...searchParams,
                        pool_names: [match.pool_name],
                        match_page: 0,
                      })}
                      theme="muted"
                    >
                      {match.pool_name}
                    </StyledLink>
                  </TD>
                  <TD className="text-right">
                    <div className="flex flex-col gap-1 items-end">
                      {match.players.map((p, i) => (
                        <StyledLink
                          key={i}
                          href={matchesRoute(seasonName, {
                            ...searchParams,
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
                      {match.players.map((_, i) => (
                        <span key={i}>{agentCounts[i]}</span>
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
      <PaginatedControls paramName="match_page" isLastPage={filteredMatches.length < MATCHES_PAGE_SIZE} />
    </div>
  )
}
