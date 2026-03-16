import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  diagnoseArtifactUrl,
  fetchDiagnoseDoctorNote,
  fetchDiagnoseManifest,
  fetchDiagnoseRuns,
  uploadDiagnoseBundle,
} from './api'

afterEach(() => {
  vi.restoreAllMocks()
  window.sessionStorage.clear()
  document.cookie = 'observatory_auth_token=; path=/; max-age=0'
  window.history.replaceState({}, '', '/')
})

describe('diagnose api', () => {
  it('uses the diagnose route namespace for list, detail, upload, and artifact URLs', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ runs: [] })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ run_id: 'run id' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ run_id: 'run id' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ run_id: 'run id', manifest: null })))
    vi.stubGlobal('fetch', fetchMock)

    await fetchDiagnoseRuns()
    await fetchDiagnoseManifest('run id')
    await fetchDiagnoseDoctorNote('run id')
    await uploadDiagnoseBundle(new File(['zip-data'], 'bundle.zip', { type: 'application/zip' }))

    expect(String(fetchMock.mock.calls[0][0])).toContain('/diagnose/v1/runs')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/diagnose/v1/runs/run%20id/manifest')
    expect(String(fetchMock.mock.calls[2][0])).toContain('/diagnose/v1/runs/run%20id/doctor-note')
    expect(String(fetchMock.mock.calls[3][0])).toContain('/diagnose/v1/runs/upload')
    expect(diagnoseArtifactUrl('run id', 'report.html')).toContain(
      '/diagnose/v1/runs/run%20id/artifacts/report.html'
    )
  })
})
