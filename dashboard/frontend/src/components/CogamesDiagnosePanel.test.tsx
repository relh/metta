import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { DiagnoseDoctorNote, DiagnoseManifest, DiagnoseRunSummary } from '../lib/api'
import { CogamesDiagnosePanel } from './CogamesDiagnosePanel'

afterEach(() => {
  cleanup()
})

describe('CogamesDiagnosePanel', () => {
  it('renders modern diagnose payload sections and replay evidence links', () => {
    const runId = 'run_modern_001'
    const manifest: DiagnoseManifest = {
      run_id: runId,
      created_at: '2026-02-22T00:00:00Z',
      command: 'cogames diagnose modern-policy',
      policy: 'modern-policy',
      pack_id: 'cg-diagnose-pack',
      pack_version: 'v1',
      stage_status: 'stage2_complete',
      run_status: 'complete',
      artifact_files: ['doctor_note.json', 'manifest.json', 'replays/episode-42.json.zst'],
      diagnose_validity: {
        valid: false,
        failed_check_ids: ['missing_mirror_scrimmage'],
        checks: [{ check_id: 'missing_mirror_scrimmage', passed: false, details: 'mirror mode missing' }],
      },
      interpretation_stability: {
        stable: false,
        snapshot_count: 3,
        notes: ['dominant issue changed across snapshots'],
      },
    }

    const note: DiagnoseDoctorNote = {
      run_id: runId,
      status: 'complete',
      diagnosis_status: 'revised_after_stage2',
      stage_status: 'stage2_complete',
      dominant_issue: 'social_coordination',
      notes: ['stage2 updated primary recommendation'],
      axes: [
        {
          axis: 'stability',
          normalized_score: 77,
          raw_score: 0.77,
          confirmed: true,
          derived_metrics: {
            reward_variance: 0.1,
            non_zero_episode_pct: 0.9,
            timeout_rate: 0.03,
            mean_move_success: 0.8,
            mean_action_failed: 0.2,
            mean_stuck_steps: 0.1,
          },
        },
        {
          axis: 'efficiency',
          normalized_score: 73,
          raw_score: 0.73,
          confirmed: true,
          derived_metrics: {
            reward_variance: 0.2,
            non_zero_episode_pct: 0.91,
            timeout_rate: 0.02,
            mean_move_success: 0.78,
            mean_action_failed: 0.22,
            mean_stuck_steps: 0.11,
          },
        },
        {
          axis: 'control',
          normalized_score: 69,
          raw_score: 0.69,
          confirmed: true,
          derived_metrics: {
            reward_variance: 0.21,
            non_zero_episode_pct: 0.88,
            timeout_rate: 0.04,
            mean_move_success: 0.7,
            mean_action_failed: 0.3,
            mean_stuck_steps: 0.16,
          },
        },
        {
          axis: 'social_coordination',
          normalized_score: 45,
          raw_score: 0.45,
          confirmed: false,
          derived_metrics: {
            reward_variance: 0.34,
            non_zero_episode_pct: 0.7,
            timeout_rate: 0.08,
            mean_move_success: 0.65,
            mean_action_failed: 0.35,
            mean_stuck_steps: 0.2,
          },
        },
      ],
      stage1_probe_catalog: [
        {
          probe_id: 'heart_box_under_pressure',
          axis: 'stability',
          mission: 'aligned.junction.held',
          question: 'Does policy opportunistically divert for heart boxes under pressure?',
          validation_metric: 'diversion_latency',
          pass_fail_threshold: '<= 2 steps',
        },
      ],
      stage1_probe_evaluations: [
        {
          probe_id: 'heart_box_under_pressure',
          axis: 'stability',
          passed: true,
          summary: 'Policy diverted once then resumed objective',
          evidence_refs: ['episode-42'],
        },
      ],
      symptoms: [
        {
          symptom_id: 'social_bridge_window_miss',
          axis: 'social_coordination',
          severity: 0.8,
          confidence: 0.7,
          likely_cause: 'late response to teammate bridge window',
          action: 'tighten teammate event trigger budget',
          expected_effect: 'better timed bridge crossing',
        },
      ],
      prescriptions: [
        {
          symptom_id: 'social_bridge_window_miss',
          action: 'add timed bridge social probe with strict window',
          owner: 'research',
          validation_metric: 'cross_in_window_rate',
          pass_fail_threshold: '>= 0.8',
        },
      ],
      tournament_objective_context: {
        aligned_junction_held_stage1: 0.111,
        aligned_junction_held_stage2_absolute: 0.222,
        aligned_junction_held_stage2_mirror: 0.333,
      },
      social_review: {
        confirmed: true,
        severity: 0.8,
        confidence: 0.9,
        summary: 'Coordination degraded under teammate timing dependence.',
        evidence_refs: [
          'absolute:policy_reward_mean=0.5521',
          'mirror:policy_reward_mean=0.4988',
          'mirror:policy_reward_gap=0.0533',
        ],
      },
      stage2_diagnosis_delta: {
        stage1_dominant_issue: 'speed',
        final_dominant_issue: 'social_coordination',
        changed: true,
        summary: 'Stage-2 social evidence changed the diagnosis.',
        evidence_refs: ['episode-42'],
      },
      evidence_index: {
        replay_refs: ['episode-42'],
      },
    }

    const runs: DiagnoseRunSummary[] = [{ run_id: runId, manifest }]

    render(
      <CogamesDiagnosePanel
        runs={runs}
        loading={false}
        error={null}
        selectedRunId={runId}
        onSelectRun={vi.fn()}
        note={note}
        noteLoading={false}
        noteError={null}
        manifest={manifest}
        replayLookupByRef={{ 'episode-42': 'https://example.test/replays/episode-42' }}
        policyVersionId="policy-123"
      />
    )

    expect(screen.getByText('Ready for Stage-2')).toBeTruthy()
    expect(screen.getByText('Invalid/Incomplete')).toBeTruthy()
    expect(screen.getByText(/aligned\.junction\.held stage1:\s*0\.111/)).toBeTruthy()
    expect(screen.getByText(/aligned\.junction\.held stage2 absolute:\s*0\.222/)).toBeTruthy()
    expect(screen.getByText(/aligned\.junction\.held stage2 mirror:\s*0\.333/)).toBeTruthy()
    expect(screen.getByText((_, node) => node?.textContent?.trim() === 'severity: 80%')).toBeTruthy()
    expect(screen.getByText((_, node) => node?.textContent?.trim() === 'confidence: 90%')).toBeTruthy()
    expect(screen.getByText('delta: Stage-2 social evidence changed the diagnosis.')).toBeTruthy()
    expect(screen.getByText(/failed checks:\s*missing_mirror_scrimmage/)).toBeTruthy()
    expect(screen.getByText('dominant issue changed across snapshots')).toBeTruthy()
    expect(screen.getByText('Run Findings Snapshot')).toBeTruthy()
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === 'P' && (node?.textContent ?? '').includes('dominant issue: social_coordination')
      )
    ).toBeTruthy()
    expect(
      screen.getByText(
        (_, node) =>
          node?.tagName === 'P' && (node?.textContent ?? '').includes('diagnosis status: revised_after_stage2')
      )
    ).toBeTruthy()
    expect(
      screen.getByText((_, node) =>
        node?.tagName === 'P' &&
        ((node?.textContent ?? '').includes('Top Symptom: social_bridge_window_miss (Social Coordination)') ?? false)
      )
    ).toBeTruthy()
    expect(
      screen.getByText((_, node) =>
        node?.tagName === 'P' &&
        (node?.textContent ?? '').includes('Primary Prescription: research') &&
        (node?.textContent ?? '').includes('add timed bridge social probe with strict window')
      )
    ).toBeTruthy()
    expect(
      screen.getByText((_, node) =>
        node?.tagName === 'P' &&
        (node?.textContent ?? '').includes('social confirmed:') &&
        (node?.textContent ?? '').includes('absolute reward mean: 0.5521') &&
        (node?.textContent ?? '').includes('mirror reward mean: 0.4988') &&
        (node?.textContent ?? '').includes('mirror gap: 0.0533')
      )
    ).toBeTruthy()

    const replayLink = screen.getByRole('link', { name: 'replay' })
    expect(replayLink.getAttribute('href')).toBe('https://example.test/replays/episode-42')
  })

  it('uses canonical evidence_index replay refs only for stage-2 gate', () => {
    const runId = 'run_missing_canonical_replay_refs'
    const manifest: DiagnoseManifest = {
      run_id: runId,
      created_at: '2026-02-20T00:00:00Z',
      command: 'cogames diagnose modern-policy',
      policy: 'modern-policy',
      pack_id: 'cg-diagnose-pack',
      pack_version: 'v1',
      stage_status: 'stage2_complete',
      run_status: 'complete',
      artifact_files: ['doctor_note.json', 'manifest.json'],
      diagnose_validity: {
        valid: true,
        failed_check_ids: [],
        checks: [],
      },
      interpretation_stability: {
        stable: true,
        snapshot_count: 1,
        notes: [],
      },
    }

    const note: DiagnoseDoctorNote = {
      run_id: runId,
      status: 'complete',
      stage_status: 'stage2_complete',
      dominant_issue: 'social_coordination',
      notes: [],
      axes: [
        {
          axis: 'stability',
          normalized_score: 80,
          raw_score: 0.8,
          confirmed: true,
          derived_metrics: {
            reward_variance: 0.1,
            non_zero_episode_pct: 0.9,
            timeout_rate: 0.02,
            mean_move_success: 0.8,
            mean_action_failed: 0.2,
            mean_stuck_steps: 0.1,
          },
        },
        {
          axis: 'efficiency',
          normalized_score: 75,
          raw_score: 0.75,
          confirmed: true,
          derived_metrics: {
            reward_variance: 0.11,
            non_zero_episode_pct: 0.88,
            timeout_rate: 0.03,
            mean_move_success: 0.79,
            mean_action_failed: 0.21,
            mean_stuck_steps: 0.11,
          },
        },
        {
          axis: 'control',
          normalized_score: 71,
          raw_score: 0.71,
          confirmed: true,
          derived_metrics: {
            reward_variance: 0.12,
            non_zero_episode_pct: 0.87,
            timeout_rate: 0.04,
            mean_move_success: 0.77,
            mean_action_failed: 0.23,
            mean_stuck_steps: 0.12,
          },
        },
      ],
      stage1_probe_catalog: [
        {
          probe_id: 'stage1_probe',
          axis: 'stability',
          mission: 'aligned.junction.held',
          question: 'probe replay evidence check',
          validation_metric: 'noop',
          pass_fail_threshold: 'noop',
        },
      ],
      stage1_probe_evaluations: [
        {
          probe_id: 'stage1_probe',
          axis: 'stability',
          passed: true,
          summary: 'probe still emits evidence refs',
          evidence_refs: ['episode-probe-1'],
        },
      ],
      symptoms: [],
      prescriptions: [],
      tournament_objective_context: {},
      evidence_index: {
        replay_refs: [],
      },
    }

    render(
      <CogamesDiagnosePanel
        runs={[{ run_id: runId, manifest }]}
        loading={false}
        error={null}
        selectedRunId={runId}
        onSelectRun={vi.fn()}
        note={note}
        noteLoading={false}
        noteError={null}
        manifest={manifest}
        replayLookupByRef={{ 'episode-probe-1': 'https://example.test/replays/episode-probe-1' }}
        policyVersionId="policy-123"
      />
    )

    expect(screen.getByText(/Replay evidence refs:\s*0/)).toBeTruthy()
    expect(screen.getByText(/Stage-2 gate status:\s*blocked/)).toBeTruthy()
    expect(screen.getByText('Invalid/Incomplete')).toBeTruthy()
  })
})
