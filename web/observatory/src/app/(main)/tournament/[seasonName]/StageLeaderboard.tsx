import { FC, ReactNode, Suspense } from 'react'

import { Spinner } from '@/components/Spinner'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import type { LeaderboardEntry, ScorePoliciesLeaderboardEntry, TeamSummary } from '@/lib/api'
import { getStageLeaderboard, type StageKind } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'
import { policyVersionRoute } from '@/lib/routes'

import { formatPolicyDisplay, formatPolicyTag } from './utils'

type LeaderboardColumn<Row> = {
  key: string
  header: ReactNode
  className?: string
  render: (row: Row, index: number) => ReactNode
}

const LeaderboardTable = <Row,>({
  rows,
  columns,
  emptyText,
  getRowKey,
}: {
  rows: Row[]
  columns: LeaderboardColumn<Row>[]
  emptyText: string
  getRowKey: (row: Row, index: number) => string
}) => {
  if (rows.length === 0) {
    return <div className="text-foreground-muted py-4 text-center">{emptyText}</div>
  }

  return (
    <Table>
      <TableHeader>
        {columns.map((column) => (
          <TH key={column.key} className={column.className}>
            {column.header}
          </TH>
        ))}
      </TableHeader>
      <TableBody>
        {rows.map((row, rowIndex) => (
          <TR key={getRowKey(row, rowIndex)}>
            {columns.map((column) => (
              <TD key={column.key}>{column.render(row, rowIndex)}</TD>
            ))}
          </TR>
        ))}
      </TableBody>
    </Table>
  )
}

const policyColumns: LeaderboardColumn<LeaderboardEntry>[] = [
  {
    key: 'rank',
    header: 'Rank',
    render: (entry) => entry.rank,
  },
  {
    key: 'policy',
    header: 'Policy',
    render: (entry) => (
      <StyledLink href={policyVersionRoute(entry.policy.id)} className="font-medium">
        {formatPolicyDisplay(entry)}
      </StyledLink>
    ),
  },
  {
    key: 'score',
    header: 'Score',
    render: (entry) => (
      <div className="flex flex-col items-start gap-0.5">
        <span className="font-mono text-sm">{entry.score.toPrecision(4)}</span>
        <span className="text-foreground-muted text-xs">({entry.matches} matches)</span>
      </div>
    ),
  },
]

const teamColumns: LeaderboardColumn<TeamSummary>[] = [
  {
    key: 'rank',
    header: 'Rank',
    render: (_team, index) => index + 1,
  },
  {
    key: 'team',
    header: 'Team',
    render: (team) => (
      <div className="flex flex-wrap gap-1">
        {team.cogs.map((cog) => (
          <StyledLink
            key={cog.position}
            href={policyVersionRoute(cog.policy.id)}
            className="inline-block px-2 py-0.5 rounded text-xs font-mono bg-surface-alt border border-border"
          >
            {formatPolicyTag(cog.policy)}
          </StyledLink>
        ))}
      </div>
    ),
  },
  {
    key: 'score',
    header: 'Score',
    render: (team) => (
      <div className="flex flex-col items-start gap-0.5">
        <span className="font-mono text-sm">{team.score !== null ? team.score.toPrecision(4) : '-'}</span>
        <span className="text-foreground-muted text-xs">({team.matches} matches)</span>
      </div>
    ),
  },
  {
    key: 'status',
    header: 'Status',
    render: (team) => (
      <span
        className={
          team.eliminated
            ? 'px-2 py-1 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
            : 'px-2 py-1 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
        }
      >
        {team.eliminated ? 'Eliminated' : 'Alive'}
      </span>
    ),
  },
]

