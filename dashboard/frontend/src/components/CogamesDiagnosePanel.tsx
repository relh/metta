'use client'

import { FC, useMemo } from 'react'

import type {
  DiagnoseAxis,
  DiagnoseDoctorNote,
  DiagnoseManifest,
  DiagnoseProbeEvaluation,
  DiagnoseRunSummary,
} from '../lib/api'

const AXIS_ORDER: DiagnoseAxis[] = ['stability', 'efficiency', 'control', 'social_coordination']

const AXIS_LABEL: Record<DiagnoseAxis, string> = {
  stability: 'Stability',
  efficiency: 'Efficiency',
  control: 'Control',
  social_coordination: 'Social Coordination',
}

function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a'
  return `${(value * 100).toFixed(digits)}%`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export const CogamesDiagnosePanel: FC<{
  runs: DiagnoseRunSummary[]
  loading: boolean
  error: string | null
  selectedRunId: string | null
  onSelectRun: (runId: string) => void
  note: DiagnoseDoctorNote | null
  noteLoading: boolean
  noteError: string | null
  manifest: DiagnoseManifest | null
}> = ({ runs, loading, error, selectedRunId, onSelectRun, note, noteLoading, noteError, manifest }) => {
  const probeEvaluations = useMemo(() => {
    if (!note) return []
    return Array.isArray(note.stage1_probe_evaluations) ? note.stage1_probe_evaluations : []
  }, [note])

  const evalByProbe = useMemo(
    () =>
      new Map<string, DiagnoseProbeEvaluation>(probeEvaluations.map((evaluation) => [evaluation.probe_id, evaluation])),
    [probeEvaluations]
  )

  const probeCatalog = useMemo(() => {
    if (!note) return []
    return Array.isArray(note.stage1_probe_catalog) ? note.stage1_probe_catalog : []
  }, [note])

  const symptoms = useMemo(() => {
    if (!note) return []
    return Array.isArray(note.symptoms) ? note.symptoms : []
  }, [note])

  const prescriptions = useMemo(() => {
    if (!note) return []
    return Array.isArray(note.prescriptions) ? note.prescriptions : []
  }, [note])

  const notes = useMemo(() => {
    if (!note) return []
    return Array.isArray(note.notes) ? note.notes : []
  }, [note])

  const axisScores = useMemo(() => {
    if (!note) return new Map<DiagnoseAxis, NonNullable<DiagnoseDoctorNote['axes']>[number]>()
    const axes = Array.isArray(note.axes) ? note.axes : []
    return new Map(axes.map((entry) => [entry.axis, entry]))
  }, [note])

  return (
    <div className="grid" style={{ gap: 12 }}>
      <section className="card">
        <div className="diagnose-header">
          <div>
            <h2 style={{ marginTop: 0, marginBottom: 4 }}>Cogames Diagnose</h2>
            <p style={{ margin: 0, color: '#546b8a' }}>
              CLI-run diagnostics from <code>outputs/cogames-diagnose</code>. Probe outcomes feed Eval Tree boxes.
            </p>
          </div>
          <code>{manifest?.run_id ?? selectedRunId ?? 'no-run-selected'}</code>
        </div>
      </section>

      <section className="card grid" style={{ gap: 10 }}>
        {loading ? (
          <p style={{ margin: 0 }}>Loading diagnose runs...</p>
        ) : error ? (
          <p style={{ margin: 0, color: '#b42318' }}>
            <strong>Error:</strong> {error}
          </p>
        ) : runs.length === 0 ? (
          <p style={{ margin: 0 }}>No diagnose runs found yet. Run your CLI flow and refresh this tab.</p>
        ) : (
          <div className="diagnose-selector-row">
            <label style={{ display: 'grid', gap: 6 }}>
              Diagnose run
              <select value={selectedRunId ?? ''} onChange={(event) => onSelectRun(event.target.value)}>
                {runs.map((run) => (
                  <option key={run.run_id} value={run.run_id}>
                    {run.run_id}
                  </option>
                ))}
              </select>
            </label>
            <div className="diagnose-meta">
              <span>
                policy: <strong>{manifest?.policy ?? '-'}</strong>
              </span>
              <span>
                stage: <strong>{manifest?.stage_status ?? note?.stage_status ?? '-'}</strong>
              </span>
              <span>
                status: <strong>{manifest?.run_status ?? note?.status ?? '-'}</strong>
              </span>
              <span>created: {formatDateTime(manifest?.created_at)}</span>
            </div>
          </div>
        )}
      </section>

      {noteLoading ? (
        <section className="card">
          <p style={{ margin: 0 }}>Loading doctor note...</p>
        </section>
      ) : noteError ? (
        <section className="card">
          <p style={{ margin: 0, color: '#b42318' }}>
            <strong>Error:</strong> {noteError}
          </p>
        </section>
      ) : note ? (
        <>
          <section className="card">
            <h3 style={{ marginTop: 0 }}>Stage-1 Axes</h3>
            <div className="grid two">
              {AXIS_ORDER.map((axis) => {
                const score = axisScores.get(axis)
                const probesForAxis = probeCatalog.filter((probe) => probe.axis === axis)
                return (
                  <article key={axis} className="diagnose-axis-card">
                    <div className="diagnose-axis-head">
                      <strong>{AXIS_LABEL[axis]}</strong>
                      <span>{score?.confirmed ? 'Mastered' : 'Needs Work'}</span>
                    </div>
                    <p style={{ margin: '8px 0', color: '#546b8a' }}>
                      normalized={score ? formatPct(score.normalized_score, 0) : 'n/a'}
                    </p>
                    <div className="grid" style={{ gap: 8 }}>
                      {probesForAxis.map((probe) => {
                        const evaluation = evalByProbe.get(probe.probe_id)
                        return (
                          <div key={probe.probe_id} className="diagnose-probe-card">
                            <div className="diagnose-axis-head">
                              <code>{probe.probe_id}</code>
                              <span className={evaluation?.passed ? 'diagnose-pass' : 'diagnose-fail'}>
                                {evaluation?.passed ? 'pass' : 'fail'}
                              </span>
                            </div>
                            <p style={{ margin: '6px 0', fontSize: 13 }}>{probe.question}</p>
                            <p style={{ margin: 0, fontSize: 12, color: '#546b8a' }}>
                              {probe.validation_metric} · {probe.pass_fail_threshold}
                            </p>
                            {evaluation?.summary ? (
                              <p style={{ margin: '6px 0 0', fontSize: 12, color: '#546b8a' }}>{evaluation.summary}</p>
                            ) : null}
                          </div>
                        )
                      })}
                    </div>
                  </article>
                )
              })}
            </div>
          </section>

          <section className="grid two">
            <article className="card">
              <h3 style={{ marginTop: 0 }}>Symptoms ({symptoms.length})</h3>
              {symptoms.length === 0 ? (
                <p style={{ marginBottom: 0 }}>No symptoms recorded.</p>
              ) : (
                <div className="grid" style={{ gap: 8 }}>
                  {symptoms.map((symptom) => (
                    <div key={symptom.symptom_id} className="diagnose-list-item">
                      <p style={{ marginTop: 0, marginBottom: 4 }}>
                        <strong>{symptom.symptom_id}</strong> · {AXIS_LABEL[symptom.axis]}
                      </p>
                      <p style={{ margin: '0 0 4px', fontSize: 13 }}>{symptom.likely_cause}</p>
                      <p style={{ margin: 0, fontSize: 12, color: '#546b8a' }}>
                        severity={formatPct(symptom.severity, 0)} · confidence={formatPct(symptom.confidence, 0)}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </article>

            <article className="card">
              <h3 style={{ marginTop: 0 }}>Prescriptions ({prescriptions.length})</h3>
              {prescriptions.length === 0 ? (
                <p style={{ marginBottom: 0 }}>No prescriptions recorded.</p>
              ) : (
                <div className="grid" style={{ gap: 8 }}>
                  {prescriptions.map((prescription, idx) => (
                    <div key={`${prescription.symptom_id}-${idx}`} className="diagnose-list-item">
                      <p style={{ marginTop: 0, marginBottom: 4 }}>
                        <strong>{prescription.symptom_id}</strong> · {prescription.owner}
                      </p>
                      <p style={{ margin: '0 0 4px', fontSize: 13 }}>{prescription.action}</p>
                      <p style={{ margin: 0, fontSize: 12, color: '#546b8a' }}>
                        {prescription.validation_metric} · {prescription.pass_fail_threshold}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </article>
          </section>

          {notes.length > 0 ? (
            <section className="card">
              <h3 style={{ marginTop: 0 }}>Doctor Notes</h3>
              <ul style={{ marginBottom: 0 }}>
                {notes.map((entry, index) => (
                  <li key={`${index}-${entry}`}>{entry}</li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : (
        <section className="card">
          <p style={{ margin: 0 }}>Select a run to load diagnose details.</p>
        </section>
      )}
    </div>
  )
}
