import type {
  DashboardAnalysisResponse,
  DashboardResponse,
  DashboardRolePercentilesResponse,
  DiagnoseDoctorNote,
  DiagnoseManifest,
  DiagnoseRunsResponse,
  DiagnoseUploadResponse,
  PantheonStoriesResponse,
} from './api.types'

export * from './api.types'

const DEFAULT_BASE_URL = 'http://127.0.0.1:8010'
const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME?.trim() || 'observatory_auth_token'
const SESSION_TOKEN_KEY = 'policy-dashboard-auth-token'
const POLICY_VERSIONS_BASE_PATH = '/dashboard/v1/policies/versions'
const DIAGNOSE_RUNS_BASE_PATH = '/dashboard/v1/cogames-diagnose/runs'

export const DASHBOARD_API_BASE_URL =
  process.env.NEXT_PUBLIC_DASHBOARD_API_BASE_URL?.replace(/\/$/, '') ?? DEFAULT_BASE_URL

type RequestMethod = 'GET' | 'POST'
type RequestBody = string | FormData | undefined
type RequestOptions = {
  method?: RequestMethod
  body?: RequestBody
  headers?: Record<string, string>
}
type DashboardDefaultPolicyVersionResponse = {
  policy_version_id: string
}

function trimToNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

function readFragmentToken(): string | null {
  if (typeof window === 'undefined') return null

  const url = new URL(window.location.href)
  const fragment = url.hash.startsWith('#') ? url.hash.slice(1) : url.hash
  if (!fragment) return null

  try {
    const token = trimToNull(decodeURIComponent(fragment))
    if (!token) return null
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, token)
    window.history.replaceState({}, '', `${url.pathname}${url.search}`)
    return token
  } catch {
    return null
  }
}

function readCookieToken(): string | null {
  if (typeof document === 'undefined') return null

  for (const part of document.cookie.split('; ')) {
    if (!part.startsWith(`${AUTH_COOKIE_NAME}=`)) continue
    return trimToNull(part.slice(AUTH_COOKIE_NAME.length + 1))
  }
  return null
}