function getScorePolicyColumns(
  scorePoliciesDescription: string | null
): LeaderboardColumn<ScorePoliciesLeaderboardEntry>[] {
  const topKMatch = scorePoliciesDescription?.match(/\btop\s+(\d+)\b/i)
  const topK = topKMatch ? Number.parseInt(topKMatch[1], 10) : null

  return [
    {
      key: 'rank',
      header: 'Rank',
      render: (entry) => entry.rank,
    },
    {
      key: 'policy',
      header: 'Policy',
      render: (entry) => (
        <StyledLink href={policyVersionRoute(entry.policy.id)} className="font-medium">
          {formatPolicyDisplay(entry)}
        </StyledLink>
      ),
    },
    {
      key: 'placement',
      header: (
        <span
          title={scorePoliciesDescription ?? undefined}
          className={scorePoliciesDescription ? 'cursor-help underline decoration-dotted underline-offset-2' : ''}
        >
          Placement Sum
        </span>
      ),
      render: (entry) => <span className="font-mono text-sm">{entry.placement_score.toPrecision(4)}</span>,
    },
    {
      key: 'appearances',
      header: (
        <span
          title="Ranks of the teams the policy appeared in"
          className="cursor-help underline decoration-dotted underline-offset-2"
        >
          Team Ranks
        </span>
      ),
      render: (entry) => (
        <div className="flex flex-col items-start gap-0.5">
          <span className="font-mono text-sm">
            {(() => {
              const contributingRanks = topK === null ? entry.team_ranks : entry.team_ranks.slice(0, topK)
              const missingCount = topK === null ? 0 : Math.max(0, topK - contributingRanks.length)
              const contributingSum = contributingRanks.reduce((sum, rank) => sum + rank, 0)
              const penaltyPerMissing =
                missingCount > 0 ? (entry.placement_score - contributingSum) / missingCount : null
              const roundedPenalty = penaltyPerMissing === null ? null : Math.round(penaltyPerMissing)
              const penaltyLabel =
                penaltyPerMissing === null
                  ? null
                  : Math.abs(penaltyPerMissing - (roundedPenalty ?? penaltyPerMissing)) < 1e-6
                    ? String(roundedPenalty)
                    : penaltyPerMissing.toPrecision(4)
              const displayedCount = entry.team_ranks.length + missingCount

              if (displayedCount === 0) {
                return '-'
              }

              return (
                <>
                  {entry.team_ranks.map((teamRank, index) => (
                    <span
                      key={`${entry.policy.id}-${teamRank}-${index}`}
                      className={topK !== null && index >= topK ? 'text-foreground-muted' : undefined}
                    >
                      {index > 0 ? ', ' : ''}
                      {teamRank}
                    </span>
                  ))}
                  {penaltyLabel !== null &&
                    Array.from({ length: missingCount }, (_value, index) => (
                      <span
                        key={`${entry.policy.id}-missing-${index}`}
                        className="text-red-600/80 dark:text-red-400/80"
                        title="Missing team appearance penalty (n+1)"
                      >
                        {entry.team_ranks.length > 0 || index > 0 ? ', ' : ''}+{penaltyLabel}
                      </span>
                    ))}
                </>
              )
            })()}
          </span>
          <span className="text-foreground-muted text-xs">({entry.team_appearances} teams)</span>
        </div>
      ),
    },
  ]
}

const StageLeaderboardContent: FC<{
  seasonName: string
  stage: string
  stageKind: StageKind | null
  scorePoliciesPool: string | null
  scorePoliciesDescription: string | null
}> = async ({ seasonName, stage, stageKind, scorePoliciesPool, scorePoliciesDescription }) => {
  const repo = await getRepo()
  const leaderboard = await getStageLeaderboard(repo, seasonName, stage, stageKind, scorePoliciesPool)

  if (leaderboard.kind === 'team') {
    return (
      <LeaderboardTable
        rows={leaderboard.rows}
        columns={teamColumns}
        emptyText="No teams yet"
        getRowKey={(team) => team.id}
      />
    )
  }

  if (leaderboard.kind === 'score-policies') {
    return (
      <LeaderboardTable
        rows={leaderboard.rows}
        columns={getScorePolicyColumns(scorePoliciesDescription)}
        emptyText="No score-policies results yet"
        getRowKey={(entry) => entry.policy.id}
      />
    )
  }

  return (
    <LeaderboardTable
      rows={leaderboard.rows}
      columns={policyColumns}
      emptyText="No results yet"
      getRowKey={(entry) => entry.policy.id}
    />
  )
}

export const StageLeaderboard: FC<{
  seasonName: string
  stage: string
  stageKind: StageKind | null
  scorePoliciesPool: string | null
  scorePoliciesDescription: string | null
}> = async ({ seasonName, stage, stageKind, scorePoliciesPool, scorePoliciesDescription }) => {
  return (
    <Suspense
      fallback={
        <div className="grid place-items-center min-h-40">
          <Spinner size="lg" />
        </div>
      }
    >
      <StageLeaderboardContent
        seasonName={seasonName}
        stage={stage}
        stageKind={stageKind}
        scorePoliciesPool={scorePoliciesPool}
        scorePoliciesDescription={scorePoliciesDescription}
      />
    </Suspense>
  )
}
