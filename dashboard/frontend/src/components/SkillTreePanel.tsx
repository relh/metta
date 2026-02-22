'use client'

import { FC, useMemo, useState } from 'react'

import type { DashboardResponse, DiagnoseAxis, DiagnoseDoctorNote, DiagnoseManifest } from '../lib/api'

type CapabilityIndicator = 'yes' | 'partial' | 'no' | 'planned'

type CapabilityCard = {
  id: string
  title: string
  description: string
  axis: DiagnoseAxis
  trained: CapabilityIndicator
  eval: CapabilityIndicator
  evidence: string[]
}

type IndicatorFilter = 'all' | CapabilityIndicator

type CapabilitySpec = {
  id: string
  title: string
  description: string
  axis: DiagnoseAxis
  trainingSource: string
}

const CAPABILITY_SPECS: CapabilitySpec[] = [
  {
    id: 'mining',
    title: 'Mining',
    description: 'Extract and bank resources with sustained throughput.',
    axis: 'efficiency',
    trainingSource: 'recipes/experiment/cogsguard.py::miner',
  },
  {
    id: 'aligning',
    title: 'Aligning',
    description: 'Capture and hold junction control objectives.',
    axis: 'control',
    trainingSource: 'recipes/experiment/cogsguard.py::aligner',
  },
  {
    id: 'scrambling',
    title: 'Scrambling',
    description: 'Disrupt opponent plans and force mistakes.',
    axis: 'control',
    trainingSource: 'planned scrambler curriculum',
  },
  {
    id: 'scouting',
    title: 'Scouting',
    description: 'Discover routes quickly and keep mobility high.',
    axis: 'stability',
    trainingSource: 'recipes/experiment/cogsguard.py::scout',
  },
  {
    id: 'coordination',
    title: 'Coordination',
    description: 'Coordinate roles under shared pressure.',
    axis: 'social_coordination',
    trainingSource: 'join curricula (scout/miner/aligning)',
  },
]

const INDICATOR_LABEL: Record<CapabilityIndicator, string> = {
  yes: 'Yes',
  partial: 'Partial',
  no: 'No',
  planned: 'Planned',
}

const AXIS_LABEL: Record<DiagnoseAxis, string> = {
  stability: 'Stability',
  efficiency: 'Efficiency',
  control: 'Control',
  social_coordination: 'Social Coordination',
}

const INDICATOR_FILTERS: Array<{ value: IndicatorFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'yes', label: 'Yes' },
  { value: 'partial', label: 'Partial' },
  { value: 'planned', label: 'Planned' },
  { value: 'no', label: 'No' },
]

function numeric(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((entry) => String(entry)) : []
}

function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

function indicatorRank(value: CapabilityIndicator): number {
  if (value === 'no') return 0
  if (value === 'planned') return 1
  if (value === 'partial') return 2
  return 3
}

function strongerIndicator(left: CapabilityIndicator, right: CapabilityIndicator): CapabilityIndicator {
  return indicatorRank(right) > indicatorRank(left) ? right : left
}

function mechanicEvalIndicators(data: DashboardResponse): Record<string, CapabilityIndicator> {
  const kpis = data.derived.kpis
  const diagnostics = asStringArray(kpis.diagnostics).join(' ').toLowerCase()

  const mining =
    numeric(kpis.resource_efficiency_per_step) > 0.02 || numeric(kpis.resource_retention) > 0.2 ? 'yes' : 'partial'

  const aligning =
    numeric(kpis.junction_control_rate) > 0.2 || numeric(kpis.alignment_stability) > 0.12 ? 'yes' : 'partial'

  const scrambling =
    diagnostics.includes('scramble') || diagnostics.includes('aggressive') || numeric(kpis.profile_aggressive) > 25
      ? 'partial'
      : 'no'

  const scouting = numeric(kpis.move_efficiency) > 0.52 || numeric(kpis.profile_mobile_scout) > 25 ? 'yes' : 'partial'

  const coordination = data.derived.outcome?.evidence_sufficient ? 'partial' : 'no'

  return {
    mining,
    aligning,
    scrambling,
    scouting,
    coordination,
  }
}

function trainedIndicators(): Record<string, CapabilityIndicator> {
  return {
    mining: 'yes',
    aligning: 'yes',
    scrambling: 'planned',
    scouting: 'yes',
    coordination: 'partial',
  }
}

function axisIndicator(
  note: DiagnoseDoctorNote | null,
  axis: DiagnoseAxis
): { indicator: CapabilityIndicator; evidence: string } | null {
  if (!note) return null
  const score = (Array.isArray(note.axes) ? note.axes : []).find((entry) => entry.axis === axis)
  if (!score) return null

  const indicator = score.confirmed ? 'yes' : score.normalized_score >= 0.65 ? 'partial' : 'no'
  const evidence = `axis ${AXIS_LABEL[axis]}=${formatPercent(score.normalized_score)} (confirmed=${String(score.confirmed)})`
  return { indicator, evidence }
}

function probeIndicator(
  note: DiagnoseDoctorNote | null,
  axis: DiagnoseAxis
): { indicator: CapabilityIndicator; evidence: string } | null {
  if (!note) return null
  const evaluations = (Array.isArray(note.stage1_probe_evaluations) ? note.stage1_probe_evaluations : []).filter(
    (entry) => entry.axis === axis
  )
  if (evaluations.length === 0) return null

  const passed = evaluations.filter((entry) => entry.passed).length
  const indicator = passed === evaluations.length ? 'yes' : passed > 0 ? 'partial' : 'no'
  return { indicator, evidence: `diagnose probes on ${AXIS_LABEL[axis]}: ${passed}/${evaluations.length} passing` }
}

