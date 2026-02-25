'use client'

import { FC, useMemo, useState } from 'react'

import type { DashboardResponse, DiagnoseAxis, DiagnoseDoctorNote, DiagnoseManifest } from '../lib/api'

type CapabilityIndicator = 'yes' | 'partial' | 'no' | 'planned'
type CapabilitySource =
  | 'capability_eval'
  | 'cogames_axis'
  | 'cogames_probe'
  | 'cogames_symptom'
  | 'kpi_diagnostic'
  | 'instrumentation'
  | 'behavior_slice'

type CapabilityCard = {
  id: string
  title: string
  description: string
  axis: DiagnoseAxis
  source: CapabilitySource
  score: number
  trained: CapabilityIndicator
  eval: CapabilityIndicator
  evidence: string[]
}

type DiagnoseAxisTreeGroup = {
  axis: DiagnoseAxis
  axisCards: CapabilityCard[]
  probeCards: CapabilityCard[]
  symptomCards: CapabilityCard[]
}

type IndicatorFilter = 'all' | CapabilityIndicator
type SourceFilter = 'all' | CapabilitySource
type CapabilityViewMode = 'tree' | 'grid'

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
    description: 'Disrupt clip opponents and force mistakes.',
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

const CAPABILITY_DEPENDENCY_GRAPH: Record<string, string[]> = {
  coordination: ['mining', 'aligning', 'scouting', 'scrambling'],
  mining: [],
  aligning: [],
  scouting: [],
  scrambling: [],
}

const INDICATOR_LABEL: Record<CapabilityIndicator, string> = {
  yes: 'Yes',
  partial: 'Partial',
  no: 'No',
  planned: 'Planned',
}

const SOURCE_LABEL: Record<CapabilitySource, string> = {
  capability_eval: 'Capability Eval',
  cogames_axis: 'Diagnose Axis',
  cogames_probe: 'Diagnose Probe',
  cogames_symptom: 'Diagnose Symptom',
  kpi_diagnostic: 'KPI Diagnostic',
  instrumentation: 'Instrumentation',
  behavior_slice: 'Behavior Slice',
}

const AXIS_LABEL: Record<DiagnoseAxis, string> = {
  stability: 'Stability',
  efficiency: 'Efficiency',
  control: 'Control',
  social_coordination: 'Social Coordination',
}

const AXIS_ORDER: DiagnoseAxis[] = ['stability', 'efficiency', 'control', 'social_coordination']
const DIAGNOSE_TREE_SOURCES: CapabilitySource[] = ['cogames_axis', 'cogames_probe', 'cogames_symptom']
const SIGNAL_TREE_SOURCES: CapabilitySource[] = ['instrumentation', 'kpi_diagnostic', 'behavior_slice']

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

function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value))
}

function normalizeRange(value: number, min: number, max: number): number {
  if (!Number.isFinite(value) || max <= min) return 0
  return clamp01((value - min) / (max - min))
}

function scoreToIndicator(score: number): CapabilityIndicator {
  if (score >= 0.75) return 'yes'
  if (score >= 0.4) return 'partial'
  return 'no'
}

function slug(value: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
  return normalized.replace(/^-+|-+$/g, '') || 'scenario'
}

function inferAxisFromText(value: string): DiagnoseAxis {
  const text = value.toLowerCase()
  if (
    text.includes('resource') ||
    text.includes('mine') ||
    text.includes('miner') ||
    text.includes('efficiency') ||
    text.includes('retention')
  ) {
    return 'efficiency'
  }
  if (
    text.includes('align') ||
    text.includes('junction') ||
    text.includes('control') ||
    text.includes('scramble') ||
    text.includes('aggression')
  ) {
    return 'control'
  }
  if (
    text.includes('social') ||
    text.includes('coordination') ||
    text.includes('team') ||
    text.includes('pair') ||
    text.includes('self_play')
  ) {
    return 'social_coordination'
  }
  return 'stability'
}

