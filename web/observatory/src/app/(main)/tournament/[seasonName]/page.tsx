import { FC, Suspense } from 'react'
import { createLoader, parseAsString } from 'nuqs/server'
import { redirect } from 'next/navigation'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { matchesRoute, policyVersionRoute, seasonPlayersRoute } from '@/lib/routes'
import { getSeasonStageContext } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'
import { seasonTabModeForName } from '@/lib/tournament/tabMode'
import { StageLeaderboard } from './StageLeaderboard'
import { StartTournamentButton } from './StartTournamentButton'
import { formatPolicyDisplay } from './utils'

const nuqsParams = { stage: parseAsString, view: parseAsString }
const parseSearchParams = createLoader(nuqsParams)

const FlatLeaderboard: FC<{ seasonName: string }> = async ({ seasonName }) => {
  const repo = await getRepo()
  const leaderboard = await repo.getSeasonLeaderboard(seasonName)
  if (leaderboard.length === 0) {
    return (
      <TR>
        <TD colSpan={3} className="text-foreground-muted py-4 text-center">
          No entries yet
        </TD>
      </TR>
    )
  }

  return (
    <>
      {leaderboard.map((entry) => (
        <TR key={entry.policy.id}>
          <TD>{entry.rank}</TD>
          <TD>
            <StyledLink href={policyVersionRoute(entry.policy.id)} className="font-medium">
              {formatPolicyDisplay(entry)}
            </StyledLink>
          </TD>
          <TD>
            {entry.score.toPrecision(4)}{' '}
            <StyledLink
              href={matchesRoute(seasonName, {
                pool_names: ['competition'],
                policy_version_ids: [entry.policy.id],
              })}
              theme="muted"
              className="text-foreground-muted"
            >
              ({entry.matches} matches)
            </StyledLink>
          </TD>
        </TR>
      ))}
    </>
  )
}

export default async function SeasonPage({ params, searchParams }: PageProps<'/tournament/[seasonName]'>) {
  const { seasonName } = await params
  const parsed = await parseSearchParams(searchParams)
  const repo = await getRepo()
  const stageContext = await getSeasonStageContext(repo, seasonName, parsed.stage)

  if (stageContext.teamSeason) {
    const progress = stageContext.progress

    if (parsed.view !== 'leaderboard') {
      redirect(
        seasonPlayersRoute(seasonName, {
          stage: parsed.stage ?? undefined,
          mode: seasonTabModeForName(seasonName),
        })
      )
    }

    if (!progress || !progress.started) {
      const policyCount = stageContext.stages[0]?.policy_count ?? 0
      return (
        <Card title="Tournament">
          <StartTournamentButton seasonName={seasonName} policyCount={policyCount} />
        </Card>
      )
    }

    const leaderboardStage =
      stageContext.selectedStage ?? stageContext.progress?.stage_flow[0]?.input_pool ?? stageContext.stages[0]?.name
    if (!leaderboardStage) {
      return (
        <Card>
          <div className="text-foreground-muted text-sm">No stages configured.</div>
        </Card>
      )
    }
    const selectedFlowStage = progress.stage_flow.find((stage) => stage.input_pool === leaderboardStage)
    if (selectedFlowStage?.status === 'pending') {
      return (
        <Card>
          <div className="text-foreground-muted py-4 text-center">This stage has not started yet.</div>
        </Card>
      )
    }

    return (
      <Card>
        <StageLeaderboard
          seasonName={seasonName}
          stage={leaderboardStage}
          stageKind={stageContext.selectedStageKind}
          scorePoliciesPool={stageContext.scorePoliciesPool}
          scorePoliciesDescription={stageContext.scorePoliciesDescription}
        />
      </Card>
    )
  }

  return (
    <Card>
      <Table>
        <TableHeader>
          <TH>Rank</TH>
          <TH>Policy</TH>
          <TH>Score</TH>
        </TableHeader>
        <TableBody>
          <Suspense
            fallback={
              <TR>
                <TD colSpan={3} className="text-center">
                  <div className="grid place-items-center min-h-80">
                    <Spinner size="lg" />
                  </div>
                </TD>
              </TR>
            }
          >
            <FlatLeaderboard seasonName={seasonName} />
          </Suspense>
        </TableBody>
      </Table>
    </Card>
  )
}
