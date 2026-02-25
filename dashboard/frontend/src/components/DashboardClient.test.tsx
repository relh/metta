import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardClient } from './DashboardClient'
import * as api from '../lib/api'
import type { DashboardResponse, DashboardRolePercentilesResponse } from '../lib/api'

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
  it('toggles replay theater mode with the "t" shortcut', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-theater', name: 'glanky', version: 3, rank: 1, score: 2.1, matches: 8 },
      episodes: [
        {
          episode_id: 'episode-1',
          status: 'completed',
          reward: 1.2,
          opponent_name: 'opponent-a',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 123,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-02-25T08:00:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 1,
      },
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-theater')
    render(<DashboardClient />)

    const replayShell = await screen.findByTestId('replay-spotlight-shell')
    fireEvent.load(screen.getByTitle('Replay spotlight'))
    expect(replayShell.getAttribute('data-theater-mode')).toBe('off')

    fireEvent.keyDown(window, { key: 't' })
    expect(replayShell.getAttribute('data-theater-mode')).toBe('on')

    fireEvent.keyDown(window, { key: 't' })
    expect(replayShell.getAttribute('data-theater-mode')).toBe('off')
  })

  it('triggers replay fullscreen with the "f" shortcut and ignores typing contexts', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-fullscreen', name: 'glanky', version: 4, rank: 1, score: 2.4, matches: 9 },
      episodes: [
        {
          episode_id: 'episode-2',
          status: 'completed',
          reward: 1.3,
          opponent_name: 'opponent-b',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 240,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-02-25T08:15:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 1,
      },
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-fullscreen')
    render(<DashboardClient />)

    const replayShell = await screen.findByTestId('replay-spotlight-shell')
    fireEvent.load(screen.getByTitle('Replay spotlight'))
    const requestFullscreenSpy = vi.fn()
    Object.defineProperty(replayShell, 'requestFullscreen', {
      configurable: true,
      value: requestFullscreenSpy,
    })

    fireEvent.keyDown(window, { key: 'f' })
    expect(requestFullscreenSpy).toHaveBeenCalledTimes(1)

    const input = screen.getByLabelText('Policy version id:')
    fireEvent.keyDown(input, { key: 'f' })
    expect(requestFullscreenSpy).toHaveBeenCalledTimes(1)
  })

  it('does not block dashboard loading progress on replay spotlight iframe load', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-replay-load', name: 'glanky', version: 5, rank: 1, score: 2.5, matches: 10 },
      episodes: [
        {
          episode_id: 'episode-replay-load',
          status: 'completed',
          reward: 1.4,
          opponent_name: 'opponent-c',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 260,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-02-25T09:00:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 1,
      },
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-replay-load')
    render(<DashboardClient />)

    expect(await screen.findByRole('progressbar')).toBeTruthy()
    await screen.findByTestId('replay-spotlight-shell')

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })

    expect(screen.getByTestId('replay-spotlight-loading')).toBeTruthy()
    fireEvent.load(screen.getByTitle('Replay spotlight'))
    await waitFor(() => {
      expect(screen.queryByTestId('replay-spotlight-loading')).toBeNull()
    })
  })

  it('prefetches diagnose runs in parallel with dashboard fetch', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-prefetch', name: 'glanky', version: 6, rank: 1, score: 2.6, matches: 11 },
      episodes: [],
      season: 'beta-cvc',
      generated_at: '2026-02-25T09:15:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 0,
      },
    }

    const pendingDashboard = deferred<DashboardResponse>()
    const pendingDiagnoseRuns = deferred<{ runs: api.DiagnoseRunSummary[] }>()
    vi.mocked(api.fetchDashboardData).mockReturnValueOnce(pendingDashboard.promise)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockReturnValueOnce(pendingDiagnoseRuns.promise)

    window.history.replaceState({}, '', '/?policyVersionId=policy-prefetch')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(api.fetchDashboardData).toHaveBeenCalledWith('policy-prefetch')
    })
    expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(1)

    pendingDashboard.resolve(response)
    pendingDiagnoseRuns.resolve({ runs: [] })

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })
    expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(1)
  })

  it('does not block dashboard render on parses preload', async () => {
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
    const pendingPercentiles = deferred<DashboardRolePercentilesResponse>()
    const percentiles: DashboardRolePercentilesResponse = {
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    }
    vi.mocked(api.fetchDashboardData).mockReturnValueOnce(pending.promise)
    vi.mocked(api.fetchDashboardRolePercentiles).mockReturnValueOnce(pendingPercentiles.promise)
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=test-policy-id')
    render(<DashboardClient />)

    expect(await screen.findByText(/Generating dashboard summary\./)).toBeTruthy()
    expect(screen.getByRole('progressbar')).toBeTruthy()

    pending.resolve(response)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })
    expect(screen.getByRole('button', { name: 'Overview' })).toBeTruthy()
    expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledWith('test-policy-id')

    pendingPercentiles.resolve(percentiles)
  })

  it('preloads parses data after loading the default dashboard policy', async () => {
    const response: DashboardResponse = {
      policy: { id: 'default-top-policy-uuid', name: 'glanky', version: 2, rank: 1, score: 1.5, matches: 12 },
      episodes: [],
      season: 'beta-cvc',
      generated_at: '2026-02-24T10:35:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 0,
      },
    }

    const percentiles: DashboardRolePercentilesResponse = {
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    }

    vi.mocked(api.fetchDashboardDefaultData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce(percentiles)
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    render(<DashboardClient />)

    await waitFor(() => {
      expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledWith('default-top-policy-uuid')
    })
  })

  it('does not refetch parses percentiles when switching non-parses tabs', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-123', name: 'glanky', version: 2, rank: 1, score: 1.5, matches: 12 },
      episodes: [],
      season: 'beta-cvc',
      generated_at: '2026-02-24T10:35:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 0,
      },
    }

    const percentiles: DashboardRolePercentilesResponse = {
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce(percentiles)
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-123')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Capabilities' }))
    fireEvent.click(screen.getByRole('button', { name: 'Episodes' }))
    fireEvent.click(screen.getByRole('button', { name: 'Health' }))

    expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledTimes(1)
  })
})