function requestHeaders(extraHeaders?: Record<string, string>, body?: RequestBody): Record<string, string> {
  const headers: Record<string, string> = body instanceof FormData ? {} : { 'Content-Type': 'application/json' }
  const sessionToken =
    typeof window === 'undefined' ? null : trimToNull(window.sessionStorage.getItem(SESSION_TOKEN_KEY))
  const token = readFragmentToken() ?? sessionToken ?? readCookieToken()

  if (token) {
    headers['X-Auth-Token'] = token
  }
  if (!extraHeaders) {
    return headers
  }
  for (const [key, value] of Object.entries(extraHeaders)) {
    if (!value) continue
    headers[key] = value
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

function isNetworkLikeError(error: unknown): boolean {
  if (error instanceof TypeError) return true
  const message = error instanceof Error ? error.message : String(error)
  const lowered = message.toLowerCase()
  return lowered.includes('failed to fetch') || lowered.includes('networkerror')
}

function networkErrorMessage(): string {
  if (isLocalApiBaseUrl(DASHBOARD_API_BASE_URL)) {
    return (
      `Network/CORS error reaching ${DASHBOARD_API_BASE_URL}. ` +
      `Run the local backend on http://127.0.0.1:8010 and set ` +
      `NEXT_PUBLIC_DASHBOARD_API_BASE_URL=http://127.0.0.1:8010.`
    )
  }
  return (
    `Network/CORS error reaching ${DASHBOARD_API_BASE_URL}. ` +
    `Check VPN/network access and verify the dashboard API is reachable from your environment.`
  )
}

async function sleep(ms: number): Promise<void> {
  return await new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

async function parseJsonOrThrow(response: Response): Promise<unknown> {
  const text = await response.text()
  const maybeJson = text ? (JSON.parse(text) as unknown) : null

  if (response.ok) {
    return maybeJson
  }

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
  throw new Error(`${response.status}: ${String(jsonObject?.detail ?? jsonObject?.message ?? response.statusText)}`)
}

async function dashboardRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET'
  const send = async (): Promise<Response> => {
    try {
      return await fetch(`${DASHBOARD_API_BASE_URL}${path}`, {
        method,
        headers: requestHeaders(options.headers, options.body),
        body: options.body,
        cache: 'no-store',
      })
    } catch (error) {
      if (!isNetworkLikeError(error)) throw error
      throw new Error(networkErrorMessage())
    }
  }

  let response = await send()
  if (response.status === 503 && method === 'GET') {
    await sleep(350)
    response = await send()
  }
  return (await parseJsonOrThrow(response)) as T
}

function policyVersionPath(policyVersionId: string, suffix: string): string {
  return `${POLICY_VERSIONS_BASE_PATH}/${encodeURIComponent(policyVersionId)}${suffix}`
}

function diagnoseRunPath(runId: string, suffix: string): string {
  return `${DIAGNOSE_RUNS_BASE_PATH}/${encodeURIComponent(runId)}${suffix}`
}

export async function fetchDashboardData(policyVersionId: string): Promise<DashboardResponse> {
  return await dashboardRequest<DashboardResponse>(policyVersionPath(policyVersionId, '/data'))
}

export async function fetchDashboardDefaultData(): Promise<DashboardResponse> {
  try {
    return await dashboardRequest<DashboardResponse>(`${POLICY_VERSIONS_BASE_PATH}/default/data`)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    if (!message.startsWith('422: Invalid policy version id format') && !message.startsWith('404:')) {
      throw error
    }
  }

  const defaultVersion = await dashboardRequest<DashboardDefaultPolicyVersionResponse>(
    `${POLICY_VERSIONS_BASE_PATH}/default`
  )
  const policyVersionId = defaultVersion.policy_version_id.trim()
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
  return await dashboardRequest<DashboardAnalysisResponse>(policyVersionPath(policyVersionId, '/analysis'), {
    method: 'POST',
    body: '{}',
    headers: key ? { 'X-Anthropic-Api-Key': key } : undefined,
  })
}

export async function fetchDashboardRolePercentiles(
  policyVersionId: string
): Promise<DashboardRolePercentilesResponse> {
  return await dashboardRequest<DashboardRolePercentilesResponse>(
    policyVersionPath(policyVersionId, '/role-percentiles')
  )
}

export async function fetchDiagnoseRuns(): Promise<DiagnoseRunsResponse> {
  return await dashboardRequest<DiagnoseRunsResponse>(DIAGNOSE_RUNS_BASE_PATH)
}

export async function fetchDiagnoseManifest(runId: string): Promise<DiagnoseManifest> {
  return await dashboardRequest<DiagnoseManifest>(diagnoseRunPath(runId, '/manifest'))
}

export async function fetchDiagnoseDoctorNote(runId: string): Promise<DiagnoseDoctorNote> {
  return await dashboardRequest<DiagnoseDoctorNote>(diagnoseRunPath(runId, '/doctor-note'))
}

export async function uploadDiagnoseBundle(bundle: File): Promise<DiagnoseUploadResponse> {
  const formData = new FormData()
  formData.append('bundle', bundle)
  return await dashboardRequest<DiagnoseUploadResponse>(`${DIAGNOSE_RUNS_BASE_PATH}/upload`, {
    method: 'POST',
    body: formData,
  })
}

export async function fetchPantheonStories(): Promise<PantheonStoriesResponse> {
  return await dashboardRequest<PantheonStoriesResponse>('/dashboard/v1/pantheon/stories')
}

export function diagnoseArtifactUrl(runId: string, artifact: string): string {
  return `${DASHBOARD_API_BASE_URL}${diagnoseRunPath(runId, `/artifacts/${encodeURIComponent(artifact)}`)}`
}
