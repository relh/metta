import Link from 'next/link'
import { notFound } from 'next/navigation'

import {
  diagnoseArtifactUrl,
  fetchDiagnoseDoctorNote,
  fetchDiagnoseManifest,
  type DiagnoseAxis,
  type DiagnoseAxisScore,
  type DiagnoseDoctorNote,
  type DiagnoseManifest,
  type DiagnosePrescription,
  type DiagnoseProbeDefinition,
  type DiagnoseProbeEvaluation,
  type DiagnoseSymptom,
} from '../../../lib/api'

const AXIS_ORDER: DiagnoseAxis[] = ['stability', 'efficiency', 'control', 'social_coordination']

const AXIS_LABEL: Record<DiagnoseAxis, string> = {
  stability: 'Stability',
  efficiency: 'Efficiency',
  control: 'Control',
  social_coordination: 'Social Coordination',
}

function formatPct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

function byAxis<T extends { axis: DiagnoseAxis }>(items: T[]): Record<DiagnoseAxis, T[]> {
  return {
    stability: items.filter((item) => item.axis === 'stability'),
    efficiency: items.filter((item) => item.axis === 'efficiency'),
    control: items.filter((item) => item.axis === 'control'),
    social_coordination: items.filter((item) => item.axis === 'social_coordination'),
  }
}

