import { cleanup, render, screen, waitFor } from '@testing-library/react'
import type { ComponentType } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { DashboardResponse, DashboardRolePercentilesResponse } from '../lib/api'

const DASHBOARD_CACHE_STORAGE_KEY = 'policy-dashboard-response-cache:v1'
const ROLE_PERCENTILES_CACHE_STORAGE_KEY = 'policy-dashboard-role-percentiles-cache:v1'

const DASHBOARD_API_BASE_URL = 'https://api.policy-dashboard.softmax-research.net'

type DashboardClientApiMocks = {
  fetchDashboardData: ReturnType<typeof vi.fn>
  fetchDashboardDefaultData: ReturnType<typeof vi.fn>
  fetchDashboardAnalysis: ReturnType<typeof vi.fn>
  fetchDashboardRolePercentiles: ReturnType<typeof vi.fn>
  fetchDiagnoseRuns: ReturnType<typeof vi.fn>
  fetchDiagnoseManifest: ReturnType<typeof vi.fn>
  fetchDiagnoseDoctorNote: ReturnType<typeof vi.fn>
  fetchPantheonStories: ReturnType<typeof vi.fn>
}

async function loadDashboardClientWithMocks(): Promise<{
  DashboardClient: ComponentType
  mocks: DashboardClientApiMocks
}> {
  vi.resetModules()

  const mocks: DashboardClientApiMocks = {
    fetchDashboardData: vi.fn(),
    fetchDashboardDefaultData: vi.fn(),
    fetchDashboardAnalysis: vi.fn(),
    fetchDashboardRolePercentiles: vi.fn(),
    fetchDiagnoseRuns: vi.fn(),
    fetchDiagnoseManifest: vi.fn(),
    fetchDiagnoseDoctorNote: vi.fn(),
    fetchPantheonStories: vi.fn(),
  }

  vi.doMock('../lib/api', () => ({
    DASHBOARD_API_BASE_URL,
    ...mocks,
  }))

  const { DashboardClient } = await import('./DashboardClient')
  return { DashboardClient, mocks }
}

function buildDashboardResponse(
  policyVersionId: string,
  policyName: string,
  generatedAt = '2026-02-24T10:35:00Z'
): DashboardResponse {
  return {
    policy: { id: policyVersionId, name: policyName, version: 2, rank: 1, score: 1.5, matches: 12 },
    episodes: [],
    season: 'beta-cvc',
    generated_at: generatedAt,
    derived: {
      kpis: {},
      failures: {},
      opponent_metrics: {},
    },
    selection: {
      sampled_episode_count: 0,
    },
  }
}

function buildPercentilesResponse(): DashboardRolePercentilesResponse {
  return {
    pool_id: 'pool-1',
    pool_name: 'default',
    roles: {},
    rows: [],
  }
}

function createStorageMock(): Storage {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    clear() {
      map.clear()
    },
    getItem(key: string) {
      return map.has(key) ? map.get(key)! : null
    },
    key(index: number) {
      return [...map.keys()][index] ?? null
    },
    removeItem(key: string) {
      map.delete(key)
    },
    setItem(key: string, value: string) {
      map.set(key, value)
    },
  }
}

beforeEach(() => {
  const storage = createStorageMock()
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    value: storage,
  })
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: storage,
  })
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  window.history.replaceState({}, '', '/')
  vi.unmock('../lib/api')
  vi.resetModules()
  vi.clearAllMocks()
})

describe('DashboardClient cache persistence', () => {
  it('persists dashboard + parses caches to localStorage after a successful load', async () => {
    const response = buildDashboardResponse('policy-cache-write', 'cache-write-policy')
    const percentiles = buildPercentilesResponse()
    const { DashboardClient, mocks } = await loadDashboardClientWithMocks()

    mocks.fetchDashboardData.mockResolvedValueOnce(response)
    mocks.fetchDashboardRolePercentiles.mockResolvedValueOnce(percentiles)
    mocks.fetchDiagnoseRuns.mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-cache-write')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(mocks.fetchDashboardData).toHaveBeenCalledWith('policy-cache-write')
    })
    await waitFor(() => {
      expect(mocks.fetchDashboardRolePercentiles).toHaveBeenCalledWith('policy-cache-write')
    })

    const rawDashboardCache = window.localStorage.getItem(DASHBOARD_CACHE_STORAGE_KEY)
    const rawRoleCache = window.localStorage.getItem(ROLE_PERCENTILES_CACHE_STORAGE_KEY)
    expect(rawDashboardCache).toBeTruthy()
    expect(rawRoleCache).toBeTruthy()

    const parsedDashboardCache = JSON.parse(String(rawDashboardCache)) as {
      entries: Array<{ policyVersionId: string }>
    }
    const parsedRoleCache = JSON.parse(String(rawRoleCache)) as {
      entries: Array<{ cacheKey: string }>
    }

    expect(parsedDashboardCache.entries.some((entry) => entry.policyVersionId === 'policy-cache-write')).toBe(true)
    expect(parsedRoleCache.entries.some((entry) => entry.cacheKey.startsWith('policy-cache-write:'))).toBe(true)
  })

  it('hydrates from valid persisted cache and skips network fetches for dashboard/parses', async () => {
    const cachedResponse = buildDashboardResponse('policy-cache-hit', 'cached-policy')
    const savedAtMs = Date.now()
    window.localStorage.setItem(
      DASHBOARD_CACHE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        apiBaseUrl: DASHBOARD_API_BASE_URL,
        savedAtMs,
        entries: [{ policyVersionId: 'policy-cache-hit', response: cachedResponse }],
      })
    )
    window.localStorage.setItem(
      ROLE_PERCENTILES_CACHE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        apiBaseUrl: DASHBOARD_API_BASE_URL,
        savedAtMs,
        entries: [
          { cacheKey: `policy-cache-hit:${cachedResponse.generated_at}`, response: buildPercentilesResponse() },
        ],
      })
    )

    const { DashboardClient, mocks } = await loadDashboardClientWithMocks()
    mocks.fetchDiagnoseRuns.mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-cache-hit')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    })
    expect(mocks.fetchDashboardData).not.toHaveBeenCalled()
    expect(mocks.fetchDashboardRolePercentiles).not.toHaveBeenCalled()
  })

  it('ignores expired persisted cache entries and refetches dashboard data', async () => {
    const expiredCachedResponse = buildDashboardResponse('policy-cache-expired', 'stale-policy')
    const liveResponse = buildDashboardResponse('policy-cache-expired', 'live-policy')
    window.localStorage.setItem(
      DASHBOARD_CACHE_STORAGE_KEY,
      JSON.stringify({
        version: 1,
        apiBaseUrl: DASHBOARD_API_BASE_URL,
        savedAtMs: Date.now() - 31 * 60 * 1000,
        entries: [{ policyVersionId: 'policy-cache-expired', response: expiredCachedResponse }],
      })
    )

    const { DashboardClient, mocks } = await loadDashboardClientWithMocks()
    mocks.fetchDashboardData.mockResolvedValueOnce(liveResponse)
    mocks.fetchDashboardRolePercentiles.mockResolvedValueOnce(buildPercentilesResponse())
    mocks.fetchDiagnoseRuns.mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-cache-expired')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(mocks.fetchDashboardData).toHaveBeenCalledWith('policy-cache-expired')
    })
    expect(await screen.findByText('live-policy')).toBeTruthy()
  })
})
