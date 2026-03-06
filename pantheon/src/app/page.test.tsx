import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { fetchPantheonStories } from '../lib/api'
import PantheonPage from './page'

vi.mock('../lib/api', () => ({
  fetchPantheonStories: vi.fn(),
}))

describe('PantheonPage', () => {
  it('shows an empty state when there are no stories', async () => {
    vi.mocked(fetchPantheonStories).mockResolvedValue({
      generated_at: '2026-03-06T00:00:00Z',
      stories: [],
    })

    render(<PantheonPage />)

    expect(await screen.findByText('No Pantheon stories found yet.')).toBeTruthy()
  })

  it('shows grouped hall counts from API data', async () => {
    vi.mocked(fetchPantheonStories).mockResolvedValue({
      generated_at: '2026-03-06T00:00:00Z',
      stories: [
        {
          story_id: 'story-1',
          hall: 'fame',
          title: 'Fame Story',
          motif: 'motif',
          summary: 'summary',
          policy: 'policy-a',
          created_at: '2026-03-06T00:00:00Z',
        },
      ],
    })

    render(<PantheonPage />)

    expect(await screen.findByText('Hall of Fame')).toBeTruthy()
    expect(screen.getByText('Fame Story')).toBeTruthy()
  })
})
