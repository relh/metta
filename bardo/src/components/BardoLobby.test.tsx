import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BardoLobby } from './BardoLobby'

const replaceMock = vi.fn()
let currentSearchParams = new URLSearchParams()

vi.mock('next/image', () => ({
  default: (props: Record<string, unknown>) => {
    const { alt, ...rest } = props
    delete rest.unoptimized
    // eslint-disable-next-line @next/next/no-img-element
    return <img alt={typeof alt === 'string' ? alt : ''} {...rest} />
  },
}))

vi.mock('next/navigation', () => ({
  usePathname: () => '/bardo',
  useRouter: () => ({
    replace: replaceMock,
  }),
  useSearchParams: () => currentSearchParams,
}))

const WORLD_STATE = {
  generatedAt: '2026-03-13T12:00:00Z',
  totalPolicies: 2,
  policies: [
    {
      policyId: 'policy-1',
      policyVersionId: 'version-1',
      name: 'alpha-runner',
      userId: 'user-1',
      userName: 'Alpha User',
      createdAt: '2026-03-13T11:00:00Z',
      activeJobIds: [],
      seasonIds: ['season-1'],
    },
    {
      policyId: 'policy-2',
      policyVersionId: 'version-2',
      name: 'beta-builder',
      userId: 'user-2',
      userName: 'Beta User',
      createdAt: '2026-03-13T11:05:00Z',
      activeJobIds: ['job-1'],
      seasonIds: [],
    },
  ],
  activeJobs: [
    {
      id: 'job-1',
      status: 'running',
      policyVersionIds: ['version-2'],
    },
  ],
  seasons: [
    {
      seasonId: 'season-1',
      name: 'Alpha Season',
      version: 1,
      compatVersion: '0.13',
      createdAt: '2026-03-13T10:00:00Z',
      stageCount: 2,
      entrantCount: 1,
      activeEntrantCount: 1,
    },
  ],
}

describe('BardoLobby', () => {
  beforeEach(() => {
    replaceMock.mockReset()
    currentSearchParams = new URLSearchParams()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        async () =>
          new Response(JSON.stringify(WORLD_STATE), {
            status: 200,
            headers: { ETag: 'W/"bardo-world"' },
          })
      )
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('initializes the visible filter state from the q search param', async () => {
    currentSearchParams = new URLSearchParams('q=alpha')

    render(<BardoLobby />)

    expect(await screen.findByDisplayValue('alpha')).toBeTruthy()
    expect((await screen.findAllByText('Filter: "alpha"')).length).toBeGreaterThan(0)

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(1)
    })
    expect(String(vi.mocked(fetch).mock.calls[0]?.[0])).toContain('/api/world-state?q=alpha')
  })

  it('submits the filter form and preserves unrelated search params in the URL', async () => {
    currentSearchParams = new URLSearchParams('theme=dark')

    render(<BardoLobby />)

    const input = await screen.findByLabelText('Filter policies')
    fireEvent.change(input, { target: { value: 'beta user' } })
    fireEvent.submit(input.closest('form')!)

    expect(replaceMock).toHaveBeenCalledWith('/bardo?theme=dark&q=beta+user')
  })

  it('clears the active filter and removes q from the URL', async () => {
    currentSearchParams = new URLSearchParams('q=alpha&theme=light')

    render(<BardoLobby />)

    const clearButton = await screen.findByRole('button', { name: 'Clear' })
    fireEvent.click(clearButton)

    expect(replaceMock).toHaveBeenCalledWith('/bardo?theme=light')
    expect((screen.getByLabelText('Filter policies') as HTMLInputElement).value).toBe('')
  })

  it('keeps the clear button visible while the active URL filter still differs from the draft input', async () => {
    currentSearchParams = new URLSearchParams('q=alpha')

    render(<BardoLobby />)

    const input = await screen.findByLabelText('Filter policies')
    fireEvent.change(input, { target: { value: '' } })

    expect(screen.getByRole('button', { name: 'Clear' })).toBeTruthy()
  })
})
