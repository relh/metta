import clsx from 'clsx'
import { createLoader, parseAsString } from 'nuqs/server'

import { Card } from '@/components/Card'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import type { TeamSummary } from '@/lib/api'
import { getSeasonStageContext, getTeamStages } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'

import { stageFlowLabel, stageLabel } from '../stageSelection'
import { formatPolicyTag } from '../utils'

const parseSearchParams = createLoader({ stage: parseAsString })

type TeamRow = {
  key: string
  cogs: TeamSummary['cogs']
  byStage: Map<string, TeamSummary>
}

type TeamCompositionGroup = {
  key: string
  cogs: TeamSummary['cogs']
  byStage: Map<string, TeamSummary[]>
}

export default async function TeamsPage({ params, searchParams }: PageProps<'/tournament/[seasonName]/teams'>) {
  const { seasonName } = await params
  const repo = await getRepo()
  const parsed = await parseSearchParams(searchParams)

  const stageContext = await getSeasonStageContext(repo, seasonName, parsed.stage)
  const teamStages = getTeamStages(stageContext.stages, stageContext.progress)
  const selectedStage = stageContext.selectedStage
  const selectedFlowStage = selectedStage
    ? stageContext.progress?.stage_flow.find((stage) => stage.input_pool === selectedStage)
    : null
  const selectedStageTitle = selectedFlowStage
    ? stageFlowLabel(selectedFlowStage)
    : selectedStage
      ? stageLabel(selectedStage)
      : null
  const cardTitle = 'Teams'
  const selectedStageStatus = selectedStage ? selectedFlowStage?.status : null
  const selectedTeamStage =
    selectedStage && teamStages.some((stage) => stage.name === selectedStage) ? selectedStage : null
  const stageFlowByPool = new Map((stageContext.progress?.stage_flow ?? []).map((stage) => [stage.input_pool, stage]))

  if (selectedStage && (selectedStageStatus === 'pending' || !selectedTeamStage)) {
    return (
      <Card title={cardTitle}>
        <div className="text-foreground-muted py-4 text-center">
          No team results for this stage yet ({selectedStageTitle ?? stageLabel(selectedStage)}).
        </div>
      </Card>
    )
  }

  const teamsByStage = await Promise.all(
    teamStages.map(
      async (stage): Promise<readonly [string, TeamSummary[]]> => [
        stage.name,
        await repo.getSeasonTeams(seasonName, {
          pool_name: stage.name,
          limit: stage.team_count ?? undefined,
        }),
      ]
    )
  )
  const compositionMap = new Map<string, TeamCompositionGroup>()

  for (const [stageName, teams] of teamsByStage) {
    for (const team of teams) {
      const key = team.cogs.map((cog) => cog.policy.id).join('|')
      let group = compositionMap.get(key)
      if (!group) {
        group = {
          key,
          cogs: team.cogs,
          byStage: new Map<string, TeamSummary[]>(),
        }
        compositionMap.set(key, group)
      }
      const stageTeams = group.byStage.get(stageName)
      if (stageTeams) {
        stageTeams.push(team)
      } else {
        group.byStage.set(stageName, [team])
      }
    }
  }
  const rows: TeamRow[] = []
  for (const group of compositionMap.values()) {
    for (const stageTeams of group.byStage.values()) {
      stageTeams.sort((a, b) => (b.score ?? Number.NEGATIVE_INFINITY) - (a.score ?? Number.NEGATIVE_INFINITY))
    }
    const rowCount = Math.max(...teamStages.map((stage) => group.byStage.get(stage.name)?.length ?? 0))
    for (let i = 0; i < rowCount; i++) {
      const rowByStage = new Map<string, TeamSummary>()
      for (const stage of teamStages) {
        const team = group.byStage.get(stage.name)?.[i]
        if (team) {
          rowByStage.set(stage.name, team)
        }
      }
      rows.push({
        key: `${group.key}:${i}`,
        cogs: group.cogs,
        byStage: rowByStage,
      })
    }
  }

  rows.sort((a, b) => {
    if (selectedTeamStage) {
      const aScore = a.byStage.get(selectedTeamStage)?.score ?? Number.NEGATIVE_INFINITY
      const bScore = b.byStage.get(selectedTeamStage)?.score ?? Number.NEGATIVE_INFINITY
      if (aScore !== bScore) return bScore - aScore
    }
    if (a.byStage.size !== b.byStage.size) return b.byStage.size - a.byStage.size
    return a.key.localeCompare(b.key)
  })

  return (
    <Card title={cardTitle}>
      {rows.length === 0 ? (
        <div className="text-foreground-muted py-4 text-center">No teams found</div>
      ) : (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TH>Team</TH>
              {teamStages.map((stage) => {
                const stageFlow = stageFlowByPool.get(stage.name)
                return (
                  <TH
                    key={stage.name}
                    className={clsx(
                      'min-w-40',
                      selectedTeamStage === stage.name
                        ? 'bg-blue-100 dark:bg-blue-950/40 text-blue-800 dark:text-blue-200'
                        : ''
                    )}
                  >
                    {stageFlow ? stageFlowLabel(stageFlow) : stageLabel(stage.name)}
                  </TH>
                )
              })}
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TR key={row.key}>
                  <TD>
                    <div className="flex flex-wrap gap-1">
                      {row.cogs.map((cog) => (
                        <StyledLink
                          key={cog.position}
                          href={`/policies/versions/${cog.policy.id}`}
                          className="inline-block px-2 py-0.5 rounded text-xs font-mono bg-surface-alt border border-border hover:border-blue-400 transition-colors"
                        >
                          {formatPolicyTag(cog.policy)}
                        </StyledLink>
                      ))}
                    </div>
                  </TD>
                  {teamStages.map((stage) => {
                    const team = row.byStage.get(stage.name)
                    if (!team) {
                      return (
                        <TD
                          key={stage.name}
                          className={clsx(
                            'text-foreground-muted',
                            selectedTeamStage === stage.name ? 'bg-blue-950/10' : ''
                          )}
                        >
                          -
                        </TD>
                      )
                    }
                    return (
                      <TD key={stage.name} className={selectedTeamStage === stage.name ? 'bg-blue-950/10' : ''}>
                        <div className="flex flex-col gap-1 items-start">
                          <span className="font-mono text-sm">
                            {team.score !== null ? team.score.toPrecision(4) : '-'}
                          </span>
                          <span className="text-xs text-foreground-muted">{team.matches} matches</span>
                          <span
                            className={
                              team.eliminated
                                ? 'px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                                : 'px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400'
                            }
                          >
                            {team.eliminated ? 'Eliminated' : 'Alive'}
                          </span>
                        </div>
                      </TD>
                    )
                  })}
                </TR>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  )
}
