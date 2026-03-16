import type { ReactNode } from 'react'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import DiagnoseRunPage from './page'
import { fetchDiagnoseDoctorNote, fetchDiagnoseManifest } from '../../lib/api'

const { notFoundMock } = vi.hoisted(() => ({
  notFoundMock: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
}))

vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: { children: ReactNode; href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock('next/navigation', () => ({
  notFound: notFoundMock,
}))

vi.mock('../../lib/api', () => ({
  diagnoseArtifactUrl: vi.fn((runId: string, artifact: string) => `/diagnose/${runId}/${artifact}`),
  fetchDiagnoseDoctorNote: vi.fn(),
  fetchDiagnoseManifest: vi.fn(),
}))

function buildManifest() {
  return {
    run_id: 'run-1',
    created_at: '2026-03-01T00:00:00Z',
    command: 'uv run diagnose',
    policy: 'Test Policy',
    pack_id: 'pack',
    pack_version: '1',
    stage_status: 'complete',
    run_status: 'complete',
    artifact_files: ['extra.json'],
    diagnose_validity: {
      valid: true,
      failed_check_ids: [],
      checks: [],
    },
    interpretation_stability: {
      stable: true,
    },
  }
}

function buildDoctorNote() {
  return {
    run_id: 'run-1',
    status: 'complete',
    stage_status: 'complete',
    dominant_issue: 'none',
    notes: ['healthy'],
    axes: [
      {
        axis: 'stability',
        normalized_score: 80,
        raw_score: 0.8,
        confirmed: true,
        derived_metrics: {
          reward_variance: 0.4,
          non_zero_episode_pct: 1,
          timeout_rate: 0.1,
          mean_move_success: 0.9,
          mean_action_failed: 0.0,
          mean_stuck_steps: 1,
        },
      },
    ],
    stage1_probe_catalog: [],
    stage1_probe_evaluations: [],
    symptoms: [],
    prescriptions: [],
    tournament_objective_context: {},
    evidence_index: {},
  }
}

describe('DiagnoseRunPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders manifest-backed details when both requests succeed', async () => {
    vi.mocked(fetchDiagnoseManifest).mockResolvedValue(buildManifest())
    vi.mocked(fetchDiagnoseDoctorNote).mockResolvedValue(buildDoctorNote())

    render(await DiagnoseRunPage({ params: Promise.resolve({ runId: 'run-1' }) }))

    expect(fetchDiagnoseManifest).toHaveBeenCalledWith('run-1')
    expect(fetchDiagnoseDoctorNote).toHaveBeenCalledWith('run-1')
    expect(screen.getByText('Test Policy')).toBeTruthy()
    expect(screen.getByText('extra.json')).toBeTruthy()
  })

  it('falls back to the generic title when the manifest is unavailable', async () => {
    vi.mocked(fetchDiagnoseManifest).mockRejectedValue(new Error('missing manifest'))
    vi.mocked(fetchDiagnoseDoctorNote).mockResolvedValue(buildDoctorNote())

    render(await DiagnoseRunPage({ params: Promise.resolve({ runId: 'run-1' }) }))

    expect(screen.getByText('Diagnose Run')).toBeTruthy()
  })

  it('ignores probes with unrecognized axis values', async () => {
    vi.mocked(fetchDiagnoseManifest).mockResolvedValue(buildManifest())
    vi.mocked(fetchDiagnoseDoctorNote).mockResolvedValue({
      ...buildDoctorNote(),
      stage1_probe_catalog: [
        {
          probe_id: 'unexpected-axis',
          axis: 'unknown_axis',
          question: 'Should be ignored',
          validation_metric: 'noop',
          pass_fail_threshold: '>0',
        },
      ],
    })

    render(await DiagnoseRunPage({ params: Promise.resolve({ runId: 'run-1' }) }))

    expect(screen.getAllByText('Stage 1 Axes').length).toBeGreaterThan(0)
    expect(screen.queryByText('unexpected-axis')).toBeNull()
  })

  it('calls notFound when the doctor note is unavailable', async () => {
    vi.mocked(fetchDiagnoseManifest).mockResolvedValue(buildManifest())
    vi.mocked(fetchDiagnoseDoctorNote).mockRejectedValue(new Error('missing doctor note'))

    await expect(DiagnoseRunPage({ params: Promise.resolve({ runId: 'run-1' }) })).rejects.toThrow('NOT_FOUND')
    expect(notFoundMock).toHaveBeenCalled()
  })
})
