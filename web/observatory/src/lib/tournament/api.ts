import type {
  LeaderboardEntry,
  ProgressResponse,
  ScorePoliciesLeaderboardEntry,
  StageLeaderboardType,
  StageStats,
  TeamSummary,
} from '@/lib/api'
import type { Repo } from '@/lib/repo'

import { isTeamSeason, resolveSelectedStage, stageKindForPool } from './stages'

export type StageKind = ProgressResponse['stage_flow'][number]['kind']

export type SeasonStageContext = {
  teamSeason: boolean
  stages: StageStats[]
  progress: ProgressResponse | null
  selectedStage: string | null
  selectedStageKind: StageKind | null
  scorePoliciesPool: string | null
  scorePoliciesDescription: string | null
  hasTeams: boolean
}

export type StageLeaderboardData =
  | { kind: 'policy'; rows: LeaderboardEntry[] }
  | { kind: 'team'; rows: TeamSummary[] }
  | { kind: 'score-policies'; rows: ScorePoliciesLeaderboardEntry[] }

function stageKindToLeaderboardType(stageKind: StageKind | null): StageLeaderboardType {
  if (stageKind === 'team_eval') return 'team'
  if (stageKind === 'score_policies') return 'score-policies'
  return 'policy'
}

export async function getSeasonStageContext(
  repo: Repo,
  seasonName: string,
  rawStage: string | null = null
): Promise<SeasonStageContext> {
  const stages = await repo.getSeasonStages(seasonName)
  const teamSeason = isTeamSeason(stages)
  const progress = teamSeason ? await repo.getSeasonProgress(seasonName) : null
  const selectedStage = progress ? resolveSelectedStage(stages, progress.stage_flow, rawStage, progress.started) : null
  const selectedStageKind = progress && selectedStage ? stageKindForPool(progress.stage_flow, selectedStage) : null
  const scorePoliciesStage = progress?.stage_flow.find((stage) => stage.kind === 'score_policies') ?? null
  const scorePoliciesPool = scorePoliciesStage?.output_pool ?? null
  const scorePoliciesDescription = scorePoliciesStage?.description ?? null
  const hasTeams = stages.some((stage) => (stage.team_count ?? 0) > 0)

  return {
    teamSeason,
    stages,
    progress,
    selectedStage,
    selectedStageKind,
    scorePoliciesPool,
    scorePoliciesDescription,
    hasTeams,
  }
}

export function getTeamStages(stages: StageStats[], progress: ProgressResponse | null): StageStats[] {
  if (!progress) {
    return stages.filter((stage) => (stage.team_count ?? 0) > 0)
  }

  const stageByName = new Map(stages.map((stage) => [stage.name, stage]))
  return progress.stage_flow
    .filter((stage) => stage.kind === 'team_eval')
    .map((stage) => stageByName.get(stage.input_pool))
    .filter((stage): stage is StageStats => stage !== undefined && (stage.team_count ?? 0) > 0)
}

export function getPlayerStages(stages: StageStats[], progress: ProgressResponse | null): StageStats[] {
  if (!progress) {
    return stages
  }

  const stageByName = new Map(stages.map((stage) => [stage.name, stage]))
  const seen = new Set<string>()
  const playerStages: StageStats[] = []

  for (const stage of progress.stage_flow) {
    if (stage.kind !== 'policy_eval' && stage.kind !== 'team_eval') {
      continue
    }
    const stageStats = stageByName.get(stage.input_pool)
    if (!stageStats || seen.has(stageStats.name)) {
      continue
    }
    seen.add(stageStats.name)
    playerStages.push(stageStats)
  }

  return playerStages
}

export async function getStageLeaderboard(
  repo: Repo,
  seasonName: string,
  stage: string,
  stageKind: StageKind | null,
  scorePoliciesPool: string | null
): Promise<StageLeaderboardData> {
  const leaderboardType = stageKindToLeaderboardType(stageKind)
  const poolName = leaderboardType === 'score-policies' ? (scorePoliciesPool ?? stage) : stage

  if (leaderboardType === 'team') {
    return { kind: 'team', rows: await repo.getSeasonStageLeaderboard(seasonName, 'team', poolName) }
  }

  if (leaderboardType === 'score-policies') {
    return {
      kind: 'score-policies',
      rows: await repo.getSeasonStageLeaderboard(seasonName, 'score-policies', poolName),
    }
  }

  return { kind: 'policy', rows: await repo.getSeasonStageLeaderboard(seasonName, 'policy', poolName) }
}
