const DEFAULT_BASE_URL = 'http://127.0.0.1:8010'
const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME?.trim() || 'observatory_auth_token'
const DASHBOARD_AUTH_TOKEN_SESSION_STORAGE_KEY = 'policy-dashboard-auth-token'

export const DASHBOARD_API_BASE_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_API_BASE_URL?.replace(/\/$/, '') ?? DEFAULT_BASE_URL

function trimToNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

function readAuthTokenFromUrlFragment(): string | null {
  if (typeof window === 'undefined') return null
  const currentUrl = new URL(window.location.href)
  const rawFragment = currentUrl.hash.startsWith('#') ? currentUrl.hash.slice(1) : currentUrl.hash
  if (!rawFragment) return null

  let decodedFragment = rawFragment
  try {
    decodedFragment = decodeURIComponent(rawFragment)
  } catch {
    return null
  }
  const token = trimToNull(decodedFragment)
  if (!token) return null

  window.sessionStorage.setItem(DASHBOARD_AUTH_TOKEN_SESSION_STORAGE_KEY, token)
  window.history.replaceState({}, '', `${currentUrl.pathname}${currentUrl.search}`)
  return token
}

function readAuthTokenFromCookies(): string | null {
  if (typeof document === 'undefined') return null
  const parts = document.cookie.split('; ')
  for (const part of parts) {
    if (!part.startsWith(`${AUTH_COOKIE_NAME}=`)) continue
    return trimToNull(part.slice(AUTH_COOKIE_NAME.length + 1))
  }
  return null
}

function getDashboardRequestHeaders(extraHeaders?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const sessionToken =
    typeof window === 'undefined'
      ? null
      : trimToNull(window.sessionStorage.getItem(DASHBOARD_AUTH_TOKEN_SESSION_STORAGE_KEY))
  const token = readAuthTokenFromUrlFragment() ?? sessionToken ?? readAuthTokenFromCookies()
  if (token) {
    headers['X-Auth-Token'] = token
  }
  if (extraHeaders) {
    for (const [key, value] of Object.entries(extraHeaders)) {
      if (!value) continue
      headers[key] = value
    }
  }
  return headers
}

function isLocalApiBaseUrl(apiBaseUrl: string): boolean {
  try {
    const parsed = new URL(apiBaseUrl)
    return parsed.hostname === '127.0.0.1' || parsed.hostname === 'localhost'
  } catch {
    return apiBaseUrl.includes('127.0.0.1') || apiBaseUrl.includes('localhost')
  }
}

export type DashboardEpisode = {
  episode_id: string
  id?: string
  job_id?: string
  created_at?: string | null
  replay_url?: string | null
  thumbnail_url?: string | null
  status: string
  avg_reward?: number
  reward: number
  opponent_name: string
  opponent_version?: number
  team_composition: string
  diagnostic_tags: string[]
  behavior_tags?: string[]
  error_type?: string | null
  error_message?: string | null
  steps: number
  metrics?: Record<string, unknown>
  [key: string]: unknown
}

export type DashboardKpis = {
  diagnostics?: string[]
  avg_reward?: number
  mean_reward?: number
  success_rate?: number
  failure_rate?: number
  total_episodes?: number
  noop_rate?: number
  reward_consistency?: number
  reward_nonzero_pct?: number
  vibe_change_rate?: number
  net_alignment_rate?: number
  hearts_to_junction_rate?: number
  resource_efficiency_per_step?: number
  resource_retention?: number
  junction_control_rate?: number
  alignment_stability?: number
  move_efficiency?: number
  action_success_rate?: number
  freeze_vulnerability?: number
  profile_aggressive?: number
  profile_defensive?: number
  profile_resource_hoarder?: number
  profile_junction_hunter?: number
  profile_mobile_scout?: number
  [key: string]: unknown
}

export type DashboardFailures = {
  total_episodes?: number
  completed_episodes?: number
  failed_episodes?: number
  failed_rate?: number
  timeout_failures?: number
  oom_failures?: number
  crash_failures?: number
  other_failures?: number
  freeze_heavy_completed?: number
  noop_heavy_completed?: number
  [key: string]: unknown
}

export type DashboardOutcomeSnapshot = {
  id?: string
  name?: string
  version?: number
  rank?: number | null
  score?: number | null
  matches?: number
  season?: string
  [key: string]: unknown
}

