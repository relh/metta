import { afterEach, describe, expect, it, vi } from 'vitest'

import { bardoProxyHeaders } from './proxy-headers'
import { GET } from './route'

const ORIGINAL_AUTH_COOKIE_NAME = process.env.OBSERVATORY_AUTH_COOKIE_NAME
const ORIGINAL_NEXT_PUBLIC_AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME

function fakeRequest(
  args: {
    headers?: Record<string, string>
    cookies?: Record<string, string>
  } = {}
) {
  const headers = new Headers(args.headers)
  const cookieMap = args.cookies ?? {}

  return {
    headers,
    cookies: {
      get(name: string) {
        const value = cookieMap[name]
        return value ? { value } : undefined
      },
    },
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()

  if (ORIGINAL_AUTH_COOKIE_NAME === undefined) {
    delete process.env.OBSERVATORY_AUTH_COOKIE_NAME
  } else {
    process.env.OBSERVATORY_AUTH_COOKIE_NAME = ORIGINAL_AUTH_COOKIE_NAME
  }

  if (ORIGINAL_NEXT_PUBLIC_AUTH_COOKIE_NAME === undefined) {
    delete process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME
  } else {
    process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME = ORIGINAL_NEXT_PUBLIC_AUTH_COOKIE_NAME
  }
})

function fakeRouteRequest(
  args: {
    query?: string
    headers?: Record<string, string>
    cookies?: Record<string, string>
  } = {}
) {
  const headers = new Headers(args.headers)
  const cookieMap = args.cookies ?? {}
  const query = args.query ? `?${args.query}` : ''

  return {
    nextUrl: new URL(`http://localhost/bardo/api/world-state${query}`),
    headers,
    cookies: {
      get(name: string) {
        const value = cookieMap[name]
        return value ? { value } : undefined
      },
    },
  }
}

describe('bardoProxyHeaders', () => {
  it('forwards auth identity headers and keeps explicit token over cookie token', () => {
    const request = fakeRequest({
      headers: {
        'x-auth-token': 'header-token',
        authorization: 'Bearer authz-token',
        'x-auth-secret': 'secret-token',
        'x-user-id': 'user-id',
        'x-user-email': 'user@softmax.com',
        'x-user-is-softmax-team-member': 'true',
      },
      cookies: {
        observatory_auth_token: 'cookie-token',
      },
    })

    expect(bardoProxyHeaders(request)).toEqual({
      Accept: 'application/json',
      Authorization: 'Bearer authz-token',
      'X-Auth-Secret': 'secret-token',
      'X-Auth-Token': 'header-token',
      'X-User-Email': 'user@softmax.com',
      'X-User-Id': 'user-id',
      'X-User-Is-Softmax-Team-Member': 'true',
    })
  })

  it('falls back to observatory auth cookie token when no auth token header exists', () => {
    const request = fakeRequest({
      cookies: {
        observatory_auth_token: 'cookie-token',
      },
    })

    expect(bardoProxyHeaders(request)).toEqual({
      Accept: 'application/json',
      'X-Auth-Token': 'cookie-token',
    })
  })

  it('supports custom auth cookie name via OBSERVATORY_AUTH_COOKIE_NAME', () => {
    process.env.OBSERVATORY_AUTH_COOKIE_NAME = 'custom_observatory_token'
    const request = fakeRequest({
      cookies: {
        custom_observatory_token: 'custom-token',
      },
    })

    expect(bardoProxyHeaders(request)).toEqual({
      Accept: 'application/json',
      'X-Auth-Token': 'custom-token',
    })
  })

  it('falls back to NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME when OBSERVATORY_AUTH_COOKIE_NAME is unset', () => {
    delete process.env.OBSERVATORY_AUTH_COOKIE_NAME
    process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME = 'next_public_cookie_name'
    const request = fakeRequest({
      cookies: {
        next_public_cookie_name: 'next-public-token',
      },
    })

    expect(bardoProxyHeaders(request)).toEqual({
      Accept: 'application/json',
      'X-Auth-Token': 'next-public-token',
    })
  })

  it('prefers OBSERVATORY_AUTH_COOKIE_NAME over NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME when both are set', () => {
    process.env.OBSERVATORY_AUTH_COOKIE_NAME = 'private_cookie_name'
    process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME = 'public_cookie_name'
    const request = fakeRequest({
      cookies: {
        private_cookie_name: 'private-token',
        public_cookie_name: 'public-token',
      },
    })

    expect(bardoProxyHeaders(request)).toEqual({
      Accept: 'application/json',
      'X-Auth-Token': 'private-token',
    })
  })
})

describe('GET /api/world-state', () => {
  it('forwards conditional etag headers and preserves upstream etag on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ generatedAt: '2026-03-07T18:36:00Z', policies: [], activeJobs: [], seasons: [] }), {
        status: 200,
        headers: { ETag: 'W/"world-etag"' },
      })
    )
    vi.stubGlobal('fetch', fetchMock)

    const response = await GET(
      fakeRouteRequest({
        query: 'q=alpha',
        headers: {
          'if-none-match': 'W/"client-etag"',
          'x-auth-token': 'header-token',
        },
      }) as never
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [upstreamUrl, requestInit] = fetchMock.mock.calls[0] as [URL, RequestInit]
    expect(String(upstreamUrl)).toBe('http://127.0.0.1:8010/bardo/v1/world-state?q=alpha')
    expect((requestInit.headers as Record<string, string>)['If-None-Match']).toBe('W/"client-etag"')
    expect((requestInit.headers as Record<string, string>)['X-Auth-Token']).toBe('header-token')

    expect(response.status).toBe(200)
    expect(response.headers.get('etag')).toBe('W/"world-etag"')
    expect(response.headers.get('cache-control')).toBe('private, no-cache')
  })

  it('returns 304 without a response body when upstream returns 304', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 304, headers: { ETag: 'W/"world-etag"' } }))
    vi.stubGlobal('fetch', fetchMock)

    const response = await GET(
      fakeRouteRequest({
        headers: {
          'if-none-match': 'W/"world-etag"',
        },
      }) as never
    )

    expect(response.status).toBe(304)
    expect(await response.text()).toBe('')
    expect(response.headers.get('etag')).toBe('W/"world-etag"')
    expect(response.headers.get('cache-control')).toBe('private, no-cache')
  })
})
