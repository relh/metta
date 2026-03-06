import Link from 'next/link'

import { fetchDiagnoseRuns, type DiagnoseRunSummary } from '../../lib/api'
import { DiagnoseUploadPanel } from './DiagnoseUploadPanel'

function runTitle(run: DiagnoseRunSummary): string {
  if (!run.manifest) return 'Diagnose run'
  return `${run.manifest.policy} (${run.manifest.pack_id}:${run.manifest.pack_version})`
}

function runSubtitle(run: DiagnoseRunSummary): string {
  if (!run.manifest) return 'manifest.json missing'
  return `stage=${run.manifest.stage_status} · status=${run.manifest.run_status} · created_at=${run.manifest.created_at}`
}

export default async function DiagnoseIndexPage() {
  let runs: DiagnoseRunSummary[] = []
  let error: string | null = null
  try {
    runs = (await fetchDiagnoseRuns()).runs
  } catch (err) {
    error = err instanceof Error ? err.message : String(err)
  }

  return (
    <main className="grid" style={{ gap: 16 }}>
      <header className="card">
        <h1 style={{ marginTop: 0 }}>Cogames Diagnose</h1>
        <p style={{ marginBottom: 0 }}>
          Local runs from <code>outputs/cogames-diagnose</code>
        </p>
      </header>

      <section className="card grid" style={{ gap: 12 }}>
        {error ? (
          <p style={{ margin: 0, color: '#b42318' }}>
            <strong>Error:</strong> {error}
          </p>
        ) : runs.length === 0 ? (
          <p style={{ margin: 0 }}>No local runs found.</p>
        ) : (
          <div className="grid" style={{ gap: 10 }}>
            {runs.map((run) => (
              <div
                key={run.run_id}
                style={{
                  border: '1px solid #d9e1eb',
                  borderRadius: 10,
                  padding: 12,
                  background: '#fff',
                  display: 'grid',
                  gap: 6,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                  <strong>{runTitle(run)}</strong>
                  <Link href={`/diagnose/${encodeURIComponent(run.run_id)}`} style={{ color: '#1f6feb' }}>
                    Open
                  </Link>
                </div>
                <code style={{ fontSize: 12 }}>{run.run_id}</code>
                <span style={{ fontSize: 13, color: '#3d5d84' }}>{runSubtitle(run)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <DiagnoseUploadPanel />
    </main>
  )
}
