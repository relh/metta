import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { fetchPantheonStories } from '../../lib/api'
import PantheonV0Page from './page'

vi.mock('../../lib/api', () => ({
  fetchPantheonStories: vi.fn(),
}))

describe('PantheonV0Page', () => {
  it('serves the same pantheon surface as /pantheon', async () => {
    vi.mocked(fetchPantheonStories).mockResolvedValue({
      generated_at: '2026-03-06T00:00:00Z',
      stories: [],
    })

    render(<PantheonV0Page />)

    expect(await screen.findByText('Pantheon')).toBeTruthy()
  })
})