function buildCapabilityCards(
  data: DashboardResponse,
  note: DiagnoseDoctorNote | null,
  manifest: DiagnoseManifest | null
): CapabilityCard[] {
  const trained = trainedIndicators()
  const evalFromMetrics = mechanicEvalIndicators(data)

  return CAPABILITY_SPECS.map((spec) => {
    const axisSignal = axisIndicator(note, spec.axis)
    const probeSignal = probeIndicator(note, spec.axis)

    let evalIndicator = evalFromMetrics[spec.id] ?? 'no'
    if (axisSignal) {
      evalIndicator = strongerIndicator(evalIndicator, axisSignal.indicator)
    }
    if (probeSignal) {
      evalIndicator = probeSignal.indicator
    }

    const evidence = [
      `training source: ${spec.trainingSource}`,
      axisSignal?.evidence,
      probeSignal?.evidence,
      manifest?.run_id ? `diagnose run: ${manifest.run_id}` : null,
    ].filter((value): value is string => Boolean(value))

    return {
      id: spec.id,
      title: spec.title,
      description: spec.description,
      axis: spec.axis,
      trained: trained[spec.id] ?? 'planned',
      eval: evalIndicator,
      evidence,
    }
  })
}

export const SkillTreePanel: FC<{
  data: DashboardResponse
  diagnoseNote?: DiagnoseDoctorNote | null
  diagnoseManifest?: DiagnoseManifest | null
}> = ({ data, diagnoseNote = null, diagnoseManifest = null }) => {
  const [query, setQuery] = useState('')
  const [trainedFilter, setTrainedFilter] = useState<IndicatorFilter>('all')
  const [evalFilter, setEvalFilter] = useState<IndicatorFilter>('all')

  const capabilities = useMemo(
    () => buildCapabilityCards(data, diagnoseNote, diagnoseManifest),
    [data, diagnoseManifest, diagnoseNote]
  )

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return capabilities.filter((capability) => {
      const queryMatch =
        normalized.length === 0 ||
        [capability.title, capability.description, ...capability.evidence].join(' ').toLowerCase().includes(normalized)
      const trainedMatch = trainedFilter === 'all' || capability.trained === trainedFilter
      const evalMatch = evalFilter === 'all' || capability.eval === evalFilter
      return queryMatch && trainedMatch && evalMatch
    })
  }, [capabilities, evalFilter, query, trainedFilter])

  const counts = useMemo(() => {
    const next: Record<CapabilityIndicator, number> = {
      yes: 0,
      partial: 0,
      planned: 0,
      no: 0,
    }
    for (const capability of capabilities) {
      next[capability.eval] += 1
    }
    return next
  }, [capabilities])

  return (
    <div className="grid" style={{ gap: 12 }}>
      <section className="card grid" style={{ gap: 12 }}>
        <div className="dashboard-control-head">
          <div>
            <h2 style={{ marginTop: 0, marginBottom: 4 }}>Capability Grid</h2>
            <p style={{ margin: 0, color: '#6b7280' }}>
              Unified capability view for both Eval and Train tabs. Each box tracks training coverage and eval outcomes.
            </p>
          </div>
        </div>

        <div className="skill-controls capability-controls">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search capabilities and evidence..."
          />
          <select value={trainedFilter} onChange={(event) => setTrainedFilter(event.target.value as IndicatorFilter)}>
            {INDICATOR_FILTERS.map((option) => (
              <option key={`trained-${option.value}`} value={option.value}>
                Trained: {option.label}
              </option>
            ))}
          </select>
          <select value={evalFilter} onChange={(event) => setEvalFilter(event.target.value as IndicatorFilter)}>
            {INDICATOR_FILTERS.map((option) => (
              <option key={`eval-${option.value}`} value={option.value}>
                Eval: {option.label}
              </option>
            ))}
          </select>
        </div>
      </section>

      <section className="card">
        <div className="skill-legend">
          <span className="badge badge-status indicator-yes">Eval Yes {counts.yes}</span>
          <span className="badge badge-status indicator-partial">Eval Partial {counts.partial}</span>
          <span className="badge badge-status indicator-planned">Eval Planned {counts.planned}</span>
          <span className="badge badge-status indicator-no">Eval No {counts.no}</span>
        </div>
      </section>

      <section className="capability-grid">
        {filtered.length === 0 ? (
          <article className="card">
            <p style={{ margin: 0 }}>No capabilities match current filters.</p>
          </article>
        ) : (
          filtered.map((capability) => (
            <article key={capability.id} className="card capability-card">
              <div className="capability-card-head">
                <h3 style={{ margin: 0 }}>{capability.title}</h3>
                <span className="badge badge-source">Axis: {AXIS_LABEL[capability.axis]}</span>
              </div>
              <p className="capability-description">{capability.description}</p>

              <div className="capability-indicator-row">
                <div className={`capability-indicator indicator-${capability.trained}`}>
                  <span>Trained</span>
                  <strong>{INDICATOR_LABEL[capability.trained]}</strong>
                </div>
                <div className={`capability-indicator indicator-${capability.eval}`}>
                  <span>Eval</span>
                  <strong>{INDICATOR_LABEL[capability.eval]}</strong>
                </div>
              </div>

              <div className="capability-evidence">
                {capability.evidence.map((entry) => (
                  <p key={`${capability.id}-${entry}`}>
                    <code>{entry}</code>
                  </p>
                ))}
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  )
}
