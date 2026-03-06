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
      throw new Error('401: Failed to authenticate. Refresh Observatory login and reopen Diagnose.')
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
