import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  fetchDashboardAnalysis,
  fetchDashboardData,
  fetchDashboardDefaultData,
  fetchPantheonStories,
  uploadDiagnoseBundle,
} from './api'
import type { DashboardResponse } from './api'

const DASHBOARD_RESPONSE: DashboardResponse = {
  policy: {
    id: '7e16ac5f-7fe6-4970-940c-acc2d6c29013',
    name: 'glanky',
    version: 11,
  },
  episodes: [],
  season: 'beta-cvc',
  generated_at: '2026-02-24T10:30:00Z',
  derived: {
    kpis: {},
    failures: {},
    opponent_metrics: {},
  },
  selection: {
    sampled_episode_count: 0,
  },
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  window.sessionStorage.clear()
  document.cookie = 'observatory_auth_token=; path=/; max-age=0'
  window.history.replaceState({}, '', '/')
})

function mockDashboardFetch() {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(DASHBOARD_RESPONSE)))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function readAuthHeader(fetchMock: ReturnType<typeof vi.fn>): string | undefined {
  const requestInit = fetchMock.mock.calls[0]?.[1] as RequestInit
  const headers = requestInit.headers as Record<string, string>
  return headers['X-Auth-Token']
}

describe('dashboard api', () => {
  it('falls back from /default/data to /default + /{id}/data during rolling deploy mismatch', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Invalid policy version id format' }), { status: 422 })
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ policy_version_id: DASHBOARD_RESPONSE.policy.id })))
      .mockResolvedValueOnce(new Response(JSON.stringify(DASHBOARD_RESPONSE)))
    vi.stubGlobal('fetch', fetchMock)

    const response = await fetchDashboardDefaultData()

    expect(response.policy.id).toBe(DASHBOARD_RESPONSE.policy.id)
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/policy-dashboard/v1/policies/versions/default/data')
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('include=')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/policy-dashboard/v1/policies/versions/default')
    expect(String(fetchMock.mock.calls[2][0])).toContain(
      `/policy-dashboard/v1/policies/versions/${encodeURIComponent(DASHBOARD_RESPONSE.policy.id)}/data`
    )
    expect(String(fetchMock.mock.calls[2][0])).not.toContain('include=')
  })

  it('retries GET once on transient 503 before failing', async () => {
    vi.useFakeTimers()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ detail: 'Service temporarily unavailable' }), { status: 503 })
      )
      .mockResolvedValueOnce(new Response(JSON.stringify(DASHBOARD_RESPONSE)))
    vi.stubGlobal('fetch', fetchMock)

    const pending = fetchDashboardData(DASHBOARD_RESPONSE.policy.id)
    await vi.advanceTimersByTimeAsync(351)
    const response = await pending

    expect(response.policy.id).toBe(DASHBOARD_RESPONSE.policy.id)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('surfaces the friendly 503 error even when the backend returns html', async () => {
    vi.useFakeTimers()
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('<html>temporarily unavailable</html>', { status: 503 }))
      .mockResolvedValueOnce(new Response('<html>temporarily unavailable</html>', { status: 503 }))
    vi.stubGlobal('fetch', fetchMock)

    const pending = fetchDashboardData(DASHBOARD_RESPONSE.policy.id)
    void pending.catch(() => undefined)
    await vi.advanceTimersByTimeAsync(351)

    await expect(pending).rejects.toThrow('503: Service temporarily unavailable - please try again.')
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('preserves json parse failures on successful responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('<html>ok but not json</html>'))
    vi.stubGlobal('fetch', fetchMock)

    await expect(fetchDashboardData(DASHBOARD_RESPONSE.policy.id)).rejects.toBeInstanceOf(SyntaxError)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('fetches the main dashboard summary without eager role or diagnose embeds', async () => {
    const fetchMock = mockDashboardFetch()

    await fetchDashboardData(DASHBOARD_RESPONSE.policy.id)

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      `/policy-dashboard/v1/policies/versions/${encodeURIComponent(DASHBOARD_RESPONSE.policy.id)}/data`
    )
    expect(String(fetchMock.mock.calls[0][0])).not.toContain('include=')
  })

  it('prefers URL hash token over cookie, stores it in sessionStorage, and scrubs it from the URL', async () => {
    const fetchMock = mockDashboardFetch()
    document.cookie = 'observatory_auth_token=cookie-token'
    window.history.replaceState({}, '', '/?policyVersionId=test-policy#hash-token')

    await fetchDashboardData(DASHBOARD_RESPONSE.policy.id)

    expect(readAuthHeader(fetchMock)).toBe('hash-token')
    expect(window.sessionStorage.getItem('policy-dashboard-auth-token')).toBe('hash-token')
    expect(new URL(window.location.href).hash).toBe('')
  })

  it('ignores query-string authToken and falls back to cookie', async () => {
    const fetchMock = mockDashboardFetch()
    document.cookie = 'observatory_auth_token=cookie-token'
    window.history.replaceState({}, '', '/?policyVersionId=test-policy&authToken=query-token')

    await fetchDashboardData(DASHBOARD_RESPONSE.policy.id)

    expect(readAuthHeader(fetchMock)).toBe('cookie-token')
  })

  it('uses sessionStorage auth token when URL fragment is gone', async () => {
    const fetchMock = mockDashboardFetch()
    window.sessionStorage.setItem('policy-dashboard-auth-token', 'session-token')
    document.cookie = 'observatory_auth_token=cookie-token'
    window.history.replaceState({}, '', '/?policyVersionId=test-policy')

    await fetchDashboardData(DASHBOARD_RESPONSE.policy.id)

    expect(readAuthHeader(fetchMock)).toBe('session-token')
  })

  it('overrides stored session token when a fresh hash token appears', async () => {
    const fetchMock = mockDashboardFetch()
    window.sessionStorage.setItem('policy-dashboard-auth-token', 'old-session-token')
    window.history.replaceState({}, '', '/?policyVersionId=test-policy#fresh-hash-token')

    await fetchDashboardData(DASHBOARD_RESPONSE.policy.id)

    expect(readAuthHeader(fetchMock)).toBe('fresh-hash-token')
    expect(window.sessionStorage.getItem('policy-dashboard-auth-token')).toBe('fresh-hash-token')
  })

  it('fetches pantheon stories from the pantheon service route', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          generated_at: '2026-03-05T00:00:00Z',
          stories: [],
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    const response = await fetchPantheonStories()

    expect(response.stories).toEqual([])
    expect(String(fetchMock.mock.calls[0][0])).toContain('/pantheon/v1/stories')
  })

  it('posts dashboard analysis with a trimmed anthropic header', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ analysis: 'looks good', data_sources: ['dashboard'] })))
    vi.stubGlobal('fetch', fetchMock)

    const response = await fetchDashboardAnalysis(DASHBOARD_RESPONSE.policy.id, '  test-key  ')

    expect(response.analysis).toBe('looks good')
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      `/policy-dashboard/v1/policies/versions/${encodeURIComponent(DASHBOARD_RESPONSE.policy.id)}/analysis`
    )
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit
    const headers = requestInit.headers as Record<string, string>
    expect(requestInit.method).toBe('POST')
    expect(requestInit.body).toBe('{}')
    expect(headers['X-Anthropic-Api-Key']).toBe('test-key')
  })

  it('uploads diagnose bundles as multipart without forcing json content-type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ run_id: 'run-1', manifest: null })))
    vi.stubGlobal('fetch', fetchMock)

    await uploadDiagnoseBundle(new File(['zip-data'], 'bundle.zip', { type: 'application/zip' }))

    expect(String(fetchMock.mock.calls[0][0])).toContain('/diagnose/v1/runs/upload')
    const requestInit = fetchMock.mock.calls[0][1] as RequestInit
    const headers = requestInit.headers as Record<string, string>
    expect(requestInit.method).toBe('POST')
    expect(requestInit.body).toBeInstanceOf(FormData)
    expect(headers['Content-Type']).toBeUndefined()
  })
})
