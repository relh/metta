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
const CORE_STAGE1_AXES: DiagnoseAxis[] = ['stability', 'efficiency', 'control']

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

function parseRefCandidates(reference: string): string[] {
  const trimmed = reference.trim()
  if (!trimmed) return []
  const candidates = new Set<string>([trimmed])
  const patterns = [
    /(episode[_\s-]?id|episode)\s*[:=#]\s*([0-9A-Za-z-]+)/i,
    /(job[_\s-]?id|job)\s*[:=#]\s*([0-9A-Za-z-]+)/i,
    /\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/i,
  ]
  for (const pattern of patterns) {
    const match = trimmed.match(pattern)
    if (!match) continue
    const candidate = match[2] ?? match[1]
    if (candidate) candidates.add(candidate)
  }
  return [...candidates]
}

function replayUrlForEvidenceRef(reference: string, lookup: Record<string, string>): string | null {
  if (/^https?:\/\//i.test(reference)) return reference
  for (const candidate of parseRefCandidates(reference)) {
    if (lookup[candidate]) return lookup[candidate]
  }
  return null
}

function radarPoint(index: number, total: number, normalized: number, size = 220): { x: number; y: number } {
  const radius = (size / 2) * Math.max(0, Math.min(1, normalized))
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2
  const center = size / 2
  return {
    x: center + radius * Math.cos(angle),
    y: center + radius * Math.sin(angle),
  }
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
  replayLookupByRef: Record<string, string>
  policyVersionId: string | null
}> = ({
  runs,
  loading,
  error,
  selectedRunId,
  onSelectRun,
  note,
  noteLoading,
  noteError,
  manifest,
  replayLookupByRef,
  policyVersionId,
}) => {
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

  const coreAxisChecks = useMemo(() => {
    return CORE_STAGE1_AXES.map((axis) => {
      const score = axisScores.get(axis)
      return { axis, confirmed: Boolean(score?.confirmed) }
    })
  }, [axisScores])

  const stage1GateReady = useMemo(() => coreAxisChecks.every((check) => check.confirmed), [coreAxisChecks])

  const hasReplayEvidence = useMemo(() => {
    for (const evaluation of probeEvaluations) {
      const refs = Array.isArray(evaluation.evidence_refs) ? evaluation.evidence_refs : []
      for (const reference of refs) {
        if (/^https?:\/\//i.test(reference)) return true
        if (replayUrlForEvidenceRef(reference, replayLookupByRef)) return true
      }
    }
    return false
  }, [probeEvaluations, replayLookupByRef])

  const stage2GateReady = stage1GateReady && hasReplayEvidence

  const stageStatus = String(manifest?.stage_status ?? note?.stage_status ?? '-')
  const runStatus = String(manifest?.run_status ?? note?.status ?? '-')
  const stageStatusLower = stageStatus.toLowerCase()
  const runStatusLower = runStatus.toLowerCase()
  const stage2Reached = stageStatusLower.includes('stage2') || stageStatusLower.includes('social')
  const runInvalid =
    runStatusLower.includes('invalid') ||
    runStatusLower.includes('incomplete') ||
    (!stage2GateReady && (stageStatusLower.includes('complete') || stage2Reached))

  const radarPolygon = useMemo(() => {
    const points = AXIS_ORDER.map((axis, index) => {
      const score = axisScores.get(axis)
      const normalized = score && Number.isFinite(score.normalized_score) ? score.normalized_score : 0
      return radarPoint(index, AXIS_ORDER.length, normalized)
    })
    return points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')
  }, [axisScores])

  const diagnoseCommand = useMemo(() => {
    if (!policyVersionId) return null
    return `uv run cogames diagnose "metta://policy/${policyVersionId}" --mission-set cogsguard_evals`
  }, [policyVersionId])

  return (
    <div className="grid" style={{ gap: 12 }}>
      <section className="card">
        <div className="diagnose-header">
          <div>
            <h2 style={{ marginTop: 0, marginBottom: 4 }}>Cogames Diagnose</h2>
            <p style={{ margin: 0, color: '#546b8a' }}>
              CLI-run diagnostics from <code>outputs/cogames-diagnose</code>. Stage-1 confirms signals, then Stage-2
              social checks finalize prescriptions.
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
          <div className="grid" style={{ gap: 8 }}>
            <p style={{ margin: 0 }}>No diagnose runs found yet. Run this locally, then refresh this tab:</p>
            {diagnoseCommand ? (
              <div className="diagnose-list-item">
                <code>{diagnoseCommand}</code>
              </div>
            ) : (
              <p style={{ margin: 0, color: '#546b8a' }}>
                Load a policy in the dashboard first so we can generate a UUID-scoped diagnose command.
              </p>
            )}
          </div>
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
                stage: <strong>{stageStatus}</strong>
              </span>
              <span>
                status: <strong>{runStatus}</strong>
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
          <section className="card" style={{ display: 'grid', gap: 10 }}>
            <h3 style={{ margin: 0 }}>Stage Gating + Validity</h3>
            <div className="grid two">
              <article className="diagnose-list-item">
                <p style={{ marginTop: 0, marginBottom: 6 }}>
                  <strong>Stage-1 Core Signals</strong>
                </p>
                <p style={{ margin: '0 0 6px', fontSize: 13 }}>
                  {stage1GateReady ? (
                    <span className="diagnose-pass">Ready for Stage-2</span>
                  ) : (
                    <span className="diagnose-fail">Not ready for Stage-2</span>
                  )}
                </p>
                <ul style={{ margin: 0 }}>
                  {coreAxisChecks.map((check) => (
                    <li key={check.axis}>
                      {AXIS_LABEL[check.axis]}: {check.confirmed ? 'confirmed' : 'missing'}
                    </li>
                  ))}
                </ul>
              </article>
              <article className="diagnose-list-item">
                <p style={{ marginTop: 0, marginBottom: 6 }}>
                  <strong>Run Validity (Required Pack)</strong>
                </p>
                <p style={{ margin: '0 0 6px', fontSize: 13 }}>
                  {runInvalid ? (
                    <span className="diagnose-fail">Invalid/Incomplete</span>
                  ) : (
                    <span className="diagnose-pass">Valid</span>
                  )}
                </p>
                <ul style={{ margin: 0 }}>
                  <li>Replay evidence: {hasReplayEvidence ? 'present' : 'missing'}</li>
                  <li>Stage-2 reached: {stage2Reached ? 'yes' : 'no'}</li>
                  <li>Stage-2 gate status: {stage2GateReady ? 'pass' : 'blocked'}</li>
                </ul>
              </article>
            </div>
          </section>

          <section className="card" style={{ display: 'grid', gap: 10 }}>
            <h3 style={{ margin: 0 }}>Spider Chart + Stage-1 Axes</h3>
            <div className="grid two">
              <article className="diagnose-list-item">
                <svg width="220" height="220" viewBox="0 0 220 220" role="img" aria-label="Axis spider chart">
                  <title>Diagnose axis radar</title>
                  {[0.25, 0.5, 0.75, 1].map((level) => {
                    const ring = AXIS_ORDER.map((_, index) => radarPoint(index, AXIS_ORDER.length, level))
                      .map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`)
                      .join(' ')
                    return (
                      <polygon
                        key={level}
                        points={ring}
                        fill="none"
                        stroke="var(--line)"
                        strokeWidth={1}
                        strokeDasharray={level === 1 ? undefined : '3 3'}
                      />
                    )
                  })}
                  {AXIS_ORDER.map((axis, index) => {
                    const edge = radarPoint(index, AXIS_ORDER.length, 1)
                    return (
                      <line key={axis} x1={110} y1={110} x2={edge.x} y2={edge.y} stroke="var(--line)" strokeWidth={1} />
                    )
                  })}
                  <polygon points={radarPolygon} fill="rgba(37, 99, 235, 0.25)" stroke="#2563eb" strokeWidth={2} />
                  {AXIS_ORDER.map((axis, index) => {
                    const labelPoint = radarPoint(index, AXIS_ORDER.length, 1.08)
                    return (
                      <text
                        key={`${axis}-label`}
                        x={labelPoint.x}
                        y={labelPoint.y}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        style={{ fontSize: 11, fill: 'var(--ink-muted)' }}
                      >
                        {AXIS_LABEL[axis]}
                      </text>
                    )
                  })}
                </svg>
              </article>
              <article className="grid" style={{ gap: 8 }}>
                {AXIS_ORDER.map((axis) => {
                  const score = axisScores.get(axis)
                  return (
                    <div key={axis} className="diagnose-list-item">
                      <div className="diagnose-axis-head">
                        <strong>{AXIS_LABEL[axis]}</strong>
                        <span>{score?.confirmed ? 'confirmed' : 'not confirmed'}</span>
                      </div>
                      <p style={{ margin: '6px 0 0', fontSize: 13 }}>
                        normalized={score ? formatPct(score.normalized_score, 0) : 'n/a'}
                      </p>
                    </div>
                  )
                })}
              </article>
            </div>
          </section>

          <section className="card">
            <h3 style={{ marginTop: 0 }}>Probe Outcomes + Evidence</h3>
            <div className="grid two">
              {AXIS_ORDER.map((axis) => {
                const probesForAxis = probeCatalog.filter((probe) => probe.axis === axis)
                return (
                  <article key={axis} className="diagnose-axis-card">
                    <div className="diagnose-axis-head">
                      <strong>{AXIS_LABEL[axis]}</strong>
                      <span>{probesForAxis.length} probes</span>
                    </div>
                    <div className="grid" style={{ gap: 8, marginTop: 8 }}>
                      {probesForAxis.map((probe) => {
                        const evaluation = evalByProbe.get(probe.probe_id)
                        const evidence = Array.isArray(evaluation?.evidence_refs) ? evaluation.evidence_refs : []
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
                            {evidence.length > 0 && (
                              <div style={{ display: 'grid', gap: 4, marginTop: 8 }}>
                                {evidence.map((reference) => {
                                  const replayUrl = replayUrlForEvidenceRef(reference, replayLookupByRef)
                                  return (
                                    <div key={`${probe.probe_id}-${reference}`} style={{ fontSize: 12 }}>
                                      <code>{reference}</code>{' '}
                                      {replayUrl ? (
                                        <a href={replayUrl} target="_blank" rel="noreferrer">
                                          replay
                                        </a>
                                      ) : null}
                                    </div>
                                  )
                                })}
                              </div>
                            )}
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
