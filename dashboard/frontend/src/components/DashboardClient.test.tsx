import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardClient, percentileRank } from './DashboardClient'
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
  it('percentileRank ignores non-finite samples in denominator', () => {
    expect(percentileRank(10, [Number.NaN, 5, 10])).toBe(100)
    expect(percentileRank(10, [Number.NaN, Number.POSITIVE_INFINITY])).toBeNull()
  })

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

  it('loads diagnose runs after dashboard data resolves when not embedded', async () => {
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
    expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(0)

    pendingDashboard.resolve(response)
    pendingDiagnoseRuns.resolve({ runs: [] })

    await waitFor(() => {
      expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })
    expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(1)
  })

  it('skips diagnose run fetch when dashboard payload embeds diagnose runs', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-embedded-diagnose', name: 'glanky', version: 7, rank: 1, score: 2.7, matches: 12 },
      episodes: [],
      season: 'beta-cvc',
      generated_at: '2026-02-25T09:20:00Z',
      derived: {
        kpis: {},
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 0,
      },
      diagnose_runs: [
        {
          run_id: 'embedded-run-1',
          manifest: {
            run_id: 'embedded-run-1',
            created_at: '2026-02-25T09:19:59Z',
            command: 'uv run cogames diagnose',
            policy: 'glanky:v7',
            pack_id: 'cogsguard',
            pack_version: 'v1',
            stage_status: 'stage1_complete',
            run_status: 'completed',
            artifact_files: [],
            diagnose_validity: { valid: true, failed_check_ids: [], checks: [] },
            interpretation_stability: { stable: true, snapshot_count: 1, notes: [] },
          },
        },
      ],
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-1',
      pool_name: 'default',
      roles: {},
      rows: [],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-embedded-diagnose')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })
    expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(0)
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

  it('renders the simplified overview pills with merged data-quality status', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-pill-cleanup', name: 'glanky', version: 8, rank: 4, score: 1.7, matches: 22 },
      episodes: [
        {
          episode_id: 'episode-pill-cleanup-1',
          status: 'completed',
          reward: 0.9,
          opponent_name: 'opponent-z',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 180,
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-03-01T09:20:00Z',
      derived: {
        kpis: {
          avg_reward: 1.24,
          move_efficiency: 0.65,
          action_success_rate: 0.73,
          junction_control_rate: 0.83,
          resource_retention: 0,
          freeze_vulnerability: 0,
          noop_rate: 0.033,
          reward_consistency: 0,
        },
        failures: {},
        opponent_metrics: {},
        instrumentation: {
          compliant: false,
          score: 0.7,
          checks: [
            {
              key: 'created_at',
              kind: 'field',
              coverage: 1,
              present_count: 1,
              total_count: 1,
              status: 'pass',
              message: 'ok',
            },
            {
              key: 'replay_url',
              kind: 'field',
              coverage: 0,
              present_count: 0,
              total_count: 1,
              status: 'missing',
              message: 'missing',
            },
          ],
        },
        unsupported: {
          has_unsupported_state: true,
          issues: [
            {
              code: 'missing_replay_urls',
              severity: 'warn',
              message: 'Some completed episodes have no replay URL.',
              affected_count: 1,
              total_count: 1,
              recommended_action: 'Enable replay artifact upload.',
            },
          ],
        },
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

    window.history.replaceState({}, '', '/?policyVersionId=policy-pill-cleanup')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })

    expect(screen.getByText(/^Data Quality$/)).toBeTruthy()
    expect(screen.getByText(/^Action Success$/)).toBeTruthy()
    expect(screen.getByText(/^Avg Reward$/)).toBeTruthy()
    expect(screen.getByText(/^Junction Control$/)).toBeTruthy()
    expect(screen.getByText(/^Noop Rate$/)).toBeTruthy()
    expect(screen.getByText('yellow: between 0.50 and 2.00')).toBeTruthy()
    expect(screen.getByText('sample reward percentile: P100')).toBeTruthy()

    expect(screen.queryByText(/^Move Efficiency$/)).toBeNull()
    expect(screen.queryByText(/^Outcome Verdict$/)).toBeNull()
    expect(screen.queryByText(/^Version Trend$/)).toBeNull()
    expect(screen.queryByText(/^Unsupported Issues$/)).toBeNull()
    expect(screen.queryByText(/^Instrumentation Score$/)).toBeNull()
    expect(screen.queryByText(/^Check Failures$/)).toBeNull()
    expect(screen.queryByText(/^Template$/)).toBeNull()
    expect(screen.queryByText(/^Resource Retention$/)).toBeNull()
    expect(screen.queryByText(/^Freeze Vulnerability$/)).toBeNull()
    expect(screen.queryByText(/^Reward Consistency$/)).toBeNull()
  })

  it('prefers parse-derived reward percentile when available', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-pill-parse-percentile', name: 'glanky', version: 9, rank: 3, score: 2.0, matches: 30 },
      episodes: [
        {
          episode_id: 'episode-pill-parse-percentile-1',
          status: 'completed',
          reward: 1.6,
          opponent_name: 'opponent-y',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 200,
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-03-02T15:30:00Z',
      derived: {
        kpis: {
          avg_reward: 1.6,
          action_success_rate: 0.91,
          junction_control_rate: 0.72,
          noop_rate: 0.02,
        },
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 1,
      },
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-parse',
      pool_name: 'default',
      roles: {},
      rows: [
        {
          role: 'aligner',
          percentile: 80,
          details: {
            metrics: {
              reward: {
                percentile: 88.2,
                avg: 1.6,
                higher_is_better: true,
              },
            },
            overall_percentile: 80,
          },
          updated_at: '2026-03-02T15:30:00Z',
        },
      ],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-pill-parse-percentile')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })

    await waitFor(() => {
      expect(screen.getByText('pool reward percentile: P88 (sample P100)')).toBeTruthy()
    })
  })

  it('marks missing instrumentation as non-clean data quality', async () => {
    const response: DashboardResponse = {
      policy: { id: 'policy-pill-missing-inst', name: 'glanky', version: 10, rank: 3, score: 2.0, matches: 30 },
      episodes: [
        {
          episode_id: 'episode-pill-missing-inst-1',
          status: 'completed',
          reward: 1.6,
          opponent_name: 'opponent-y',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 200,
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-03-02T15:30:00Z',
      derived: {
        kpis: {
          avg_reward: 1.6,
          action_success_rate: 0.91,
          junction_control_rate: 0.72,
          noop_rate: 0.02,
        },
        failures: {},
        opponent_metrics: {},
      },
      selection: {
        sampled_episode_count: 1,
      },
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-missing-inst',
      pool_name: 'default',
      roles: {},
      rows: [],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-pill-missing-inst')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })

    expect(screen.getByText('instrumentation summary missing from payload')).toBeTruthy()
    expect(screen.getByText('0 issues · instrumentation missing')).toBeTruthy()
  })

  it('does not refetch parse percentiles when switching non-coordination tabs', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: 'Performance' }))
    fireEvent.click(screen.getByRole('button', { name: 'Capabilities' }))
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))

    expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledTimes(1)
  })
})