function mechanicEvalScores(data: DashboardResponse): Record<string, number> {
  const kpis = data.derived.kpis
  const diagnostics = asStringArray(kpis.diagnostics).join(' ').toLowerCase()

  const mining = Math.max(
    normalizeRange(numeric(kpis.resource_efficiency_per_step), 0.0, 0.04),
    normalizeRange(numeric(kpis.resource_retention), 0.0, 0.5)
  )

  const aligning = Math.max(
    normalizeRange(numeric(kpis.junction_control_rate), 0.0, 0.4),
    normalizeRange(numeric(kpis.alignment_stability), 0.0, 0.24)
  )

  const scramblingSignals = [
    diagnostics.includes('scramble') || diagnostics.includes('aggressive') ? 0.65 : 0,
    normalizeRange(numeric(kpis.profile_aggressive), 0, 50),
  ]
  const scrambling = Math.max(...scramblingSignals)

  const scouting = Math.max(
    normalizeRange(numeric(kpis.move_efficiency), 0.35, 0.75),
    normalizeRange(numeric(kpis.profile_mobile_scout), 0, 50)
  )

  const coordination = data.derived.outcome?.evidence_sufficient ? 0.6 : 0.2

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
): { indicator: CapabilityIndicator; score: number; evidence: string } | null {
  if (!note) return null
  const score = asArray<NonNullable<DiagnoseDoctorNote['axes']>[number]>(note.axes).find((entry) => entry.axis === axis)
  if (!score) return null

  const normalized = clamp01(numeric(score.normalized_score))
  const indicator = score.confirmed ? 'yes' : normalized >= 0.4 ? 'partial' : 'no'
  const evidence = `axis ${AXIS_LABEL[axis]}=${formatPercent(score.normalized_score)} (confirmed=${String(score.confirmed)})`
  return { indicator, score: normalized, evidence }
}

function probeIndicator(
  note: DiagnoseDoctorNote | null,
  axis: DiagnoseAxis
): { indicator: CapabilityIndicator; score: number; evidence: string } | null {
  if (!note) return null
  const evaluations = asArray<NonNullable<DiagnoseDoctorNote['stage1_probe_evaluations']>[number]>(
    note.stage1_probe_evaluations
  ).filter((entry) => entry.axis === axis)
  if (evaluations.length === 0) return null

  const passed = evaluations.filter((entry) => entry.passed).length
  const score = passed / evaluations.length
  const indicator = passed === evaluations.length ? 'yes' : passed > 0 ? 'partial' : 'no'
  return {
    indicator,
    score,
    evidence: `diagnose probes on ${AXIS_LABEL[axis]}: ${passed}/${evaluations.length} passing`,
  }
}

function buildCapabilityEvalCards(
  data: DashboardResponse,
  note: DiagnoseDoctorNote | null,
  manifest: DiagnoseManifest | null
): CapabilityCard[] {
  const trained = trainedIndicators()
  const evalFromMetrics = mechanicEvalScores(data)

  return CAPABILITY_SPECS.map((spec) => {
    const axisSignal = axisIndicator(note, spec.axis)
    const probeSignal = probeIndicator(note, spec.axis)

    const baseScore = clamp01(evalFromMetrics[spec.id] ?? 0)
    let evalScore = baseScore

    if (axisSignal) {
      evalScore = Math.max(evalScore, axisSignal.score)
    }
    if (probeSignal) {
      // Probe outcomes are direct scenario checks and should override heuristic/base scoring.
      evalScore = probeSignal.score
    }

    let evalIndicator = scoreToIndicator(evalScore)
    if (axisSignal?.indicator === 'yes') {
      evalIndicator = 'yes'
    }
    if (probeSignal) {
      evalIndicator = probeSignal.indicator
    }

    const evidence = [
      `training source: ${spec.trainingSource}`,
      `score: ${formatPercent(evalScore, 0)}`,
      axisSignal?.evidence,
      probeSignal?.evidence,
      manifest?.run_id ? `diagnose run: ${manifest.run_id}` : null,
    ].filter((value): value is string => Boolean(value))

    return {
      id: spec.id,
      title: spec.title,
      description: spec.description,
      axis: spec.axis,
      source: 'capability_eval',
      score: evalScore,
      trained: trained[spec.id] ?? 'planned',
      eval: evalIndicator,
      evidence,
    }
  })
}

function buildKpiDiagnosticCards(data: DashboardResponse): CapabilityCard[] {
  const diagnostics = asStringArray(data.derived.kpis.diagnostics)
  return diagnostics.map((entry) => ({
    id: `kpi-diagnostic-${slug(entry)}`,
    title: `KPI Diagnostic: ${entry}`,
    description: 'State-page diagnostic signal emitted from sampled episodes.',
    axis: inferAxisFromText(entry),
    source: 'kpi_diagnostic',
    score: 0.2,
    trained: 'planned',
    eval: 'no',
    evidence: ['score: 20%', 'triggered by dashboard KPI diagnostic stream'],
  }))
}

