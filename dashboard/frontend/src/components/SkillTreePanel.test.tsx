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
      screen.getByText('Dependency tree uses capability-eval signals only. Root skill depends on child skills.')
    ).toBeTruthy()
    expect(screen.getByText('Coordination')).toBeTruthy()

    const treeButton = screen.getByRole('button', { name: 'Tree' })
    const gridButton = screen.getByRole('button', { name: 'Grid' })
    expect(treeButton.getAttribute('disabled')).not.toBeNull()
    expect(gridButton.getAttribute('disabled')).toBeNull()

    fireEvent.click(gridButton)

    expect(treeButton.getAttribute('disabled')).toBeNull()
    expect(gridButton.getAttribute('disabled')).not.toBeNull()
    expect(screen.getByText('Mining')).toBeTruthy()
  })
})
