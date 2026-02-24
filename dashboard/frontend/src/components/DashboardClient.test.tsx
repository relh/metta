import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardClient } from './DashboardClient'
import * as api from '../lib/api'
import type { DashboardResponse } from '../lib/api'

vi.mock('../lib/api', () => ({
  DASHBOARD_API_BASE_URL: 'https://api.policy-dashboard.softmax-research.net',
  fetchDashboardData: vi.fn(),
  fetchDashboardDefaultData: vi.fn(),
  fetchDashboardAnalysis: vi.fn(),
  fetchDashboardRolePercentiles: vi.fn(),
  fetchDiagnoseRuns: vi.fn(),
  fetchDiagnoseManifest: vi.fn(),
  fetchDiagnoseDoctorNote: vi.fn(),
}))

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((resolveValue, rejectValue) => {
    resolve = resolveValue
    reject = rejectValue
  })
  return { promise, resolve, reject }
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
  window.history.replaceState({}, '', '/')
})

describe('DashboardClient', () => {
  it('shows a progress bar while dashboard data is loading', async () => {
    const response: DashboardResponse = {
      policy: { id: 'test-policy-id', name: 'glanky', version: 1, rank: 1, score: 1.0, matches: 1 },
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

    const pending = deferred<DashboardResponse>()
    vi.mocked(api.fetchDashboardData).mockReturnValueOnce(pending.promise)
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=test-policy-id')
    render(<DashboardClient />)

    expect(await screen.findByText(/Generating dashboard summary\./)).toBeTruthy()
    expect(screen.getByRole('progressbar')).toBeTruthy()

    pending.resolve(response)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })
  })
})
