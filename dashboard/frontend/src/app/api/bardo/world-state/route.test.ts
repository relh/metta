import { afterEach, describe, expect, it } from 'vitest'

import { bardoProxyHeaders } from './route'

const ORIGINAL_AUTH_COOKIE_NAME = process.env.OBSERVATORY_AUTH_COOKIE_NAME

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
  if (ORIGINAL_AUTH_COOKIE_NAME === undefined) {
    delete process.env.OBSERVATORY_AUTH_COOKIE_NAME
    return
  }
  process.env.OBSERVATORY_AUTH_COOKIE_NAME = ORIGINAL_AUTH_COOKIE_NAME
})

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
})
