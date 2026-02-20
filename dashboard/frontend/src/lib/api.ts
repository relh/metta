const DEFAULT_BASE_URL = 'http://127.0.0.1:8010'

export const DASHBOARD_API_BASE_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_API_BASE_URL?.replace(/\/$/, '') ?? DEFAULT_BASE_URL

export type DashboardEpisode = {
  id?: string
  status?: string
  avg_reward?: number
  reward?: number
  opponent_name?: string
  team_composition?: string
  diagnostic_tags?: string[]
  [key: string]: unknown
}

export type DashboardKpis = {
  diagnostics?: string[]
  mean_reward?: number
  success_rate?: number
  failure_rate?: number
  total_episodes?: number
  resource_efficiency_per_step?: number
  resource_retention?: number
  junction_control_rate?: number
  alignment_stability?: number
  move_efficiency?: number
  action_success_rate?: number
  freeze_vulnerability?: number
  profile_aggressive?: number
  profile_mobile_scout?: number
  [key: string]: unknown
}

export type DashboardFailures = {
  timeout_failures?: number
  oom_failures?: number
  crash_failures?: number
  other_failures?: number
  [key: string]: unknown
}

export type DashboardDerived = {
  kpis?: DashboardKpis
  failures?: DashboardFailures
  outcome?: {
    verdict?: string
    evidence_sufficient?: boolean
    reason?: string
    [key: string]: unknown
  }
  [key: string]: unknown
}

export type DashboardResponse = {
  policy?: { id?: string; name?: string; version?: number }
  season?: string
  generated_at?: string
  episodes?: DashboardEpisode[]
  derived?: DashboardDerived
  selection?: { sampled_episode_count?: number; [key: string]: unknown }
  [key: string]: unknown
}

export type DashboardAnalysisResponse = {
  analysis: string
  data_sources: string[]
}

async function parseJsonOrThrow(response: Response) {
  const text = await response.text()
  const maybeJson = text ? JSON.parse(text) : null
  if (!response.ok) {
    const detail = maybeJson?.detail ?? maybeJson?.message ?? response.statusText
    throw new Error(`${response.status}: ${String(detail)}`)
  }
  return maybeJson
}

export async function fetchDashboardData(policyVersionId: string): Promise<DashboardResponse> {
  const response = await fetch(
    `${DASHBOARD_API_BASE_URL}/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/data`,
    {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
    }
  )
  return (await parseJsonOrThrow(response)) as DashboardResponse
}

export async function fetchDashboardAnalysis(policyVersionId: string): Promise<DashboardAnalysisResponse> {
  const response = await fetch(
    `${DASHBOARD_API_BASE_URL}/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/analysis`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
      cache: 'no-store',
    }
  )
  return (await parseJsonOrThrow(response)) as DashboardAnalysisResponse
}
