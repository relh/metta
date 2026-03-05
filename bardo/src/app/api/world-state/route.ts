import { NextRequest, NextResponse } from 'next/server'

const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store, max-age=0',
}

const FORWARDED_HEADER_MAPPINGS = [
  ['x-auth-token', 'X-Auth-Token'],
  ['authorization', 'Authorization'],
  ['x-auth-secret', 'X-Auth-Secret'],
  ['x-user-id', 'X-User-Id'],
  ['x-user-email', 'X-User-Email'],
  ['x-user-is-softmax-team-member', 'X-User-Is-Softmax-Team-Member'],
] as const

function bardoWorldStateUrl(): string {
  return (
    process.env.BARDO_WORLD_STATE_URL ||
    'http://127.0.0.1:8010/dashboard/v1/bardo/world-state'
  ).replace(/\/$/, '')
}

function authCookieName(): string {
  return process.env.OBSERVATORY_AUTH_COOKIE_NAME?.trim() || 'observatory_auth_token'
}

function trimToNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

type ProxyAuthRequest = {
  headers: Headers
  cookies: {
    get(name: string): { value: string } | undefined
  }
}

export function bardoProxyHeaders(request: ProxyAuthRequest): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  }

  for (const [incoming, outgoing] of FORWARDED_HEADER_MAPPINGS) {
    const value = trimToNull(request.headers.get(incoming))
    if (!value) continue
    headers[outgoing] = value
  }

  if (!headers['X-Auth-Token']) {
    const cookieToken = trimToNull(request.cookies.get(authCookieName())?.value)
    if (cookieToken) headers['X-Auth-Token'] = cookieToken
  }

  return headers
}

export async function GET(request: NextRequest) {
  const url = new URL(bardoWorldStateUrl())
  const nameFilter = request.nextUrl.searchParams.get('q')?.trim()
  if (nameFilter) {
    url.searchParams.set('q', nameFilter)
  }

  try {
    const response = await fetch(url, {
      cache: 'no-store',
      headers: bardoProxyHeaders(request),
    })
    const payload = await response.json()

    return NextResponse.json(payload, {
      status: response.status,
      headers: NO_STORE_HEADERS,
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    return NextResponse.json(
      { error: `Failed to load bardo world state: ${detail}` },
      { status: 502, headers: NO_STORE_HEADERS }
    )
  }
}
