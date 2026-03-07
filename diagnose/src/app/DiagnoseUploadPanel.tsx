'use client'

import { useRef, useState } from 'react'

import { type DiagnoseUploadResponse, uploadDiagnoseBundle } from '../lib/api'

const DEFAULT_DIAGNOSE_COMMAND =
  'uv run cogames diagnose class=random --mission-set cogsguard_evals --bundle-zip ./diagnose-results.zip'

type DiagnoseUploadPanelProps = {
  onUploaded?: (uploaded: DiagnoseUploadResponse) => void
}

export function DiagnoseUploadPanel({ onUploaded }: DiagnoseUploadPanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const onBundleSelected = async (bundle: File | null | undefined) => {
    if (!bundle || loading) return
    setLoading(true)
    setError(null)
    setSuccess(null)
    try {
      const uploaded = await uploadDiagnoseBundle(bundle)
      setSuccess(`Imported ${uploaded.run_id} from ${bundle.name}.`)
      onUploaded?.(uploaded)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <section className="card grid" style={{ gap: 10 }}>
      <h2 style={{ margin: 0 }}>Import Diagnose Bundle</h2>
      <p style={{ margin: 0, color: '#3d5d84', fontSize: 13 }}>
        Run diagnose locally, then upload the exported zip to populate this run catalog.
      </p>
      <code>{DEFAULT_DIAGNOSE_COMMAND}</code>
      <label
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 8,
          width: 'fit-content',
          border: '1px dashed #8da2bb',
          borderRadius: 10,
          padding: '8px 10px',
          cursor: loading ? 'not-allowed' : 'pointer',
          opacity: loading ? 0.65 : 1,
        }}
      >
        <span>Diagnose bundle (.zip)</span>
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          disabled={loading}
          onChange={(event) => {
            void onBundleSelected(event.currentTarget.files?.[0])
          }}
        />
      </label>
      {loading ? <p style={{ margin: 0 }}>Uploading diagnose bundle...</p> : null}
      {error ? (
        <p style={{ margin: 0, color: '#b42318' }}>
          <strong>Error:</strong> {error}
        </p>
      ) : null}
      {success ? <p style={{ margin: 0, color: '#176537' }}>{success}</p> : null}
    </section>
  )
}
