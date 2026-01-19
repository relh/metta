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

  const token = appConfig.authToken ?? request.cookies.get(AUTH_COOKIE_NAME)

  if (!token) {
    const authUrl = new URL(`${appConfig.authServerUrl}/tokens/cli`)
    authUrl.searchParams.set('callback', `${request.nextUrl.origin}/auth/callback`)
    return NextResponse.redirect(authUrl)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\..*).*)'],
}
