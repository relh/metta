const DEFAULT_BASE_URL = 'http://127.0.0.1:8010'
const AUTH_COOKIE_NAME = 'observatory_auth_token'

export const DASHBOARD_API_BASE_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_API_BASE_URL?.replace(/\/$/, '') ?? DEFAULT_BASE_URL

export type DashboardEpisode = {
  episode_id: string
  status: string
  reward: number
  opponent_name: string
  team_composition: string
  diagnostic_tags: string[]
  steps: number
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
}

export type DashboardFailures = {
  timeout_failures?: number
  oom_failures?: number
  crash_failures?: number
  other_failures?: number
}

export type DashboardOpponentMetric = {
  count: number
  total_reward: number
  avg_reward: number
  strategy_profile: Record<string, number>
}

export type DashboardDerived = {
  kpis: DashboardKpis
  failures: DashboardFailures
  opponent_metrics: Record<string, DashboardOpponentMetric>
  outcome?: {
    verdict?: string
    evidence_sufficient?: boolean
    reason?: string
  }
}

export type DashboardResponse = {
  policy: { id: string; name: string; version: number }
  season: string
  generated_at: string
  episodes: DashboardEpisode[]
  derived: DashboardDerived
  selection: { sampled_episode_count: number }
}

export type DashboardAnalysisResponse = {
  analysis: string
  data_sources: string[]
}

export type DashboardRoleMetricDef = {
  key: string
  source_names: string[]
  higher_is_better: boolean
}

export type DashboardRolePercentileMetric = {
  avg?: number
  percentile?: number
  higher_is_better?: boolean
  samples?: number
  source_names?: string[]
  source_metrics?: Record<string, unknown>
}

export type DashboardRolePercentileRow = {
  role: string
  percentile: number
  details?: {
    metrics?: Record<string, DashboardRolePercentileMetric>
    overall_percentile?: number
    [key: string]: unknown
  }
  updated_at: string
}

export type DashboardRolePercentilesResponse = {
  pool_id: string | null
  pool_name: string | null
  roles: Record<string, DashboardRoleMetricDef[]>
  rows: DashboardRolePercentileRow[]
}

export type DiagnoseAxis = 'stability' | 'efficiency' | 'control' | 'social_coordination'

export type DiagnoseManifest = {
  run_id: string
  created_at: string
  command: string
  policy: string
  pack_id: string
  pack_version: string
  stage_status: string
  run_status: string
  artifact_files?: string[]
  [key: string]: unknown
}

export type DiagnoseAxisScore = {
  axis: DiagnoseAxis
  normalized_score: number
  raw_score: number
  confirmed: boolean
  derived_metrics: {
    reward_variance: number
    non_zero_episode_pct: number
    timeout_rate: number
    mean_move_success: number
    mean_action_failed: number
    mean_stuck_steps: number
    [key: string]: number
  }
  [key: string]: unknown
}

export type DiagnoseProbeDefinition = {
  probe_id: string
  axis: DiagnoseAxis
  mission: string
  question: string
  validation_metric: string
  pass_fail_threshold: string
  [key: string]: unknown
}

export type DiagnoseProbeEvaluation = {
  probe_id: string
  axis: DiagnoseAxis
  passed: boolean
  summary: string
  evidence_refs: string[]
  [key: string]: unknown
}

export type DiagnoseSymptom = {
  symptom_id: string
  axis: DiagnoseAxis
  severity: number
  confidence: number
  likely_cause: string
  action: string
  expected_effect: string
  [key: string]: unknown
}

export type DiagnosePrescription = {
  symptom_id: string
  action: string
  owner: string
  validation_metric: string
  pass_fail_threshold: string
  [key: string]: unknown
}

export type DiagnoseDoctorNote = {
  run_id: string
  status: string
  stage_status: string
  dominant_issue: string
  notes: string[]
  axes: DiagnoseAxisScore[]
  stage1_probe_catalog: DiagnoseProbeDefinition[]
  stage1_probe_evaluations: DiagnoseProbeEvaluation[]
  symptoms: DiagnoseSymptom[]
  prescriptions: DiagnosePrescription[]
  [key: string]: unknown
}

export type DiagnoseRunSummary = {
  run_id: string
  manifest: DiagnoseManifest | null
}

export type DiagnoseRunsResponse = {
  runs: DiagnoseRunSummary[]
}

type DashboardRequestMethod = 'GET' | 'POST'

async function dashboardRequest<T>(path: string, method: DashboardRequestMethod = 'GET', body?: string): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (typeof document !== 'undefined') {
    for (const part of document.cookie.split('; ')) {
      if (!part.startsWith(`${AUTH_COOKIE_NAME}=`)) continue
      const token = part.slice(AUTH_COOKIE_NAME.length + 1).trim()
      if (token) headers['X-Auth-Token'] = token
      break
    }
  }

  const response = await fetch(`${DASHBOARD_API_BASE_URL}${path}`, {
    method,
    headers,
    body,
    cache: 'no-store',
  })

  const text = await response.text()
  const maybeJson = text ? JSON.parse(text) : null
  if (!response.ok) {
    if (response.status === 401) {
      throw new Error('401: Failed to authenticate. Refresh Observatory login and reopen Policy Dashboard.')
    }
    const detail = maybeJson?.detail ?? maybeJson?.message ?? response.statusText
    throw new Error(`${response.status}: ${String(detail)}`)
  }
  return maybeJson as T
}

export async function fetchDashboardData(policyVersionId: string): Promise<DashboardResponse> {
  return await dashboardRequest<DashboardResponse>(
    `/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/data`
  )
}

export async function fetchDashboardAnalysis(policyVersionId: string): Promise<DashboardAnalysisResponse> {
  return await dashboardRequest<DashboardAnalysisResponse>(
    `/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/analysis`,
    'POST',
    '{}'
  )
}

export async function fetchDashboardRolePercentiles(
  policyVersionId: string
): Promise<DashboardRolePercentilesResponse> {
  return await dashboardRequest<DashboardRolePercentilesResponse>(
    `/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/role-percentiles`
  )
}

export async function fetchDiagnoseRuns(): Promise<DiagnoseRunsResponse> {
  return await dashboardRequest<DiagnoseRunsResponse>('/dashboard/v1/cogames-diagnose/runs')
}

export async function fetchDiagnoseManifest(runId: string): Promise<DiagnoseManifest> {
  return await dashboardRequest<DiagnoseManifest>(
    `/dashboard/v1/cogames-diagnose/runs/${encodeURIComponent(runId)}/manifest`
  )
}

export async function fetchDiagnoseDoctorNote(runId: string): Promise<DiagnoseDoctorNote> {
  return await dashboardRequest<DiagnoseDoctorNote>(
    `/dashboard/v1/cogames-diagnose/runs/${encodeURIComponent(runId)}/doctor-note`
  )
}

export function diagnoseArtifactUrl(runId: string, artifact: string): string {
  return `${DASHBOARD_API_BASE_URL}/dashboard/v1/cogames-diagnose/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifact)}`
}