export type DashboardOutcomeDelta = {
  rank_delta?: number | null
  score_delta?: number | null
  matches_delta?: number | null
  [key: string]: unknown
}

export type DashboardOutcome = {
  verdict?: string
  evidence_sufficient?: boolean
  reason?: string
  current?: DashboardOutcomeSnapshot
  baseline?: DashboardOutcomeSnapshot | null
  delta?: DashboardOutcomeDelta
  [key: string]: unknown
}

export type DashboardOpponentStats = {
  count: number
  total_reward: number
  avg_reward: number
  avg_metrics: Record<string, number>
  strategy_profile: Record<string, number>
  [key: string]: unknown
}

export type DashboardTeamCompStats = {
  composition?: string
  count?: number
  avg_reward?: number
  avg_move_efficiency?: number
  avg_junction_aligned?: number
  avg_resource_gained?: number
  [key: string]: unknown
}

export type DashboardMatchupSlice = {
  key?: string
  count?: number
  avg_reward?: number
  delta_vs_policy?: number
  baseline_count?: number | null
  baseline_avg_reward?: number | null
  delta_vs_baseline?: number | null
  [key: string]: unknown
}

export type DashboardMatchupSummary = {
  evidence_sufficient?: boolean
  interaction_specific_issue?: boolean
  reason?: string
  current_avg_reward?: number
  baseline_avg_reward?: number | null
  global_reward_delta?: number | null
  opponent_spread?: number
  best_opponent?: string | null
  worst_opponent?: string | null
  composition_spread?: number
  best_composition?: string | null
  worst_composition?: string | null
  opponent_slices?: DashboardMatchupSlice[]
  composition_slices?: DashboardMatchupSlice[]
  [key: string]: unknown
}

export type DashboardTrendPoint = {
  id?: string
  name?: string
  version?: number
  rank?: number | null
  score?: number | null
  matches?: number
  has_leaderboard_data?: boolean
  [key: string]: unknown
}

export type DashboardTrendSummary = {
  evidence_sufficient?: boolean
  direction?: string
  reason?: string
  score_delta_from_oldest?: number | null
  rank_delta_from_oldest?: number | null
  points?: DashboardTrendPoint[]
  [key: string]: unknown
}

export type DashboardTrendExplorerSeries = {
  key: string
  label: string
  higher_is_better?: boolean
  direction?: string
  reason?: string
  values?: Array<number | null>
  deltas?: Array<number | null>
  [key: string]: unknown
}

export type DashboardTrendDistribution = {
  count?: number
  mean?: number | null
  median?: number | null
  p10?: number | null
  p90?: number | null
  [key: string]: unknown
}

export type DashboardTrendMetricOverlay = {
  key: string
  label?: string
  higher_is_better?: boolean
  current_value?: number | null
  current_display?: string
  team?: DashboardTrendDistribution
  population?: DashboardTrendDistribution
  delta_vs_team_mean?: number | null
  delta_vs_population_mean?: number | null
  signal?: string
  reason?: string
  [key: string]: unknown
}

export type DashboardSubmissionPatternGroup = {
  code?: string
  title?: string
  metric_key?: string
  severity?: string
  count?: number
  versions?: string[]
  evidence?: string
  next_action?: string
  [key: string]: unknown
}

export type DashboardTrendExplorerSummary = {
  evidence_sufficient?: boolean
  selected_metric?: string
  version_labels?: string[]
  series?: DashboardTrendExplorerSeries[]
  metric_overlays?: DashboardTrendMetricOverlay[]
  submission_patterns?: DashboardSubmissionPatternGroup[]
  [key: string]: unknown
}

export type DashboardConfidenceInterval = {
  key?: string
  label?: string
  point_estimate?: number | null
  lower?: number | null
  upper?: number | null
  crosses_zero?: boolean | null
  current_samples?: number
  baseline_samples?: number
  interpretation?: string
  [key: string]: unknown
}

export type DashboardConfidenceSummary = {
  evidence_sufficient?: boolean
  intervals?: DashboardConfidenceInterval[]
  recommended_actions?: string[]
  [key: string]: unknown
}

export type DashboardPatternSignal = {
  code?: string
  title?: string
  severity?: string
  confidence?: string
  evidence?: string
  next_action?: string
  [key: string]: unknown
}

