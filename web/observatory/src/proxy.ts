import type { NextRequest } from 'next/server'
import { NextResponse } from 'next/server'

import { AUTH_COOKIE_NAME } from './auth/constants'
import { config as appConfig } from './config'

const PUBLIC_PATHS = ['/auth/callback']

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl

  if (PUBLIC_PATHS.some((p) => pathname.startsWith(p))) {
    return NextResponse.next()
  }

  const isTraceRequest =
    pathname.startsWith('/api/jobs/') && (pathname.endsWith('/trace') || pathname.endsWith('/setup-trace'))
  const cookieToken = request.cookies.get(AUTH_COOKIE_NAME)?.value
  const queryToken = isTraceRequest ? request.nextUrl.searchParams.get('auth_token') : null
  // TODO: Replace auth_token query fallback with short-lived signed trace tokens.
  // Perfetto loads from ui.perfetto.dev and can't send localhost cookies.
  const token = appConfig.authToken ?? cookieToken ?? queryToken

  if (!token) {
    const authUrl = new URL(`${appConfig.authServerUrl}/tokens/cli`)
    const queryParams = new URLSearchParams()
    queryParams.set('observatory_url', pathname + request.nextUrl.search)
    authUrl.searchParams.set('callback', `${appConfig.siteUrl}/auth/callback?${queryParams.toString()}`)
    return NextResponse.redirect(authUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
