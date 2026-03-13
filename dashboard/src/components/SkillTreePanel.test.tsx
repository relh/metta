import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { DashboardResponse } from '../lib/api'
import { SkillTreePanel } from './SkillTreePanel'

const BASE_RESPONSE: DashboardResponse = {
  policy: {
    id: 'policy-1',
    name: 'glanky',
    version: 11,
  },
  season: 'beta-cvc',
  generated_at: '2026-02-24T10:30:00Z',
  episodes: [],
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
  cleanup()
})

describe('SkillTreePanel', () => {
  it('renders dependency tree mode by default and allows toggling to grid mode', () => {
    render(<SkillTreePanel data={BASE_RESPONSE} diagnoseNote={null} diagnoseManifest={null} />)

    expect(screen.getByText('Capability Tree')).toBeTruthy()
    expect(
      screen.getByText(
        'Tree view now includes all filtered tiles via related subtrees: core abilities, diagnose evidence, and operational signals.'
      )
    ).toBeTruthy()
    expect(screen.getByText('Coordination')).toBeTruthy()
    expect(screen.getByText('Diagnose Axis: Stability')).toBeTruthy()
    expect(screen.getByText('Mining')).toBeTruthy()

    const collapseDependenciesButton = screen.getByRole('button', { name: 'Collapse 4 dependencies' })
    fireEvent.click(collapseDependenciesButton)
    expect(screen.queryByText('Mining')).toBeNull()

    const expandDependenciesButton = screen.getByRole('button', { name: 'Expand 4 dependencies' })
    fireEvent.click(expandDependenciesButton)
    expect(screen.getByText('Mining')).toBeTruthy()

    const treeButton = screen.getByRole('button', { name: 'Tree' })
    const gridButton = screen.getByRole('button', { name: 'Grid' })
    expect(treeButton.getAttribute('disabled')).not.toBeNull()
    expect(gridButton.getAttribute('disabled')).toBeNull()

    fireEvent.click(gridButton)

    expect(treeButton.getAttribute('disabled')).toBeNull()
    expect(gridButton.getAttribute('disabled')).not.toBeNull()
    expect(screen.getByText('Mining')).toBeTruthy()
  })

  it('labels shaped-reward capabilities as Trained and other tiles as Backed', () => {
    const response: DashboardResponse = {
      ...BASE_RESPONSE,
      derived: {
        ...BASE_RESPONSE.derived,
        capability_code_audit: {
          generated_at: '2026-02-25T12:00:00Z',
          capabilities: {
            mining: {
              status: 'yes',
              support_type: 'trained',
              training_source: 'recipes/experiment/cogsguard.py::miner',
              evidence: [
                'PASS: role recipe function [recipes/experiment/cogsguard.py::miner]',
                'PASS: role-specific reward shaper [packages/cogames/src/cogames/games/cogs_vs_clips/reward_variants.py::_apply_miner]',
              ],
            },
          },
          sources: {
            capability_eval: { status: 'yes', support_type: 'backed', evidence: [] },
            cogames_axis: { status: 'yes', support_type: 'backed', evidence: [] },
            cogames_probe: { status: 'yes', support_type: 'backed', evidence: [] },
            cogames_symptom: { status: 'yes', support_type: 'backed', evidence: [] },
            kpi_diagnostic: { status: 'yes', support_type: 'backed', evidence: [] },
            instrumentation: { status: 'yes', support_type: 'backed', evidence: [] },
            behavior_slice: { status: 'yes', support_type: 'backed', evidence: [] },
          },
        },
      },
    }

    render(<SkillTreePanel data={response} diagnoseNote={null} diagnoseManifest={null} />)

    expect(screen.getAllByText('Trained').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Backed').length).toBeGreaterThan(0)
  })
})
