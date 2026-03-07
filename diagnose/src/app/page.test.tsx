import { act, cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { type DiagnoseRunsResponse, fetchDiagnoseRuns } from '../lib/api'
import { DiagnoseIndexClient } from './DiagnoseIndexClient'

vi.mock('../lib/api', () => ({
  fetchDiagnoseRuns: vi.fn(),
}))

let latestOnUploaded: ((uploaded: { run_id: string; manifest: null }) => void) | null = null

vi.mock('./DiagnoseUploadPanel', () => ({
  DiagnoseUploadPanel: ({ onUploaded }: { onUploaded?: (uploaded: { run_id: string; manifest: null }) => void }) => {
    latestOnUploaded = onUploaded ?? null
    return <div>upload-panel</div>
  },
}))

describe('DiagnoseIndexClient', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    latestOnUploaded = null
  })

  it('omits the dashboard back link', async () => {
    vi.mocked(fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    render(<DiagnoseIndexClient />)

    expect(await screen.findByText('No local runs found.')).toBeTruthy()
    expect(screen.queryByText('← Back to dashboard')).toBeNull()
  })

  it('preserves uploaded runs when an older load resolves later', async () => {
    let resolveFetch: ((value: DiagnoseRunsResponse) => void) | null = null
    const pendingFetch = new Promise<DiagnoseRunsResponse>((resolve) => {
      resolveFetch = resolve
    })
    vi.mocked(fetchDiagnoseRuns).mockReturnValue(pendingFetch)

    render(<DiagnoseIndexClient />)

    expect(latestOnUploaded).toBeTruthy()
    await act(async () => {
      latestOnUploaded?.({ run_id: 'run-uploaded', manifest: null })
    })

    await act(async () => {
      resolveFetch?.({ runs: [] })
      await pendingFetch
    })

    expect(screen.getByText('run-uploaded')).toBeTruthy()
    expect(screen.queryByText('No local runs found.')).toBeNull()
  })
})
