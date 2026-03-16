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

function getDashboardRequestHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const sessionToken =
    typeof window === 'undefined'
      ? null
      : trimToNull(window.sessionStorage.getItem(DASHBOARD_AUTH_TOKEN_SESSION_STORAGE_KEY))
  const token = readAuthTokenFromUrlFragment() ?? sessionToken ?? readAuthTokenFromCookies()
  if (token) {
    headers['X-Auth-Token'] = token
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
      throw new Error('401: Failed to authenticate. Refresh Observatory login and reopen Pantheon.')
    }
    if (response.status === 503) {
      throw new Error('503: Service temporarily unavailable - please try again.')
    }
    const detail = jsonObject?.detail ?? jsonObject?.message ?? response.statusText
    throw new Error(`${response.status}: ${String(detail)}`)
  }

  return maybeJson
}

async function dashboardRequest<T>(path: string): Promise<T> {
  const send = async (): Promise<Response> => {
    try {
      return await fetch(`${DASHBOARD_API_BASE_URL}${path}`, {
        method: 'GET',
        headers: getDashboardRequestHeaders(),
        cache: 'no-store',
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      const isNetworkLikeError =
        error instanceof TypeError ||
        message.toLowerCase().includes('failed to fetch') ||
        message.toLowerCase().includes('networkerror')
      if (!isNetworkLikeError) throw error

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
  if (response.status === 503) {
    await sleep(350)
    response = await send()
  }
  return (await parseJsonOrThrow(response)) as T
}

export type PantheonStory = {
  story_id: string
  hall: 'fame' | 'same' | 'lame'
  title: string
  motif: string
  summary: string
  policy: string
  run_id?: string | null
  episode_id?: string | null
  replay_url?: string | null
  source?: string
  tags?: string[]
  created_at: string
}

export type PantheonStoriesResponse = {
  generated_at: string
  source_root?: string | null
  stories: PantheonStory[]
}

export async function fetchPantheonStories(): Promise<PantheonStoriesResponse> {
  return await dashboardRequest<PantheonStoriesResponse>('/pantheon/v1/stories')
}
