import type { ProgressResponse, StageStats } from '@/lib/api'

import { stageKindLabel, type TournamentStageFlowEntry } from './stages'

export type StageProgressItem = {
  index: number
  inputPool: string
  outputPool: string
  status: TournamentStageFlowEntry['status']
  title: string
  description: string
  showMatchCount: boolean
  matchCount: number
  completionPct: number
  entrantLabel: string
  entrantCount: number | null
  exitLabel: string
  exitCount: number | null
}

function stageTitle(stage: ProgressResponse['stage_flow'][number]): string {
  return stageKindLabel(stage.kind)
}

function policyCount(stats: StageStats | undefined): number | null {
  return stats ? stats.policy_count : null
}

function teamCount(stats: StageStats | undefined): number | null {
  return stats ? (stats.team_count ?? null) : null
}

function poolMetrics(
  stage: ProgressResponse['stage_flow'][number],
  inputStats: StageStats | undefined,
  outputStats: StageStats | undefined
): Pick<StageProgressItem, 'entrantLabel' | 'entrantCount' | 'exitLabel' | 'exitCount'> {
  switch (stage.kind) {
    case 'sample_teams':
      return {
        entrantLabel: 'Starting policies',
        entrantCount: policyCount(inputStats),
        exitLabel: 'Resulting teams',
        exitCount: teamCount(outputStats),
      }
    case 'team_eval':
      return {
        entrantLabel: 'Starting teams',
        entrantCount: teamCount(inputStats),
        exitLabel: 'Resulting teams',
        exitCount: teamCount(outputStats),
      }
    case 'score_policies':
      return {
        entrantLabel: 'Starting teams',
        entrantCount: teamCount(inputStats),
        exitLabel: 'Resulting policies',
        exitCount: policyCount(outputStats),
      }
    case 'policy_eval':
    default:
      return {
        entrantLabel: 'Starting policies',
        entrantCount: policyCount(inputStats),
        exitLabel: 'Resulting policies',
        exitCount: policyCount(outputStats),
      }
  }
}

export function buildStageProgressItems(
  stageFlow: ProgressResponse['stage_flow'],
  stages: StageStats[]
): StageProgressItem[] {
  const statsByPool = new Map(stages.map((stage) => [stage.name, stage]))

  return stageFlow.map((stage) => {
    const inputStats = statsByPool.get(stage.input_pool)
    const outputStats = statsByPool.get(stage.output_pool)
    const metrics = poolMetrics(stage, inputStats, outputStats)
    return {
      index: stage.index,
      inputPool: stage.input_pool,
      outputPool: stage.output_pool,
      status: stage.status,
      title: stageTitle(stage),
      description: stage.description,
      showMatchCount: stage.kind !== 'sample_teams',
      matchCount: inputStats?.match_count ?? 0,
      completionPct: inputStats?.completion_pct ?? 0,
      ...metrics,
    }
  })
}
