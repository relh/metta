import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { DashboardClient, percentileRank } from './DashboardClient'
import * as api from '../lib/api'
import type { DashboardEpisode, DashboardResponse, DashboardRolePercentilesResponse } from '../lib/api'

vi.mock('../lib/api', () => ({
  DASHBOARD_API_BASE_URL: 'https://api.policy-dashboard.softmax-research.net',
  fetchDashboardData: vi.fn(),
  fetchDashboardDefaultData: vi.fn(),
  fetchDashboardAnalysis: vi.fn(),
  fetchDashboardRolePercentiles: vi.fn(),
  fetchDiagnoseRuns: vi.fn(),
  fetchDiagnoseManifest: vi.fn(),
  fetchDiagnoseDoctorNote: vi.fn(),
  fetchPantheonStories: vi.fn(),
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

const EMPTY_DERIVED = {
  kpis: {},
  failures: {},
  opponent_metrics: {},
} satisfies DashboardResponse['derived']

const EMPTY_PERCENTILES = {
  pool_id: 'pool-1',
  pool_name: 'default',
  roles: {},
  rows: [],
} satisfies DashboardRolePercentilesResponse

const EMPTY_DIAGNOSE_RUNS = { runs: [] } satisfies { runs: api.DiagnoseRunSummary[] }

function buildEpisode(overrides: Partial<DashboardEpisode> = {}): DashboardEpisode {
  return {
    episode_id: 'episode-1',
    status: 'completed',
    reward: 1,
    opponent_name: 'opponent',
    team_composition: 'miner,aligner,scout,scrambler',
    diagnostic_tags: [],
    steps: 100,
    ...overrides,
  }
}

function buildDashboardResponse({
  policyVersionId,
  generatedAt = '2026-02-24T10:30:00Z',
  policy = {},
  episodes = [],
  derived = {},
  selection = {},
  diagnoseRuns,
}: {
  policyVersionId: string
  generatedAt?: string
  policy?: Partial<DashboardResponse['policy']>
  episodes?: DashboardEpisode[]
  derived?: Partial<DashboardResponse['derived']>
  selection?: Partial<DashboardResponse['selection']>
  diagnoseRuns?: DashboardResponse['diagnose_runs']
}): DashboardResponse {
  const { kpis = {}, failures = {}, opponent_metrics = {}, ...restDerived } = derived

  return {
    policy: {
      id: policyVersionId,
      name: 'glanky',
      version: 1,
      rank: 1,
      score: 1,
      matches: 1,
      ...policy,
    },
    season: 'beta-cvc',
    generated_at: generatedAt,
    episodes,
    derived: {
      ...EMPTY_DERIVED,
      ...restDerived,
      kpis: { ...EMPTY_DERIVED.kpis, ...kpis },
      failures: { ...EMPTY_DERIVED.failures, ...failures },
      opponent_metrics: { ...EMPTY_DERIVED.opponent_metrics, ...opponent_metrics },
    },
    selection: {
      sampled_episode_count: episodes.length,
      ...selection,
    },
    ...(diagnoseRuns === undefined ? {} : { diagnose_runs: diagnoseRuns }),
  }
}

function mockDashboardLoad(
  response: DashboardResponse,
  {
    path = `/?policyVersionId=${response.policy.id}`,
    percentiles = EMPTY_PERCENTILES,
    diagnoseRuns = EMPTY_DIAGNOSE_RUNS,
  }: {
    path?: string
    percentiles?: DashboardRolePercentilesResponse
    diagnoseRuns?: { runs: api.DiagnoseRunSummary[] }
  } = {}
): void {
  vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
  vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce(percentiles)
  vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue(diagnoseRuns)
  window.history.replaceState({}, '', path)
}

async function waitForDashboardLoad(): Promise<void> {
  await waitFor(() => {
    expect(screen.queryByRole('progressbar')).toBeNull()
  })
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
    const response = buildDashboardResponse({
      policyVersionId: 'policy-theater',
      generatedAt: '2026-02-25T08:00:00Z',
      policy: { version: 3, score: 2.1, matches: 8 },
      episodes: [
        buildEpisode({
          reward: 1.2,
          opponent_name: 'opponent-a',
          steps: 123,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        }),
      ],
    })

    mockDashboardLoad(response)
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
    const response = buildDashboardResponse({
      policyVersionId: 'policy-fullscreen',
      generatedAt: '2026-02-25T08:15:00Z',
      policy: { version: 4, score: 2.4, matches: 9 },
      episodes: [
        buildEpisode({
          episode_id: 'episode-2',
          reward: 1.3,
          opponent_name: 'opponent-b',
          steps: 240,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        }),
      ],
    })

    mockDashboardLoad(response)
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
    const response = buildDashboardResponse({
      policyVersionId: 'policy-replay-load',
      generatedAt: '2026-02-25T09:00:00Z',
      policy: { version: 5, score: 2.5, matches: 10 },
      episodes: [
        buildEpisode({
          episode_id: 'episode-replay-load',
          reward: 1.4,
          opponent_name: 'opponent-c',
          steps: 260,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        }),
      ],
    })

    mockDashboardLoad(response)
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
    const response = buildDashboardResponse({
      policyVersionId: 'policy-prefetch',
      generatedAt: '2026-02-25T09:15:00Z',
      policy: { version: 6, score: 2.6, matches: 11 },
    })

    const pendingDashboard = deferred<DashboardResponse>()
    const pendingDiagnoseRuns = deferred<{ runs: api.DiagnoseRunSummary[] }>()
    vi.mocked(api.fetchDashboardData).mockReturnValueOnce(pendingDashboard.promise)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce(EMPTY_PERCENTILES)
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
    const response = buildDashboardResponse({
      policyVersionId: 'policy-embedded-diagnose',
      generatedAt: '2026-02-25T09:20:00Z',
      policy: { version: 7, score: 2.7, matches: 12 },
      diagnoseRuns: [
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
    })

    mockDashboardLoad(response)
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })
    expect(api.fetchDiagnoseRuns).toHaveBeenCalledTimes(0)
  })

  it('does not block dashboard render on parses preload', async () => {
    const response = buildDashboardResponse({ policyVersionId: 'test-policy-id' })

    const pending = deferred<DashboardResponse>()
    const pendingPercentiles = deferred<DashboardRolePercentilesResponse>()
    const percentiles: DashboardRolePercentilesResponse = EMPTY_PERCENTILES
    vi.mocked(api.fetchDashboardData).mockReturnValueOnce(pending.promise)
    vi.mocked(api.fetchDashboardRolePercentiles).mockReturnValueOnce(pendingPercentiles.promise)
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue(EMPTY_DIAGNOSE_RUNS)

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
    const response = buildDashboardResponse({
      policyVersionId: 'default-top-policy-uuid',
      generatedAt: '2026-02-24T10:35:00Z',
      policy: { version: 2, score: 1.5, matches: 12 },
    })

    vi.mocked(api.fetchDashboardDefaultData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce(EMPTY_PERCENTILES)
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue(EMPTY_DIAGNOSE_RUNS)

    render(<DashboardClient />)

    await waitFor(() => {
      expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledWith('default-top-policy-uuid')
    })
  })

  it('renders the simplified overview pills with merged data-quality status', async () => {
    const response = buildDashboardResponse({
      policyVersionId: 'policy-pill-cleanup',
      generatedAt: '2026-03-01T09:20:00Z',
      policy: { version: 8, rank: 4, score: 1.7, matches: 22 },
      episodes: [
        buildEpisode({ episode_id: 'episode-pill-cleanup-1', reward: 0.9, opponent_name: 'opponent-z', steps: 180 }),
      ],
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
    })

    mockDashboardLoad(response)
    render(<DashboardClient />)

    await waitForDashboardLoad()

    expect(screen.getByText(/^Data Quality$/)).toBeTruthy()
    expect(screen.getByText(/^Action Success$/)).toBeTruthy()
    expect(screen.getAllByText(/^Avg Reward$/).length).toBeGreaterThan(0)
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
    const response = buildDashboardResponse({
      policyVersionId: 'policy-pill-parse-percentile',
      generatedAt: '2026-03-02T15:30:00Z',
      policy: { version: 9, rank: 3, score: 2.0, matches: 30 },
      episodes: [
        buildEpisode({
          episode_id: 'episode-pill-parse-percentile-1',
          reward: 1.6,
          opponent_name: 'opponent-y',
          steps: 200,
        }),
      ],
      derived: {
        kpis: {
          avg_reward: 1.6,
          action_success_rate: 0.91,
          junction_control_rate: 0.72,
          noop_rate: 0.02,
        },
      },
    })

    mockDashboardLoad(response, {
      percentiles: {
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
      },
    })
    render(<DashboardClient />)

    await waitForDashboardLoad()

    await waitFor(() => {
      expect(screen.getByText('pool reward percentile: P88 (sample P100)')).toBeTruthy()
    })
  })

  it('marks missing instrumentation as non-clean data quality', async () => {
    const response = buildDashboardResponse({
      policyVersionId: 'policy-pill-missing-inst',
      generatedAt: '2026-03-02T15:30:00Z',
      policy: { version: 10, rank: 3, score: 2.0, matches: 30 },
      episodes: [
        buildEpisode({
          episode_id: 'episode-pill-missing-inst-1',
          reward: 1.6,
          opponent_name: 'opponent-y',
          steps: 200,
        }),
      ],
      derived: {
        kpis: {
          avg_reward: 1.6,
          action_success_rate: 0.91,
          junction_control_rate: 0.72,
          noop_rate: 0.02,
        },
      },
    })

    mockDashboardLoad(response, {
      percentiles: {
        pool_id: 'pool-missing-inst',
        pool_name: 'default',
        roles: {},
        rows: [],
      },
    })
    render(<DashboardClient />)

    await waitForDashboardLoad()

    expect(screen.getByText('instrumentation summary missing from payload')).toBeTruthy()
    expect(screen.getByText('0 issues · instrumentation missing')).toBeTruthy()
  })

  it('shows parse + teammate summary on overview and keeps coordination focused on slices', async () => {
    const response: DashboardResponse = {
      policy: {
        id: 'policy-overview-coordination-layout',
        name: 'glanky',
        version: 11,
        rank: 2,
        score: 2.4,
        matches: 40,
      },
      episodes: [
        {
          episode_id: 'episode-overview-coordination-layout-1',
          status: 'completed',
          reward: 12.4,
          opponent_name: 'unknown',
          team_composition: 'miner,aligner,scout,scrambler',
          diagnostic_tags: [],
          steps: 220,
          replay_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ',
        },
      ],
      season: 'beta-cvc',
      generated_at: '2026-03-03T10:00:00Z',
      derived: {
        kpis: {
          avg_reward: 11.85,
          action_success_rate: 0.89,
          junction_control_rate: 0.71,
          noop_rate: 0.02,
        },
        failures: {},
        opponent_metrics: {
          unknown: {
            count: 5,
            avg_reward: 53.531,
            strategy_profile: {
              aggressive: 0,
              defensive: 50,
              resource_hoarder: 0,
              junction_hunter: 0,
              mobile_scout: 50,
            },
          },
          nim_random: {
            count: 4,
            avg_reward: 1.0,
            strategy_profile: { aggressive: 0, defensive: 0, resource_hoarder: 0, junction_hunter: 0, mobile_scout: 0 },
          },
        },
        matchup: {
          reason: 'Teammate pairings improved overall (global reward delta +4.80).',
          current_avg_reward: 11.85,
          baseline_avg_reward: 7.054,
          global_reward_delta: 4.796,
          evidence_sufficient: true,
          opponent_spread: 52.501,
          best_opponent: 'unknown',
          worst_opponent: 'buggy',
          composition_spread: 8.819,
          best_composition: '?v?',
          worst_composition: '4v4',
          opponent_slices: [
            { key: 'unknown', avg_reward: 53.531, count: 5, delta_vs_baseline: 4.8, delta_vs_policy: 41.681 },
          ],
          composition_slices: [
            { key: '4v4', avg_reward: 2.0, count: 6, delta_vs_baseline: -1.0, delta_vs_policy: -9.85 },
          ],
        },
      },
      selection: {
        sampled_episode_count: 1,
      },
    }

    vi.mocked(api.fetchDashboardData).mockResolvedValueOnce(response)
    vi.mocked(api.fetchDashboardRolePercentiles).mockResolvedValueOnce({
      pool_id: 'pool-overview-coordination-layout',
      pool_name: 'default',
      roles: {},
      rows: [
        { role: 'aligner', percentile: 65.4, details: {}, updated_at: '2026-03-03T10:00:00Z' },
        { role: 'miner', percentile: 44.4, details: {}, updated_at: '2026-03-03T10:00:00Z' },
        { role: 'scrambler', percentile: 66.1, details: {}, updated_at: '2026-03-03T10:00:00Z' },
        { role: 'scout', percentile: 49.2, details: {}, updated_at: '2026-03-03T10:00:00Z' },
      ],
    })
    vi.mocked(api.fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    window.history.replaceState({}, '', '/?policyVersionId=policy-overview-coordination-layout')
    render(<DashboardClient />)

    await waitFor(() => {
      expect(screen.queryByRole('progressbar')).toBeNull()
    })

    expect(screen.getAllByText('Aligner').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Miner').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Scrambler').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Scout').length).toBeGreaterThan(0)
    expect(screen.getAllByText('P65.4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('P44.4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('P66.1').length).toBeGreaterThan(0)
    expect(screen.getAllByText('P49.2').length).toBeGreaterThan(0)
    expect(screen.getByText('Best Teammate Pairing')).toBeTruthy()
    expect(screen.getByText('Lowest-Reward Teammate Pairing')).toBeTruthy()
    expect(screen.getByText('Teammate Pairing Diagnosis')).toBeTruthy()
    expect(screen.getByText('Teammate Breakdown')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Coordination' }))

    expect(screen.queryByText('Best Teammate Pairing')).toBeNull()
    expect(screen.queryByText('Teammate Pairing Diagnosis')).toBeNull()
    expect(screen.queryByText('Teammate Breakdown')).toBeNull()
    expect(screen.getByText('Teammate Pairing Slices (Current Relative to Baseline)')).toBeTruthy()
    expect(screen.getByText('Composition Slices')).toBeTruthy()
  })

  it('loads pantheon motifs when the Pantheon tab is preselected in the URL', async () => {
    const response = buildDashboardResponse({
      policyVersionId: 'policy-pantheon',
      generatedAt: '2026-03-05T00:10:00Z',
      policy: { version: 12, score: 3.1, matches: 18 },
    })

    mockDashboardLoad(response, { path: '/?policyVersionId=policy-pantheon&tab=pantheon' })
    vi.mocked(api.fetchPantheonStories).mockResolvedValue({
      generated_at: '2026-03-05T00:10:30Z',
      stories: [
        {
          story_id: 'motif-1',
          hall: 'fame',
          title: 'Frozen Junction Hold',
          motif: 'Disciplined hold motif',
          summary: 'Held junction through final ticks.',
          policy: 'glanky:v12',
          created_at: '2026-03-05T00:10:10Z',
          source: 'seeded',
          tags: ['junction-control'],
        },
      ],
    })

    render(<DashboardClient />)

    await waitFor(() => {
      expect(api.fetchPantheonStories).toHaveBeenCalledTimes(1)
    })
    expect(screen.getByText('Frozen Junction Hold')).toBeTruthy()
    expect(screen.getByText('Hall of Fame')).toBeTruthy()
  })

  it('does not refetch parse percentiles when switching non-coordination tabs', async () => {
    const response = buildDashboardResponse({
      policyVersionId: 'policy-123',
      generatedAt: '2026-02-24T10:35:00Z',
      policy: { version: 2, score: 1.5, matches: 12 },
    })

    mockDashboardLoad(response)
    render(<DashboardClient />)

    await waitFor(() => {
      expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledTimes(1)
    })

    fireEvent.click(screen.getByRole('button', { name: 'Episodes' }))
    fireEvent.click(screen.getByRole('button', { name: 'Capabilities' }))
    fireEvent.click(screen.getByRole('button', { name: 'Overview' }))

    expect(api.fetchDashboardRolePercentiles).toHaveBeenCalledTimes(1)
  })
})
