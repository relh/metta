import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchPantheonStories } from './api'

afterEach(() => {
  vi.restoreAllMocks()
  window.sessionStorage.clear()
  document.cookie = 'observatory_auth_token=; path=/; max-age=0'
  window.history.replaceState({}, '', '/')
})

describe('pantheon api', () => {
  it('fetches stories from the pantheon route namespace', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          generated_at: '2026-03-15T00:00:00Z',
          stories: [],
        })
      )
    )
    vi.stubGlobal('fetch', fetchMock)

    const response = await fetchPantheonStories()

    expect(response.stories).toEqual([])
    expect(String(fetchMock.mock.calls[0][0])).toContain('/pantheon/v1/stories')
  })
})
