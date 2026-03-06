const FORWARDED_HEADER_MAPPINGS = [
  ['x-auth-token', 'X-Auth-Token'],
  ['authorization', 'Authorization'],
  ['x-auth-secret', 'X-Auth-Secret'],
  ['x-user-id', 'X-User-Id'],
  ['x-user-email', 'X-User-Email'],
  ['x-user-is-softmax-team-member', 'X-User-Is-Softmax-Team-Member'],
] as const

function authCookieName(): string {
  return (
    process.env.OBSERVATORY_AUTH_COOKIE_NAME?.trim() ||
    process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME?.trim() ||
    'observatory_auth_token'
  )
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
