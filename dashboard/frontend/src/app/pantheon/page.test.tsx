import { beforeEach, describe, expect, it, vi } from 'vitest'

const { redirectMock } = vi.hoisted(() => ({
  redirectMock: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  redirect: redirectMock,
}))

import PantheonPage from './page'

describe('PantheonPage', () => {
  beforeEach(() => {
    redirectMock.mockReset()
  })

  it('redirects to pantheon v0 when no query params are provided', async () => {
    await PantheonPage({ searchParams: Promise.resolve({}) })

    expect(redirectMock).toHaveBeenCalledWith('/pantheon/v0')
  })

  it('preserves query params on redirect', async () => {
    await PantheonPage({
      searchParams: Promise.resolve({
        theme: 'dark',
        source: 'embed',
        tags: ['a', 'b'],
      }),
    })

    expect(redirectMock).toHaveBeenCalledWith('/pantheon/v0?theme=dark&source=embed&tags=a&tags=b')
  })
})
