import { beforeEach, describe, expect, it, vi } from 'vitest'

const { redirectMock } = vi.hoisted(() => ({
  redirectMock: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  redirect: redirectMock,
}))

import PantheonV0Page from './page'

describe('PantheonV0Page', () => {
  beforeEach(() => {
    redirectMock.mockReset()
  })

  it('redirects to the pantheon tab surface', async () => {
    await PantheonV0Page({ searchParams: Promise.resolve({}) })

    expect(redirectMock).toHaveBeenCalledWith('/?tab=pantheon')
  })

  it('preserves non-tab query params for theme and embed context', async () => {
    await PantheonV0Page({
      searchParams: Promise.resolve({
        tab: 'overview',
        theme: 'light',
        source: 'embed',
        tags: ['x', 'y'],
      }),
    })

    expect(redirectMock).toHaveBeenCalledWith('/?tab=pantheon&theme=light&source=embed&tags=x&tags=y')
  })
})