export default async function DiagnoseRunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params

  let manifest: DiagnoseManifest | null = null
  try {
    manifest = await fetchDiagnoseManifest(runId)
  } catch {
    manifest = null
  }

  let doctorNote: DiagnoseDoctorNote | null = null
  try {
    doctorNote = await fetchDiagnoseDoctorNote(runId)
  } catch {
    notFound()
  }
  if (doctorNote === null) {
    notFound()
  }

  const axes = Array.isArray(doctorNote.axes) ? doctorNote.axes : []
  const symptoms = Array.isArray(doctorNote.symptoms) ? doctorNote.symptoms : []
  const prescriptions = Array.isArray(doctorNote.prescriptions) ? doctorNote.prescriptions : []
  const probes = Array.isArray(doctorNote.stage1_probe_catalog) ? doctorNote.stage1_probe_catalog : []
  const probeEvals = Array.isArray(doctorNote.stage1_probe_evaluations) ? doctorNote.stage1_probe_evaluations : []
  const notes = Array.isArray(doctorNote.notes) ? doctorNote.notes : []

  const axisScores = Object.fromEntries(axes.map((axis) => [axis.axis, axis])) as Partial<
    Record<DiagnoseAxis, DiagnoseAxisScore>
  >
  const probesByAxis = byAxis(probes)
  const evalByProbeId = new Map<string, DiagnoseProbeEvaluation>(
    probeEvals.map((evaluation) => [evaluation.probe_id, evaluation])
  )
  const artifactFiles = Array.isArray(manifest?.artifact_files) ? manifest.artifact_files : []
  const artifactList = [
    'manifest.json',
    'doctor_note.json',
    ...artifactFiles.filter((artifact) => artifact !== 'manifest.json' && artifact !== 'doctor_note.json'),
  ]

  return (
    <main className="grid" style={{ gap: 16 }}>
      <header className="card">
        <h1 style={{ marginTop: 0, marginBottom: 8 }}>{manifest?.policy ?? 'Diagnose Run'}</h1>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 13, color: '#3d5d84' }}>
          <code>{runId}</code>
          <span>status={doctorNote.status}</span>
          <span>stage={doctorNote.stage_status}</span>
          {doctorNote.dominant_issue ? <span>dominant={doctorNote.dominant_issue}</span> : null}
        </div>
        <div style={{ marginTop: 10, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Link href="/diagnose" style={{ color: '#1f6feb', textDecoration: 'none' }}>
            ← All runs
          </Link>
          <Link href="/" style={{ color: '#1f6feb', textDecoration: 'none' }}>
            Dashboard
          </Link>
        </div>
      </header>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Artifacts</h2>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {artifactList.map((artifact) => (
            <a
              key={artifact}
              href={diagnoseArtifactUrl(runId, artifact)}
              target="_blank"
              rel="noopener noreferrer"
              style={{ color: '#1f6feb' }}
            >
              {artifact}
            </a>
          ))}
        </div>
        {manifest?.command ? (
          <p style={{ marginBottom: 0, marginTop: 12, color: '#3d5d84', fontSize: 13 }}>
            command: <code>{manifest.command}</code>
          </p>
        ) : null}
      </section>

      <section className="card">
        <h2 style={{ marginTop: 0 }}>Stage 1 Axes</h2>
        <div className="grid two">
          {AXIS_ORDER.map((axis) => {
            const score = axisScores[axis]
            return (
              <article key={axis} style={{ border: '1px solid #d9e1eb', borderRadius: 10, padding: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <strong>{AXIS_LABEL[axis]}</strong>
                  <span>{score?.confirmed ? 'Mastered' : 'Training'}</span>
                </div>
                <p style={{ margin: '8px 0', color: '#3d5d84' }}>
                  normalized={score ? formatPct(score.normalized_score, 0) : 'n/a'}
                </p>
                {score ? (
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13 }}>
                    <li>move_success={formatPct(score.derived_metrics.mean_move_success, 0)}</li>
                    <li>timeout_rate={formatPct(score.derived_metrics.timeout_rate, 1)}</li>
                    <li>reward_variance={score.derived_metrics.reward_variance.toFixed(2)}</li>
                    <li>stuck_steps={score.derived_metrics.mean_stuck_steps.toFixed(0)}</li>
                  </ul>
                ) : (
                  <p style={{ margin: 0, color: '#3d5d84', fontSize: 13 }}>No axis score available.</p>
                )}

                <details style={{ marginTop: 10 }}>
                  <summary>Probes ({probesByAxis[axis].length})</summary>
                  <div style={{ marginTop: 8, display: 'grid', gap: 8 }}>
                    {probesByAxis[axis].map((probe: DiagnoseProbeDefinition) => {
                      const evaluation = evalByProbeId.get(probe.probe_id)
                      return (
                        <div key={probe.probe_id} style={{ border: '1px solid #d9e1eb', borderRadius: 8, padding: 10 }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <strong>{probe.probe_id}</strong>
                            <span>{evaluation?.passed ? 'passed' : 'failed'}</span>
                          </div>
                          <p style={{ margin: '6px 0', color: '#3d5d84', fontSize: 13 }}>{probe.question}</p>
                          <p style={{ margin: 0, color: '#3d5d84', fontSize: 12 }}>
                            {probe.validation_metric} · {probe.pass_fail_threshold}
                          </p>
                          {evaluation?.summary ? (
                            <p style={{ margin: '6px 0 0', color: '#3d5d84', fontSize: 12 }}>{evaluation.summary}</p>
                          ) : null}
                        </div>
                      )
                    })}
                  </div>
                </details>
              </article>
            )
          })}
        </div>
      </section>

      <section className="grid two">
        <article className="card">
          <h2 style={{ marginTop: 0 }}>Symptoms ({symptoms.length})</h2>
          {symptoms.length === 0 ? (
            <p style={{ marginBottom: 0 }}>No symptoms recorded.</p>
          ) : (
            <div className="grid" style={{ gap: 10 }}>
              {symptoms.map((symptom: DiagnoseSymptom) => (
                <div key={symptom.symptom_id} style={{ border: '1px solid #d9e1eb', borderRadius: 8, padding: 10 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <strong>{symptom.symptom_id}</strong>
                    <span>{AXIS_LABEL[symptom.axis]}</span>
                  </div>
                  <p style={{ margin: '6px 0', color: '#3d5d84', fontSize: 13 }}>{symptom.likely_cause}</p>
                  <p style={{ margin: 0, color: '#3d5d84', fontSize: 12 }}>
                    severity={formatPct(symptom.severity, 0)} · confidence={formatPct(symptom.confidence, 0)}
                  </p>
                  <p style={{ margin: '6px 0 0', color: '#3d5d84', fontSize: 12 }}>action: {symptom.action}</p>
                </div>
              ))}
            </div>
          )}
        </article>

        <article className="card">
          <h2 style={{ marginTop: 0 }}>Prescriptions ({prescriptions.length})</h2>
          {prescriptions.length === 0 ? (
            <p style={{ marginBottom: 0 }}>No prescriptions recorded.</p>
          ) : (
            <div className="grid" style={{ gap: 10 }}>
              {prescriptions.map((rx: DiagnosePrescription, idx: number) => (
                <div
                  key={`${rx.symptom_id}-${idx}`}
                  style={{ border: '1px solid #d9e1eb', borderRadius: 8, padding: 10 }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                    <strong>{rx.symptom_id}</strong>
                    <span>{rx.owner}</span>
                  </div>
                  <p style={{ margin: '6px 0', color: '#3d5d84', fontSize: 13 }}>{rx.action}</p>
                  <p style={{ margin: 0, color: '#3d5d84', fontSize: 12 }}>
                    {rx.validation_metric} · {rx.pass_fail_threshold}
                  </p>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      {notes.length > 0 ? (
        <section className="card">
          <h2 style={{ marginTop: 0 }}>Notes</h2>
          <ul style={{ marginBottom: 0 }}>
            {notes.map((note, idx) => (
              <li key={`${idx}-${note}`}>{note}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </main>
  )
}

export async function generateMetadata({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params
  return {
    title: `Diagnose: ${runId} | Standalone Dashboard`,
  }
}
