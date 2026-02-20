import type { ProgressResponse, StageStats } from '@/lib/api'

import { stageKindLabel, type TournamentStageFlowEntry } from './stages'

export type StageProgressItem = {
  index: number
  inputPool: string
  outputPool: string
  status: TournamentStageFlowEntry['status']
  title: string
  description: string
  poolsLine: string
  matchCount: number
  completionPct: number
}

function stageTitle(stage: ProgressResponse['stage_flow'][number]): string {
  return stageKindLabel(stage.kind)
}

export function buildStageProgressItems(
  stageFlow: ProgressResponse['stage_flow'],
  stages: StageStats[]
): StageProgressItem[] {
  const statsByPool = new Map(stages.map((stage) => [stage.name, stage]))

  return stageFlow.map((stage) => {
    const stats = statsByPool.get(stage.input_pool)
    return {
      index: stage.index,
      inputPool: stage.input_pool,
      outputPool: stage.output_pool,
      status: stage.status,
      title: stageTitle(stage),
      description: stage.description,
      poolsLine: `${stage.input_pool} → ${stage.output_pool}`,
      matchCount: stats?.match_count ?? 0,
      completionPct: stats?.completion_pct ?? 0,
    }
  })
}
