import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchDashboardData, fetchDashboardDefaultData } from './api'
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
})

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
    expect(String(fetchMock.mock.calls[0][0])).toContain('/dashboard/v1/policies/versions/default/data')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/dashboard/v1/policies/versions/default')
    expect(String(fetchMock.mock.calls[2][0])).toContain(
      `/dashboard/v1/policies/versions/${encodeURIComponent(DASHBOARD_RESPONSE.policy.id)}/data`
    )
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
})
