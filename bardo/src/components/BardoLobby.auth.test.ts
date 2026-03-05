import { afterEach, describe, expect, it } from 'vitest'

import { resolveBardoAuthToken } from './BardoLobby'

afterEach(() => {
  window.sessionStorage.clear()
  document.cookie = 'observatory_auth_token=; path=/; max-age=0'
  window.history.replaceState({}, '', '/')
})

describe('resolveBardoAuthToken', () => {
  it('prefers URL hash token over cookie token, stores it, and scrubs it from URL', () => {
    document.cookie = 'observatory_auth_token=cookie-token'
    window.history.replaceState({}, '', '/bardo?q=alpha#hash-token')

    expect(resolveBardoAuthToken()).toBe('hash-token')
    expect(window.sessionStorage.getItem('bardo-auth-token')).toBe('hash-token')
    expect(new URL(window.location.href).hash).toBe('')
  })

  it('prefers sessionStorage token over cookie token when URL fragment is absent', () => {
    window.sessionStorage.setItem('bardo-auth-token', 'session-token')
    document.cookie = 'observatory_auth_token=cookie-token'
    window.history.replaceState({}, '', '/bardo')

    expect(resolveBardoAuthToken()).toBe('session-token')
  })

  it('uses sessionStorage token when URL fragment and cookie are absent', () => {
    window.sessionStorage.setItem('bardo-auth-token', 'session-token')

    expect(resolveBardoAuthToken()).toBe('session-token')
  })

  it('overrides stored session token when a fresh hash token appears', () => {
    window.sessionStorage.setItem('bardo-auth-token', 'old-session-token')
    window.history.replaceState({}, '', '/bardo#fresh-token')

    expect(resolveBardoAuthToken()).toBe('fresh-token')
    expect(window.sessionStorage.getItem('bardo-auth-token')).toBe('fresh-token')
  })

  it('falls back to observatory auth cookie when no fragment or session token exists', () => {
    document.cookie = 'observatory_auth_token=cookie-token'

    expect(resolveBardoAuthToken()).toBe('cookie-token')
  })
})
