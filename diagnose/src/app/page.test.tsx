import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { fetchDiagnoseRuns } from '../lib/api'
import DiagnoseIndexPage from './page'

vi.mock('../lib/api', () => ({
  fetchDiagnoseRuns: vi.fn(),
}))

vi.mock('./DiagnoseUploadPanel', () => ({
  DiagnoseUploadPanel: () => <div>upload-panel</div>,
}))

describe('DiagnoseIndexPage', () => {
  it('omits the dashboard back link', async () => {
    vi.mocked(fetchDiagnoseRuns).mockResolvedValue({ runs: [] })

    render(await DiagnoseIndexPage())

    expect(screen.queryByText('← Back to dashboard')).toBeNull()
    expect(screen.getByText('No local runs found.')).toBeTruthy()
  })
})