function buildInstrumentationCards(data: DashboardResponse): CapabilityCard[] {
  const checks = asArray<NonNullable<NonNullable<DashboardResponse['derived']['instrumentation']>['checks']>[number]>(
    data.derived.instrumentation?.checks
  )
  return checks.map((check) => {
    const coverage = clamp01(numeric(check.coverage))
    const status = String(check.status ?? '').toLowerCase()
    const evalIndicator =
      status === 'pass'
        ? 'yes'
        : status === 'partial'
          ? 'partial'
          : status === 'missing'
            ? 'no'
            : scoreToIndicator(coverage)
    const key = String(check.key ?? 'check')
    return {
      id: `instrumentation-${slug(key)}`,
      title: `Instrumentation: ${key}`,
      description: `Coverage check for ${String(check.kind ?? 'signal')} instrumentation.`,
      axis: inferAxisFromText(`${key} ${String(check.kind ?? '')}`),
      source: 'instrumentation',
      score: coverage,
      trained: 'planned',
      eval: evalIndicator,
      evidence: [
        `score: ${formatPercent(coverage, 0)}`,
        `${String(check.present_count ?? 0)}/${String(check.total_count ?? 0)} coverage`,
        String(check.message ?? '-'),
      ],
    }
  })
}

function buildBehaviorSliceCards(data: DashboardResponse): CapabilityCard[] {
  const counts = new Map<string, number>()
  for (const episode of data.episodes) {
    const seen = new Set<string>()
    for (const tag of asStringArray(episode.behavior_tags)) {
      if (seen.has(tag)) continue
      seen.add(tag)
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
  }

  const episodeCount = data.episodes.length
  const rows = [...counts.entries()].sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
  return rows.slice(0, 64).map(([tag, count]) => {
    const score = episodeCount > 0 ? clamp01(count / episodeCount) : 0
    return {
      id: `behavior-slice-${slug(tag)}`,
      title: `Behavior Slice: ${tag}`,
      description: 'Observed episode-tag slice from curated behavior tags.',
      axis: inferAxisFromText(tag),
      source: 'behavior_slice',
      score,
      trained: 'planned',
      eval: scoreToIndicator(score),
      evidence: [
        `score: ${formatPercent(score, 0)}`,
        `${count}/${episodeCount} sampled episodes`,
        'score tracks coverage, not win quality',
      ],
    }
  })
}

function buildDiagnoseAxisCards(note: DiagnoseDoctorNote | null, manifest: DiagnoseManifest | null): CapabilityCard[] {
  const axisById = new Map(
    asArray<NonNullable<DiagnoseDoctorNote['axes']>[number]>(note?.axes).map(
      (axisScore) => [axisScore.axis, axisScore] as const
    )
  )
  return AXIS_ORDER.map((axis) => {
    const axisScore = axisById.get(axis)
    const hasData = Boolean(axisScore)
    const score = hasData ? clamp01(numeric(axisScore?.normalized_score)) : 0
    const evalIndicator = !hasData ? 'planned' : axisScore?.confirmed ? 'yes' : scoreToIndicator(score)
    return {
      id: `diagnose-axis-${axis}`,
      title: `Diagnose Axis: ${AXIS_LABEL[axis]}`,
      description: 'Canonical Stage-1 axis coverage from cogames diagnose.',
      axis,
      source: 'cogames_axis',
      score,
      trained: 'planned',
      eval: evalIndicator,
      evidence: [
        `score: ${formatPercent(score, 0)}`,
        hasData
          ? `confirmed=${String(axisScore?.confirmed)} raw_score=${String(axisScore?.raw_score ?? '-')}`
          : 'no axis score emitted for selected diagnose run',
        manifest?.run_id ? `diagnose run: ${manifest.run_id}` : 'no diagnose run selected',
      ],
    }
  })
}

function buildDiagnoseProbeCards(note: DiagnoseDoctorNote | null): CapabilityCard[] {
  if (!note) return []
  const catalog = asArray<NonNullable<DiagnoseDoctorNote['stage1_probe_catalog']>[number]>(note.stage1_probe_catalog)
  const evaluations = new Map(
    asArray<NonNullable<DiagnoseDoctorNote['stage1_probe_evaluations']>[number]>(note.stage1_probe_evaluations).map(
      (entry) => [entry.probe_id, entry]
    )
  )
  return catalog.map((probe) => {
    const evaluation = evaluations.get(probe.probe_id)
    const score = evaluation ? (evaluation.passed ? 1 : 0) : 0
    return {
      id: `diagnose-probe-${slug(probe.probe_id)}`,
      title: `Diagnose Probe: ${probe.probe_id}`,
      description: probe.question,
      axis: probe.axis,
      source: 'cogames_probe',
      score,
      trained: 'planned',
      eval: evaluation ? scoreToIndicator(score) : 'planned',
      evidence: [
        `score: ${formatPercent(score, 0)}`,
        `${probe.validation_metric} · ${probe.pass_fail_threshold}`,
        evaluation?.summary ? String(evaluation.summary) : 'probe not evaluated in selected run',
      ],
    }
  })
}

function buildDiagnoseSymptomCards(note: DiagnoseDoctorNote | null): CapabilityCard[] {
  if (!note) return []
  const symptoms = asArray<NonNullable<DiagnoseDoctorNote['symptoms']>[number]>(note.symptoms)
  return symptoms.map((symptom) => {
    const severity = clamp01(numeric(symptom.severity))
    const score = 1 - severity
    return {
      id: `diagnose-symptom-${slug(symptom.symptom_id)}`,
      title: `Diagnose Symptom: ${symptom.symptom_id}`,
      description: String(symptom.likely_cause),
      axis: symptom.axis,
      source: 'cogames_symptom',
      score,
      trained: 'planned',
      eval: scoreToIndicator(score),
      evidence: [
        `score: ${formatPercent(score, 0)} (inverse severity)`,
        `confidence: ${formatPercent(clamp01(numeric(symptom.confidence)), 0)}`,
        `action: ${String(symptom.action)}`,
      ],
    }
  })
}

function buildCapabilityCards(
  data: DashboardResponse,
  note: DiagnoseDoctorNote | null,
  manifest: DiagnoseManifest | null
): CapabilityCard[] {
  const allCards = [
    ...buildCapabilityEvalCards(data, note, manifest),
    ...buildDiagnoseAxisCards(note, manifest),
    ...buildDiagnoseProbeCards(note),
    ...buildDiagnoseSymptomCards(note),
    ...buildKpiDiagnosticCards(data),
    ...buildInstrumentationCards(data),
    ...buildBehaviorSliceCards(data),
  ]

  return allCards.sort((left, right) => {
    if (left.source !== right.source) return SOURCE_LABEL[left.source].localeCompare(SOURCE_LABEL[right.source])
    return left.title.localeCompare(right.title)
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
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [viewMode, setViewMode] = useState<CapabilityViewMode>('tree')

  const capabilities = useMemo(
    () => buildCapabilityCards(data, diagnoseNote, diagnoseManifest),
    [data, diagnoseManifest, diagnoseNote]
  )

  const sourceOptions = useMemo(() => {
    const options = new Set<CapabilitySource>()
    for (const capability of capabilities) {
      options.add(capability.source)
    }
    return [...options].sort((left, right) => SOURCE_LABEL[left].localeCompare(SOURCE_LABEL[right]))
  }, [capabilities])

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase()
    return capabilities.filter((capability) => {
      const queryMatch =
        normalized.length === 0 ||
        [capability.title, capability.description, ...capability.evidence].join(' ').toLowerCase().includes(normalized)
      const trainedMatch = trainedFilter === 'all' || capability.trained === trainedFilter
      const evalMatch = evalFilter === 'all' || capability.eval === evalFilter
      const sourceMatch = sourceFilter === 'all' || capability.source === sourceFilter
      return queryMatch && trainedMatch && evalMatch && sourceMatch
    })
  }, [capabilities, evalFilter, query, sourceFilter, trainedFilter])

  const filteredCapabilityEval = useMemo(
    () => filtered.filter((capability) => capability.source === 'capability_eval'),
    [filtered]
  )

  const filteredDiagnoseByAxis = useMemo(() => {
    return AXIS_ORDER.map((axis) => ({
      axis,
      cards: filtered
        .filter((capability) => capability.axis === axis && DIAGNOSE_TREE_SOURCES.includes(capability.source))
        .sort((left, right) => {
          if (left.source !== right.source) return SOURCE_LABEL[left.source].localeCompare(SOURCE_LABEL[right.source])
          return left.title.localeCompare(right.title)
        }),
    }))
      .filter((group) => group.cards.length > 0)
      .map(
        (group): DiagnoseAxisTreeGroup => ({
          axis: group.axis,
          axisCards: group.cards.filter((capability) => capability.source === 'cogames_axis'),
          probeCards: group.cards.filter((capability) => capability.source === 'cogames_probe'),
          symptomCards: group.cards.filter((capability) => capability.source === 'cogames_symptom'),
        })
      )
  }, [filtered])

  const filteredSignalGroups = useMemo(() => {
    return SIGNAL_TREE_SOURCES.map((source) => ({
      source,
      cards: filtered
        .filter((capability) => capability.source === source)
        .sort((left, right) => left.title.localeCompare(right.title)),
    })).filter((group) => group.cards.length > 0)
  }, [filtered])

  const treeCapabilityById = useMemo(() => {
    return new Map(filteredCapabilityEval.map((capability) => [capability.id, capability] as const))
  }, [filteredCapabilityEval])

  const treeRootIds = useMemo(() => {
    const allIds = new Set(treeCapabilityById.keys())
    if (allIds.size === 0) return []
    const dependencyIds = new Set<string>()
    for (const deps of Object.values(CAPABILITY_DEPENDENCY_GRAPH)) {
      for (const dep of deps) {
        if (allIds.has(dep)) dependencyIds.add(dep)
      }
    }
    const explicitRoots = [...allIds].filter((id) => !dependencyIds.has(id))
    return explicitRoots.length > 0 ? explicitRoots : [...allIds]
  }, [treeCapabilityById])

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

  const averageScore = useMemo(() => {
    if (capabilities.length === 0) return 0
    return capabilities.reduce((total, capability) => total + capability.score, 0) / capabilities.length
  }, [capabilities])

  const renderCapabilityCard = (
    capability: CapabilityCard,
    { treeCard = false, compact = false }: { treeCard?: boolean; compact?: boolean } = {}
  ) => {
    return (
      <article
        key={capability.id}
        className={`card capability-card${treeCard ? ' capability-tree-card' : ''}${compact ? ' capability-card-compact' : ''}`}
      >
        <div className="capability-card-head">
          <h3 style={{ margin: 0 }}>{capability.title}</h3>
          <span className="badge badge-source">
            {SOURCE_LABEL[capability.source]} · {AXIS_LABEL[capability.axis]}
          </span>
        </div>
        <p className="capability-description">{capability.description}</p>

        <div className="capability-indicator-row">
          <div className={`capability-indicator indicator-${capability.eval}`}>
            <span>Eval</span>
            <strong>{INDICATOR_LABEL[capability.eval]}</strong>
          </div>
          <div className={`capability-indicator indicator-${capability.eval}`}>
            <span>Score</span>
            <strong>{formatPercent(capability.score, 0)}</strong>
          </div>
          <div className={`capability-indicator capability-indicator-trained indicator-${capability.trained}`}>
            <span>Trained</span>
            <strong>{INDICATOR_LABEL[capability.trained]}</strong>
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
    )
  }

  const renderCapabilityTreeNode = (nodeId: string) => {
    const capability = treeCapabilityById.get(nodeId)
    if (!capability) return null
    const dependencies = (CAPABILITY_DEPENDENCY_GRAPH[nodeId] ?? []).filter((childId) =>
      treeCapabilityById.has(childId)
    )

    return (
      <li key={nodeId} className="capability-tree-node">
        {renderCapabilityCard(capability, { treeCard: true, compact: true })}
        {dependencies.length > 0 && (
          <ul className="capability-tree-children">
            {dependencies.map((childId) => renderCapabilityTreeNode(childId))}
          </ul>
        )}
      </li>
    )
  }

  const renderCardLeaves = (cards: CapabilityCard[]) => {
    return (
      <ul className="capability-tree-children">
        {cards.map((capability) => (
          <li key={capability.id} className="capability-tree-node">
            {renderCapabilityCard(capability, { treeCard: true, compact: true })}
          </li>
        ))}
      </ul>
    )
  }

  return (
    <div className="grid" style={{ gap: 12 }}>
      <section className="card grid" style={{ gap: 12 }}>
        <div className="dashboard-control-head">
          <div className="dashboard-title-line">
            <h2 style={{ margin: 0 }}>Capability Tree</h2>
            <span className="dashboard-title-subline">
              Canonical diagnosis inventory with dependency view for major skills.
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>
            scenarios: <code>{capabilities.length}</code> · avg score <code>{formatPercent(averageScore, 0)}</code>
          </p>
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
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as SourceFilter)}>
            <option value="all">Source: All</option>
            {sourceOptions.map((source) => (
              <option key={`source-${source}`} value={source}>
                Source: {SOURCE_LABEL[source]}
              </option>
            ))}
          </select>
          <div className="skill-view-toggle">
            <button type="button" onClick={() => setViewMode('tree')} disabled={viewMode === 'tree'}>
              Tree
            </button>
            <button type="button" onClick={() => setViewMode('grid')} disabled={viewMode === 'grid'}>
              Grid
            </button>
          </div>
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

      {viewMode === 'tree' ? (
        <section className="card grid" style={{ gap: 12 }}>
          <p style={{ margin: 0, fontSize: 13, color: '#4b617f' }}>
            Tree view now includes all filtered tiles via related subtrees: core abilities, diagnose evidence, and
            operational signals.
          </p>

          <article className="card grid" style={{ gap: 10 }}>
            <h3 style={{ margin: 0 }}>Core Ability Dependency Subtree</h3>
            <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>
              Root skill depends on child skills; cards include score, training status, and evidence.
            </p>
            {filteredCapabilityEval.length === 0 ? (
              <p style={{ margin: 0 }}>No capability-eval nodes match current filters.</p>
            ) : (
              <ul className="capability-tree">{treeRootIds.map((rootId) => renderCapabilityTreeNode(rootId))}</ul>
            )}
          </article>

          <article className="card grid" style={{ gap: 10 }}>
            <h3 style={{ margin: 0 }}>Diagnose Evidence Subtrees</h3>
            <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>
              Axis-organized tree including diagnose axis, probe, and symptom tiles.
            </p>
            {filteredDiagnoseByAxis.length === 0 ? (
              <p style={{ margin: 0 }}>No diagnose evidence tiles match current filters.</p>
            ) : (
              <ul className="capability-tree capability-tree-forest">
                {filteredDiagnoseByAxis.map((group) => (
                  <li key={group.axis} className="capability-tree-node">
                    <div className="capability-tree-hub capability-tree-hub-axis">
                      <strong>{AXIS_LABEL[group.axis]}</strong>
                      <span>{group.axisCards.length + group.probeCards.length + group.symptomCards.length} tiles</span>
                    </div>
                    <ul className="capability-tree-children">
                      {group.axisCards.map((capability) => (
                        <li key={capability.id} className="capability-tree-node">
                          {renderCapabilityCard(capability, { treeCard: true, compact: true })}
                        </li>
                      ))}
                      {group.probeCards.length > 0 && (
                        <li className="capability-tree-node">
                          <div className="capability-tree-hub capability-tree-hub-group">
                            <strong>Probe Checks</strong>
                            <span>{group.probeCards.length}</span>
                          </div>
                          {renderCardLeaves(group.probeCards)}
                        </li>
                      )}
                      {group.symptomCards.length > 0 && (
                        <li className="capability-tree-node">
                          <div className="capability-tree-hub capability-tree-hub-group">
                            <strong>Symptoms</strong>
                            <span>{group.symptomCards.length}</span>
                          </div>
                          {renderCardLeaves(group.symptomCards)}
                        </li>
                      )}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </article>

          <article className="card grid" style={{ gap: 10 }}>
            <h3 style={{ margin: 0 }}>Operational Signal Subtrees</h3>
            <p style={{ margin: 0, fontSize: 12, color: '#6b7280' }}>
              Source-grouped tree for instrumentation checks, KPI diagnostics, and behavior slices.
            </p>
            {filteredSignalGroups.length === 0 ? (
              <p style={{ margin: 0 }}>No operational signal tiles match current filters.</p>
            ) : (
              <ul className="capability-tree capability-tree-forest">
                {filteredSignalGroups.map((group) => (
                  <li key={group.source} className="capability-tree-node">
                    <div className="capability-tree-hub capability-tree-hub-source">
                      <strong>{SOURCE_LABEL[group.source]}</strong>
                      <span>{group.cards.length} tiles</span>
                    </div>
                    {renderCardLeaves(group.cards)}
                  </li>
                ))}
              </ul>
            )}
          </article>
        </section>
      ) : (
        <section className="capability-grid">
          {filtered.length === 0 ? (
            <article className="card">
              <p style={{ margin: 0 }}>No capabilities match current filters.</p>
            </article>
          ) : (
            filtered.map((capability) => renderCapabilityCard(capability))
          )}
        </section>
      )}
    </div>
  )
}