export type DashboardPatternSummary = {
  evidence_sufficient?: boolean
  headline?: string
  signals?: DashboardPatternSignal[]
  [key: string]: unknown
}

export type DashboardUnsupportedIssue = {
  code?: string
  severity?: string
  message?: string
  affected_count?: number
  total_count?: number
  recommended_action?: string
  [key: string]: unknown
}

export type DashboardUnsupportedSummary = {
  has_unsupported_state?: boolean
  issues?: DashboardUnsupportedIssue[]
  [key: string]: unknown
}

export type DashboardInstrumentationCheck = {
  key?: string
  kind?: string
  required?: boolean
  present_count?: number
  total_count?: number
  coverage?: number
  status?: string
  message?: string
  [key: string]: unknown
}

export type DashboardInstrumentationSummary = {
  template_version?: string
  min_coverage_threshold?: number
  compliant?: boolean
  score?: number
  checks?: DashboardInstrumentationCheck[]
  recommended_actions?: string[]
  [key: string]: unknown
}

export type DashboardStatsInventoryField = {
  key?: string
  kind?: string
  present_count?: number
  total_count?: number
  coverage?: number
  [key: string]: unknown
}

export type DashboardStatsInventorySummary = {
  total_episodes?: number
  completed_episodes?: number
  failed_episodes?: number
  distinct_metric_keys?: number
  distinct_tag_keys?: number
  top_metric_keys?: DashboardStatsInventoryField[]
  top_tag_keys?: DashboardStatsInventoryField[]
  notes?: string[]
  [key: string]: unknown
}

export type DashboardActionSummary = {
  rollout_recommendation?: string
  headline?: string
  actions?: string[]
  [key: string]: unknown
}

export type DashboardOrchestrationExperimentHook = {
  id?: string
  priority?: number
  title?: string
  objective?: string
  rationale?: string
  actions?: string[]
  acceptance_checks?: string[]
  [key: string]: unknown
}

export type DashboardOrchestrationPayloadTemplate = {
  template_version?: string
  policy_version_id?: string
  rollout_gate?: string
  mode?: string
  experiment_ids?: string[]
  [key: string]: unknown
}

export type DashboardOrchestrationSummary = {
  evidence_sufficient?: boolean
  mode?: string
  headline?: string
  experiments?: DashboardOrchestrationExperimentHook[]
  payload_template?: DashboardOrchestrationPayloadTemplate
  [key: string]: unknown
}

export type DashboardCrashDumpSignature = {
  signature?: string
  count?: number
  error_type?: string
  example_message?: string | null
  [key: string]: unknown
}

export type DashboardCrashDumpEntry = {
  episode_id?: string
  job_id?: string
  created_at?: string | null
  error_type?: string | null
  error_message?: string | null
  analysis_command?: string
  replay_url?: string | null
  [key: string]: unknown
}

export type DashboardCrashDumpSummary = {
  evidence_sufficient?: boolean
  headline?: string
  total_failed?: number
  signatures?: DashboardCrashDumpSignature[]
  entries?: DashboardCrashDumpEntry[]
  [key: string]: unknown
}

export type DashboardCapabilityCodeStatus = {
  status?: 'yes' | 'partial' | 'no' | 'planned' | string
  support_type?: 'trained' | 'backed' | string
  training_source?: string | null
  evidence?: string[]
  [key: string]: unknown
}

export type DashboardCapabilityCodeAudit = {
  template_version?: string
  generated_at?: string
  capabilities?: Record<string, DashboardCapabilityCodeStatus>
  sources?: Record<string, DashboardCapabilityCodeStatus>
  [key: string]: unknown
}

export type DashboardDerived = {
  kpis: DashboardKpis
  failures: DashboardFailures
  team_comp?: DashboardTeamCompStats[]
  opponent_metrics: Record<string, DashboardOpponentStats>
  outcome?: DashboardOutcome
  matchup?: DashboardMatchupSummary | null
  trend?: DashboardTrendSummary | null
  trend_explorer?: DashboardTrendExplorerSummary | null
  confidence?: DashboardConfidenceSummary | null
  patterns?: DashboardPatternSummary | null
  unsupported?: DashboardUnsupportedSummary | null
  instrumentation?: DashboardInstrumentationSummary | null
  stats_inventory?: DashboardStatsInventorySummary | null
  actions?: DashboardActionSummary | null
  orchestration?: DashboardOrchestrationSummary | null
  crash_dump?: DashboardCrashDumpSummary | null
  capability_code_audit?: DashboardCapabilityCodeAudit | null
  [key: string]: unknown
}

