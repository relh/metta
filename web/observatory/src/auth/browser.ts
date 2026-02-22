'use client'

import { AUTH_COOKIE_NAME } from './constants'

function isLocalHost(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1'
}

function readAuthCookieToken(): string | null {
  const tokenCookie = document.cookie.split('; ').find((cookie) => cookie.startsWith(`${AUTH_COOKIE_NAME}=`))
  if (!tokenCookie) return null
  const token = tokenCookie.slice(AUTH_COOKIE_NAME.length + 1).trim()
  return token || null
}

export function writeAuthCookieToken(token: string): void {
  const baseCookie = `${AUTH_COOKIE_NAME}=${token}; path=/; SameSite=Lax`
  document.cookie = baseCookie

  const host = window.location.hostname.toLowerCase()
  if (!isLocalHost(host)) {
    document.cookie = `${baseCookie}; domain=.softmax-research.net; Secure`
  }
}

export function syncAuthCookieToSharedDomain(): void {
  const host = window.location.hostname.toLowerCase()
  if (isLocalHost(host)) return
  const token = readAuthCookieToken()
  if (!token) return
  document.cookie = `${AUTH_COOKIE_NAME}=${token}; path=/; domain=.softmax-research.net; SameSite=Lax; Secure`
}

export function clearAuthCookies(): void {
  document.cookie = `${AUTH_COOKIE_NAME}=; path=/; max-age=0`
  document.cookie = `${AUTH_COOKIE_NAME}=; path=/; domain=.softmax-research.net; max-age=0`
}
