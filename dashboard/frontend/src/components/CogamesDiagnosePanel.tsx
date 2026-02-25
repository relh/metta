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
  return `${value.toFixed(digits)}%`
}

function formatRatioPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a'
  return `${(value * 100).toFixed(digits)}%`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a'
  return value.toFixed(digits)
}

function clampPct(value: number | null | undefined): number {
  if (value === null || value === undefined || !Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, value))
}

function asArray<T>(value: T[] | null | undefined): T[] {
  return Array.isArray(value) ? value : []
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

type SocialReview = {
  confirmed?: boolean
  severity?: number
  confidence?: number
  summary?: string
  evidence_refs?: string[]
}

function parseEvidenceRefsByKey(evidenceRefs: string[] | null | undefined): Record<string, string> {
  const parsed: Record<string, string> = {}
  for (const entry of asArray(evidenceRefs)) {
    if (typeof entry !== 'string') continue
    const equalsIndex = entry.indexOf('=')
    if (equalsIndex <= 0 || equalsIndex >= entry.length - 1) continue
    const key = entry.slice(0, equalsIndex).trim()
    const value = entry.slice(equalsIndex + 1).trim()
    if (!key || !value) continue
    parsed[key] = value
  }
  return parsed
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
  const probeEvaluations = asArray(note?.stage1_probe_evaluations)

  const evalByProbe = useMemo(
    () =>
      new Map<string, DiagnoseProbeEvaluation>(probeEvaluations.map((evaluation) => [evaluation.probe_id, evaluation])),
    [probeEvaluations]
  )

  const probeCatalog = asArray(note?.stage1_probe_catalog)
  const symptoms = asArray(note?.symptoms)
  const prescriptions = asArray(note?.prescriptions)
  const notes = asArray(note?.notes)

  const axisScores = useMemo(() => new Map(asArray(note?.axes).map((entry) => [entry.axis, entry])), [note?.axes])

  const coreAxisChecks = useMemo(() => {
    return CORE_STAGE1_AXES.map((axis) => {
      const score = axisScores.get(axis)
      return { axis, confirmed: Boolean(score?.confirmed) }
    })
  }, [axisScores])

  const stage1GateReady = coreAxisChecks.every((check) => check.confirmed)

  const replayRefs = useMemo(() => {
    const refs = asArray(note?.evidence_index?.replay_refs)
    return refs.filter((entry): entry is string => typeof entry === 'string' && entry.trim().length > 0)
  }, [note])

  const stage2GateReady = stage1GateReady && replayRefs.length > 0

  const stageStatus = String(manifest?.stage_status ?? note?.stage_status ?? '-')
  const runStatus = String(manifest?.run_status ?? note?.status ?? '-')
  const diagnosisStatus = String(note?.diagnosis_status ?? '-')
  const stageStatusLower = stageStatus.toLowerCase()
  const runStatusLower = runStatus.toLowerCase()
  const stage2Reached = stageStatusLower.includes('stage2') || stageStatusLower.includes('social')
  const diagnoseValidity = manifest?.diagnose_validity ?? null
  const runInvalid =
    (typeof diagnoseValidity?.valid === 'boolean' ? !diagnoseValidity.valid : false) ||
    runStatusLower.includes('invalid') ||
    runStatusLower.includes('incomplete') ||
    (!stage2GateReady && (stageStatusLower.includes('complete') || stage2Reached))

  const interpretationStability = manifest?.interpretation_stability ?? null
  const tournamentObjectiveContext = note?.tournament_objective_context ?? null

  const socialReview: SocialReview | null =
    note && typeof note.social_review === 'object' && note.social_review !== null
      ? (note.social_review as SocialReview)
      : null

  const stage2DiagnosisDelta =
    note && typeof note.stage2_diagnosis_delta === 'object' && note.stage2_diagnosis_delta !== null
      ? (note.stage2_diagnosis_delta as { summary?: string; changed?: boolean })
      : null

  const rankedSymptoms = useMemo(
    () =>
      [...symptoms].sort(
        (a, b) => (Number.isFinite(b.severity) ? b.severity : 0) - (Number.isFinite(a.severity) ? a.severity : 0)
      ),
    [symptoms]
  )

  const topSymptom = rankedSymptoms[0] ?? null

  const topPrescription = useMemo(() => {
    if (prescriptions.length === 0) return null
    if (!topSymptom) return prescriptions[0]
    const matching = prescriptions.find((entry) => entry.symptom_id === topSymptom.symptom_id)
    return matching ?? prescriptions[0]
  }, [prescriptions, topSymptom])

  const socialEvidenceByKey = useMemo(() => parseEvidenceRefsByKey(socialReview?.evidence_refs), [socialReview])

  const probeEvaluatedCount = useMemo(
    () => probeCatalog.filter((probe) => evalByProbe.has(probe.probe_id)).length,
    [evalByProbe, probeCatalog]
  )
  const probePassCount = useMemo(
    () => probeCatalog.filter((probe) => evalByProbe.get(probe.probe_id)?.passed).length,
    [evalByProbe, probeCatalog]
  )

  const axisMetricRows = useMemo(() => {
    const rows: Array<{ axis: DiagnoseAxis; metric: string; value: number | null }> = []
    for (const axis of AXIS_ORDER) {
      const score = axisScores.get(axis)
      const metrics = score?.derived_metrics
      if (!metrics || typeof metrics !== 'object' || Array.isArray(metrics)) continue
      for (const [metric, rawValue] of Object.entries(metrics)) {
        rows.push({
          axis,
          metric,
          value: typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue : null,
        })
      }
    }
    return rows
  }, [axisScores])

  const diagnoseValidityChecks = useMemo(() => {
    return asArray(diagnoseValidity?.checks)
  }, [diagnoseValidity?.checks])

  const radarPolygon = useMemo(() => {
    const points = AXIS_ORDER.map((axis, index) => {
      const score = axisScores.get(axis)
      const normalized =
        score && Number.isFinite(score.normalized_score) ? Math.max(0, Math.min(1, score.normalized_score / 100)) : 0
      return radarPoint(index, AXIS_ORDER.length, normalized)
    })
    return points.map((point) => `${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')
  }, [axisScores])

  const diagnoseCommand = useMemo(() => {
    if (!policyVersionId) return null
    return `uv run cogames diagnose "metta://policy/${policyVersionId}" --mission-set cogsguard_evals`
  }, [policyVersionId])

  return (
    <div className="grid diagnose-panel" style={{ gap: 12 }}>
      <section className="grid diagnose-top-row">
        <section className="card">
          <div className="diagnose-header">
            <div className="dashboard-title-line">
              <h2 style={{ margin: 0 }}>Diagnose</h2>
              <span className="dashboard-title-subline">
                CLI-run diagnostics from <code>outputs/cogames-diagnose</code>. Stage-1 confirms signals, then Stage-2
                social checks finalize prescriptions.
              </span>
              <code>{manifest?.run_id ?? selectedRunId ?? 'no-run-selected'}</code>
            </div>
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
              <p style={{ margin: 0 }}>
                No diagnose runs found yet. This is expected unless diagnose artifacts were generated/imported for this
                environment. Run this locally, then refresh this tab:
              </p>
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
                <span>
                  diagnosis: <strong>{diagnosisStatus}</strong>
                </span>
                <span>created: {formatDateTime(manifest?.created_at)}</span>
              </div>
            </div>
          )}
        </section>
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
                  <li>Replay evidence refs: {replayRefs.length}</li>
                  <li>Stage-2 reached: {stage2Reached ? 'yes' : 'no'}</li>
                  <li>Stage-2 gate status: {stage2GateReady ? 'pass' : 'blocked'}</li>
                  <li>
                    Manifest validity:{' '}
                    {typeof diagnoseValidity?.valid === 'boolean' ? String(diagnoseValidity.valid) : 'n/a'}
                  </li>
                </ul>
              </article>
            </div>
          </section>

          <section className="card" style={{ display: 'grid', gap: 10 }}>
            <h3 style={{ margin: 0 }}>Run Findings Snapshot</h3>
            <div className="grid two">
              <article className="diagnose-list-item">
                <div className="grid" style={{ gap: 8 }}>
                  <p style={{ margin: 0 }}>
                    dominant issue: <strong>{note.dominant_issue ?? '-'}</strong>
                  </p>
                  <p style={{ margin: 0 }}>
                    diagnosis status: <strong>{diagnosisStatus}</strong>
                  </p>
                  {topSymptom ? (
                    <p style={{ margin: 0, fontSize: 13 }}>
                      Top Symptom: <strong>{topSymptom.symptom_id}</strong> ({AXIS_LABEL[topSymptom.axis]}) · severity=
                      {formatRatioPct(topSymptom.severity, 0)} · confidence={formatRatioPct(topSymptom.confidence, 0)}
                    </p>
                  ) : (
                    <p style={{ margin: 0, fontSize: 13 }}>Top Symptom: none</p>
                  )}
                  {topPrescription ? (
                    <p style={{ margin: 0, fontSize: 13 }}>
                      Primary Prescription: <strong>{topPrescription.owner}</strong> · {topPrescription.action}
                    </p>
                  ) : (
                    <p style={{ margin: 0, fontSize: 13 }}>Primary Prescription: none</p>
                  )}
                  <p style={{ margin: 0, fontSize: 13 }}>
                    social confirmed:{' '}
                    <strong>{socialReview ? (socialReview.confirmed ? 'true' : 'false') : 'n/a'}</strong> · absolute
                    reward mean: <strong>{socialEvidenceByKey['absolute:policy_reward_mean'] ?? 'n/a'}</strong> · mirror
                    reward mean: <strong>{socialEvidenceByKey['mirror:policy_reward_mean'] ?? 'n/a'}</strong> · mirror
                    gap: <strong>{socialEvidenceByKey['mirror:policy_reward_gap'] ?? 'n/a'}</strong>
                  </p>
                </div>
              </article>

              <article className="diagnose-list-item">
                <div className="grid" style={{ gap: 10 }}>
                  {AXIS_ORDER.map((axis) => {
                    const score = axisScores.get(axis)
                    const scoreValue = score?.normalized_score
                    return (
                      <div key={`snapshot-axis-${axis}`} className="diagnose-axis-score-row">
                        <div className="diagnose-axis-score-head">
                          <span>{AXIS_LABEL[axis]}</span>
                          <span>{score ? formatPct(scoreValue, 0) : 'n/a'}</span>
                        </div>
                        <div className="diagnose-axis-score-track">
                          <div
                            className="diagnose-axis-score-fill"
                            style={{ width: `${clampPct(scoreValue)}%` }}
                            aria-hidden="true"
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </article>
            </div>
          </section>

          <section className="card" style={{ display: 'grid', gap: 10 }}>
            <h3 style={{ margin: 0 }}>Suite Coverage + Probe Scorecard</h3>
            <div className="grid two">
              <article className="diagnose-list-item">
                <p style={{ margin: 0 }}>
                  Pack: <strong>{manifest?.pack_id ?? '-'}</strong> · version{' '}
                  <strong>{manifest?.pack_version ?? '-'}</strong>
                </p>
                <p style={{ margin: '6px 0 0', fontSize: 13 }}>
                  Artifacts: <strong>{asArray(manifest?.artifact_files).length}</strong>
                </p>
                <p style={{ margin: '6px 0 0', fontSize: 13 }}>
                  Command: <code>{manifest?.command ?? '-'}</code>
                </p>
              </article>
              <article className="diagnose-list-item">
                <p style={{ margin: 0 }}>
                  Probe coverage: <strong>{probeEvaluatedCount}</strong> / <strong>{probeCatalog.length}</strong>
                </p>
                <p style={{ margin: '6px 0 0', fontSize: 13 }}>
                  Probe pass rate:{' '}
                  <strong>
                    {probeCatalog.length > 0 ? formatPct((probePassCount / probeCatalog.length) * 100, 0) : 'n/a'}
                  </strong>
                </p>
                <p style={{ margin: '6px 0 0', fontSize: 13 }}>
                  Evidence refs (replay-indexed): <strong>{replayRefs.length}</strong>
                </p>
              </article>
            </div>
            {probeCatalog.length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Probe</th>
                      <th>Axis</th>
                      <th>Mission</th>
                      <th>Validation</th>
                      <th>Status</th>
                      <th>Summary</th>
                      <th>Evidence</th>
                    </tr>
                  </thead>
                  <tbody>
                    {probeCatalog.map((probe) => {
                      const evaluation = evalByProbe.get(probe.probe_id)
                      const evidenceRefs = asArray(evaluation?.evidence_refs)
                      return (
                        <tr key={`probe-score-${probe.probe_id}`}>
                          <td>
                            <code>{probe.probe_id}</code>
                          </td>
                          <td>{AXIS_LABEL[probe.axis]}</td>
                          <td>{probe.mission}</td>
                          <td>
                            <code>{probe.validation_metric}</code> · {probe.pass_fail_threshold}
                          </td>
                          <td>
                            {evaluation ? (
                              <span className={evaluation.passed ? 'diagnose-pass' : 'diagnose-fail'}>
                                {evaluation.passed ? 'pass' : 'fail'}
                              </span>
                            ) : (
                              <span>not-run</span>
                            )}
                          </td>
                          <td>{evaluation?.summary ?? '-'}</td>
                          <td>
                            {evidenceRefs.length === 0 ? (
                              '-'
                            ) : (
                              <div style={{ display: 'grid', gap: 4 }}>
                                {evidenceRefs.map((reference) => {
                                  const replayUrl = replayUrlForEvidenceRef(reference, replayLookupByRef)
                                  return (
                                    <span key={`probe-evidence-${probe.probe_id}-${reference}`}>
                                      <code>{reference}</code>{' '}
                                      {replayUrl ? (
                                        <a href={replayUrl} target="_blank" rel="noreferrer">
                                          replay
                                        </a>
                                      ) : null}
                                    </span>
                                  )
                                })}
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ margin: 0 }}>No probe catalog entries in this diagnose run.</p>
            )}
          </section>

          <section className="grid two">
            <section className="card" style={{ display: 'grid', gap: 8 }}>
              <h3 style={{ margin: 0 }}>Axis Metric Drilldown</h3>
              {axisMetricRows.length === 0 ? (
                <p style={{ marginBottom: 0 }}>No derived axis metrics available.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Axis</th>
                        <th>Metric</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {axisMetricRows.map((row) => (
                        <tr key={`axis-metric-${row.axis}-${row.metric}`}>
                          <td>{AXIS_LABEL[row.axis]}</td>
                          <td>
                            <code>{row.metric}</code>
                          </td>
                          <td>{row.value === null ? 'n/a' : formatNumber(row.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="card" style={{ display: 'grid', gap: 8 }}>
              <h3 style={{ margin: 0 }}>Validity Check Details</h3>
              {diagnoseValidityChecks.length === 0 ? (
                <p style={{ marginBottom: 0 }}>No explicit validity check records in manifest.</p>
              ) : (
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Check</th>
                        <th>Status</th>
                        <th>Details</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diagnoseValidityChecks.map((check) => (
                        <tr key={`validity-check-${check.check_id}`}>
                          <td>
                            <code>{check.check_id}</code>
                          </td>
                          <td>
                            <span className={check.passed ? 'diagnose-pass' : 'diagnose-fail'}>
                              {check.passed ? 'pass' : 'fail'}
                            </span>
                          </td>
                          <td>{check.details}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </section>

          <section className="grid two">
            <article className="card">
              <h3 style={{ marginTop: 0 }}>Tournament Objective Context</h3>
              <ul style={{ marginBottom: 0 }}>
                <li>
                  aligned.junction.held stage1: {formatNumber(tournamentObjectiveContext?.aligned_junction_held_stage1)}
                </li>
                <li>
                  aligned.junction.held stage2 absolute:{' '}
                  {formatNumber(tournamentObjectiveContext?.aligned_junction_held_stage2_absolute)}
                </li>
                <li>
                  aligned.junction.held stage2 mirror:{' '}
                  {formatNumber(tournamentObjectiveContext?.aligned_junction_held_stage2_mirror)}
                </li>
              </ul>
            </article>

            <article className="card">
              <h3 style={{ marginTop: 0 }}>Stage-2 Social Review</h3>
              {socialReview ? (
                <div className="grid" style={{ gap: 8 }}>
                  <p style={{ margin: 0 }}>
                    confirmed: <strong>{socialReview.confirmed ? 'true' : 'false'}</strong>
                  </p>
                  <p style={{ margin: 0 }}>
                    severity: <strong>{formatRatioPct(socialReview.severity ?? null, 0)}</strong>
                  </p>
                  <p style={{ margin: 0 }}>
                    confidence: <strong>{formatRatioPct(socialReview.confidence ?? null, 0)}</strong>
                  </p>
                  {socialReview.summary ? <p style={{ margin: 0 }}>{socialReview.summary}</p> : null}
                  {stage2DiagnosisDelta?.summary ? (
                    <p style={{ margin: 0, color: '#546b8a' }}>delta: {stage2DiagnosisDelta.summary}</p>
                  ) : null}
                </div>
              ) : (
                <p style={{ marginBottom: 0 }}>No social review payload on this doctor note.</p>
              )}
            </article>
          </section>

          <section className="grid two">
            <article className="card">
              <h3 style={{ marginTop: 0 }}>Run Validity Checks</h3>
              {diagnoseValidity ? (
                <div className="grid" style={{ gap: 8 }}>
                  <p style={{ margin: 0 }}>
                    valid: <strong>{diagnoseValidity.valid ? 'true' : 'false'}</strong>
                  </p>
                  <p style={{ margin: 0, fontSize: 13 }}>
                    failed checks:{' '}
                    {Array.isArray(diagnoseValidity.failed_check_ids) && diagnoseValidity.failed_check_ids.length > 0
                      ? diagnoseValidity.failed_check_ids.join(', ')
                      : 'none'}
                  </p>
                </div>
              ) : (
                <p style={{ marginBottom: 0 }}>Manifest unavailable for selected run.</p>
              )}
            </article>

            <article className="card">
              <h3 style={{ marginTop: 0 }}>Interpretation Stability</h3>
              {interpretationStability ? (
                <div className="grid" style={{ gap: 8 }}>
                  <p style={{ margin: 0 }}>
                    stable: <strong>{interpretationStability.stable ? 'true' : 'false'}</strong>
                  </p>
                  <p style={{ margin: 0 }}>
                    snapshots: <strong>{String(interpretationStability.snapshot_count ?? 'n/a')}</strong>
                  </p>
                  {Array.isArray(interpretationStability.notes) && interpretationStability.notes.length > 0 ? (
                    <p style={{ margin: 0, fontSize: 13 }}>{interpretationStability.notes.join(' | ')}</p>
                  ) : null}
                </div>
              ) : (
                <p style={{ marginBottom: 0 }}>Manifest unavailable for selected run.</p>
              )}
            </article>
          </section>

          <section className="card" style={{ display: 'grid', gap: 10 }}>
            <h3 style={{ margin: 0 }}>Spider Chart + Stage-1 Axes</h3>
            <div className="grid two">
              <article className="diagnose-list-item">
                <svg width="220" height="220" viewBox="-18 -18 256 256" role="img" aria-label="Axis spider chart">
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
                        severity={formatRatioPct(symptom.severity, 0)} · confidence=
                        {formatRatioPct(symptom.confidence, 0)}
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