export type DashboardPolicy = {
  id: string
  name: string
  version: number
  rank?: number | null
  score?: number | null
  matches?: number
  [key: string]: unknown
}

export type DashboardSelection = {
  sampled_episode_count: number
  limit?: number
  offset?: number
  ordering?: string
  includes_failed_jobs_without_episode?: boolean
  baseline_limit?: number | null
  [key: string]: unknown
}

export type DashboardResponse = {
  policy: DashboardPolicy
  season: string
  generated_at: string
  episodes: DashboardEpisode[]
  derived: DashboardDerived
  selection: DashboardSelection
  role_percentiles?: DashboardRolePercentilesResponse | null
  diagnose_runs?: DiagnoseRunSummary[] | null
  [key: string]: unknown
}

export type DashboardAnalysisResponse = {
  analysis: string
  data_sources: string[]
}

export type DashboardRoleMetricDef = {
  key: string
  source_names: string[]
  higher_is_better: boolean
  include_in_overall?: boolean
  overall_weight?: number
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

export type DiagnoseValidityCheck = {
  check_id: string
  passed: boolean
  details: string
}

export type DiagnoseValidityReport = {
  valid: boolean
  failed_check_ids: string[]
  checks: DiagnoseValidityCheck[]
}

export type DiagnoseInterpretationStability = {
  stable: boolean
  snapshot_count?: number
  dominant_issue_stable?: boolean
  top_symptom_stable?: boolean
  notes?: string[]
  [key: string]: unknown
}

export type DiagnoseManifest = {
  run_id: string
  created_at: string
  command: string
  policy: string
  pack_id: string
  pack_version: string
  stage_status: string
  run_status: string
  artifact_files: string[]
  diagnose_validity: DiagnoseValidityReport
  interpretation_stability: DiagnoseInterpretationStability
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

export type DiagnoseTournamentObjectiveContext = {
  aligned_junction_held_stage1?: number | null
  aligned_junction_held_stage2_absolute?: number | null
  aligned_junction_held_stage2_mirror?: number | null
}

export type DiagnoseSocialReview = {
  confirmed: boolean
  severity: number
  confidence: number
  summary: string
  evidence_refs?: string[]
  [key: string]: unknown
}

export type DiagnoseStage2DiagnosisDelta = {
  stage1_dominant_issue: string
  final_dominant_issue: string
  changed: boolean
  summary: string
  evidence_refs: string[]
  [key: string]: unknown
}

export type DiagnoseEvidenceIndex = {
  metric_refs?: string[]
  replay_refs?: string[]
  baseline_refs?: string[]
  [key: string]: unknown
}

export type DiagnoseDoctorNote = {
  run_id: string
  status: string
  diagnosis_status?: string
  stage_status: string
  dominant_issue: string
  notes: string[]
  axes: DiagnoseAxisScore[]
  stage1_probe_catalog: DiagnoseProbeDefinition[]
  stage1_probe_evaluations: DiagnoseProbeEvaluation[]
  symptoms: DiagnoseSymptom[]
  prescriptions: DiagnosePrescription[]
  tournament_objective_context: DiagnoseTournamentObjectiveContext
  social_review?: DiagnoseSocialReview | null
  stage2_diagnosis_delta?: DiagnoseStage2DiagnosisDelta | null
  evidence_index: DiagnoseEvidenceIndex
  [key: string]: unknown
}

export type DiagnoseRunSummary = {
  run_id: string
  manifest: DiagnoseManifest | null
}

export type DiagnoseRunsResponse = {
  runs: DiagnoseRunSummary[]
}

export type DiagnoseUploadResponse = {
  run_id: string
  manifest: DiagnoseManifest | null
}

type DashboardRequestMethod = 'GET' | 'POST'
type DashboardRequestBody = string | FormData | undefined

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

async function parseJsonOrThrow(response: Response): Promise<unknown> {
  const text = await response.text()
  let maybeJson: unknown = null
  if (text) {
    try {
      maybeJson = JSON.parse(text)
    } catch {
      maybeJson = null
    }
  }
  if (!response.ok) {
    const jsonObject =
      maybeJson && typeof maybeJson === 'object' && !Array.isArray(maybeJson)
        ? (maybeJson as Record<string, unknown>)
        : null
    if (response.status === 401) {
      throw new Error('401: Failed to authenticate. Refresh Observatory login and reopen Policy Dashboard.')
    }
    if (response.status === 503) {
      throw new Error('503: Service temporarily unavailable - please try again.')
    }
    const detail = jsonObject?.detail ?? jsonObject?.message ?? response.statusText
    throw new Error(`${response.status}: ${String(detail)}`)
  }
  return maybeJson
}

async function dashboardRequest<T>(
  path: string,
  method: DashboardRequestMethod = 'GET',
  body?: DashboardRequestBody,
  extraHeaders?: Record<string, string>
): Promise<T> {
  const send = async (): Promise<Response> => {
    try {
      const headers = getDashboardRequestHeaders(extraHeaders)
      if (typeof FormData !== 'undefined' && body instanceof FormData) {
        delete headers['Content-Type']
      }
      return await fetch(`${DASHBOARD_API_BASE_URL}${path}`, {
        method,
        headers,
        body,
        cache: 'no-store',
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const isNetworkLikeError =
        error instanceof TypeError ||
        message.toLowerCase().includes('failed to fetch') ||
        message.toLowerCase().includes('networkerror')
      if (!isNetworkLikeError) {
        throw error
      }
      if (isLocalApiBaseUrl(DASHBOARD_API_BASE_URL)) {
        throw new Error(
          `Network/CORS error reaching ${DASHBOARD_API_BASE_URL}. ` +
            `Run the local backend on http://127.0.0.1:8010 and set ` +
            `NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010.`
        )
      }
      throw new Error(
        `Network/CORS error reaching ${DASHBOARD_API_BASE_URL}. ` +
          `Check VPN/network access and verify the dashboard API is reachable from your environment.`
      )
    }
  }

  let response = await send()
  if (response.status === 503 && method === 'GET') {
    await sleep(350)
    response = await send()
  }

  return (await parseJsonOrThrow(response)) as T
}

export async function fetchDashboardData(policyVersionId: string): Promise<DashboardResponse> {
  const query = new URLSearchParams({ include: 'role_percentiles,diagnose_runs' }).toString()
  return await dashboardRequest<DashboardResponse>(
    `/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/data?${query}`
  )
}

type DashboardDefaultPolicyVersionResponse = {
  policy_version_id: string
}

export async function fetchDashboardDefaultData(): Promise<DashboardResponse> {
  const query = new URLSearchParams({ include: 'role_percentiles,diagnose_runs' }).toString()
  try {
    return await dashboardRequest<DashboardResponse>(`/dashboard/v1/policies/versions/default/data?${query}`)
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    const needsFallback = message.startsWith('422: Invalid policy version id format') || message.startsWith('404:')
    if (!needsFallback) throw err
  }

  const defaultVersion = await dashboardRequest<DashboardDefaultPolicyVersionResponse>(
    '/dashboard/v1/policies/versions/default'
  )
  const policyVersionId = String(defaultVersion.policy_version_id ?? '').trim()
  if (!policyVersionId) {
    throw new Error('500: Default policy endpoint returned empty policy_version_id')
  }
  return await fetchDashboardData(policyVersionId)
}

export async function fetchDashboardAnalysis(
  policyVersionId: string,
  anthropicApiKey?: string | null
): Promise<DashboardAnalysisResponse> {
  const key = anthropicApiKey?.trim()
  return await dashboardRequest<DashboardAnalysisResponse>(
    `/dashboard/v1/policies/versions/${encodeURIComponent(policyVersionId)}/analysis`,
    'POST',
    '{}',
    key ? { 'X-Anthropic-Api-Key': key } : undefined
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

export async function uploadDiagnoseBundle(bundle: File): Promise<DiagnoseUploadResponse> {
  const formData = new FormData()
  formData.append('bundle', bundle)
  return await dashboardRequest<DiagnoseUploadResponse>('/dashboard/v1/cogames-diagnose/runs/upload', 'POST', formData)
}

export function diagnoseArtifactUrl(runId: string, artifact: string): string {
  return `${DASHBOARD_API_BASE_URL}/dashboard/v1/cogames-diagnose/runs/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(artifact)}`
}
