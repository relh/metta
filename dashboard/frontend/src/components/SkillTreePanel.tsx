'use client'

import { FC, useEffect, useMemo, useState } from 'react'

import type { DashboardResponse } from '../lib/api'

type SkillTreeMode = 'eval' | 'train'
type SkillNodeStatus = 'demonstrated' | 'tested' | 'observed' | 'mock' | 'missing' | 'planned'
type SkillNodeSource = 'dashboard' | 'cogames-diagnose' | 'training'
type SkillTreeView = 'tree' | 'matrix'
type TreeStatusFilter = 'all' | SkillNodeStatus
type TreeSourceFilter = 'all' | SkillNodeSource

type SkillTreeNode = {
  id: string
  title: string
  description: string
  status: SkillNodeStatus
  source: SkillNodeSource
  evidence?: string[]
  children?: SkillTreeNode[]
}

type CoverageAxis = {
  id: string
  label: string
}

type CoverageCell = {
  axisId: string
  status: SkillNodeStatus
  evidence: string
}

type CoverageRow = {
  id: string
  label: string
  description: string
  source: SkillNodeSource
  cells: CoverageCell[]
}

const STATUS_FILTER_OPTIONS: Array<{ value: TreeStatusFilter; label: string }> = [
  { value: 'all', label: 'All statuses' },
  { value: 'demonstrated', label: 'Demonstrated' },
  { value: 'observed', label: 'Observed' },
  { value: 'tested', label: 'Tested' },
  { value: 'mock', label: 'Mock' },
  { value: 'planned', label: 'Planned' },
  { value: 'missing', label: 'Missing' },
]

const SOURCE_FILTER_OPTIONS: Array<{ value: TreeSourceFilter; label: string }> = [
  { value: 'all', label: 'All sources' },
  { value: 'dashboard', label: 'Dashboard' },
  { value: 'cogames-diagnose', label: 'Cogames Diagnose' },
  { value: 'training', label: 'Training' },
]

const EVAL_AXES: CoverageAxis[] = [
  { id: 'clips_on', label: 'Clips On' },
  { id: 'clips_off', label: 'Clips Off' },
  { id: 'cogs_set', label: 'Cogs Set' },
  { id: 'uneven_teams', label: 'Uneven Teams' },
  { id: 'sparse_resources', label: 'Sparse Resources' },
  { id: 'prevalent_resources', label: 'Prevalent Resources' },
]

const TRAIN_AXES: CoverageAxis[] = [
  { id: 'curriculum_defined', label: 'Curriculum' },
  { id: 'eval_defined', label: 'Eval' },
  { id: 'joins_defined', label: 'Joins' },
  { id: 'variants_clips', label: 'Variants: Clips' },
  { id: 'variants_cogs', label: 'Variants: Cogs' },
  { id: 'variants_teams', label: 'Variants: Teams' },
  { id: 'variants_resources', label: 'Variants: Resources' },
]

const STAGE1_AXES = [
  {
    id: 'stage1.axis.stability',
    title: 'Stage-1 axis: stability',
    description: 'Policy remains stable under pressure, with low collapse/timeout behavior.',
  },
  {
    id: 'stage1.axis.efficiency',
    title: 'Stage-1 axis: efficiency',
    description: 'Policy executes routes/objectives with strong movement and low dead time.',
  },
  {
    id: 'stage1.axis.control',
    title: 'Stage-1 axis: control',
    description: 'Policy captures/retargets control objectives with low wrong-target persistence.',
  },
  {
    id: 'stage1.axis.social_coordination',
    title: 'Stage-1 axis: social coordination',
    description: 'Policy coordinates with teammates under shared constraints and interference.',
  },
] as const

function numeric(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((entry) => String(entry)) : []
}

function includesAny(input: string, tokens: string[]): boolean {
  const lowered = input.toLowerCase()
  return tokens.some((token) => lowered.includes(token))
}

function statusLabel(status: SkillNodeStatus): string {
  if (status === 'demonstrated') return 'Demonstrated'
  if (status === 'observed') return 'Observed'
  if (status === 'tested') return 'Tested'
  if (status === 'mock') return 'Mock'
  if (status === 'planned') return 'Planned'
  return 'Missing'
}

function sourceLabel(source: SkillNodeSource): string {
  if (source === 'dashboard') return 'Dashboard'
  if (source === 'cogames-diagnose') return 'Cogames Diagnose'
  return 'Training'
}

function mechanicStatuses(data: DashboardResponse): Record<string, SkillNodeStatus> {
  const kpis = data.derived?.kpis
  const diagnostics = asStringArray(kpis?.diagnostics).join(' ').toLowerCase()

  const miningSignal = numeric(kpis?.resource_efficiency_per_step) > 0.01 || numeric(kpis?.resource_retention) > 0.1
  const aligningSignal = numeric(kpis?.junction_control_rate) > 0.12 || numeric(kpis?.alignment_stability) > 0.08
  const scramblingSignal =
    includesAny(diagnostics, ['scramble', 'aggressive']) || numeric(kpis?.profile_aggressive) > 25
  const scoutingSignal = numeric(kpis?.move_efficiency) > 0.45 || numeric(kpis?.profile_mobile_scout) > 25
  const coordinationSignal = Boolean(data.derived?.outcome?.evidence_sufficient)

  return {
    mining: miningSignal ? 'demonstrated' : 'tested',
    aligning: aligningSignal ? 'demonstrated' : 'tested',
    scrambling: scramblingSignal ? 'tested' : 'mock',
    scouting: scoutingSignal ? 'demonstrated' : 'tested',
    coordination: coordinationSignal ? 'tested' : 'mock',
  }
}

function evalTree(data: DashboardResponse): SkillTreeNode {
  const kpis = data.derived?.kpis
  const failures = data.derived?.failures
  const diagnostics = asStringArray(kpis?.diagnostics)
  const mechanics = mechanicStatuses(data)

  const diagnoseAxes: SkillTreeNode[] = STAGE1_AXES.map((axis) => {
    if (axis.id.endsWith('stability')) {
      return {
        id: axis.id,
        title: axis.title,
        description: axis.description,
        status: numeric(kpis?.move_efficiency) > 0 ? 'tested' : 'mock',
        source: 'cogames-diagnose',
        evidence: [
          `move_efficiency=${numeric(kpis?.move_efficiency).toFixed(3)}`,
          `freeze_vulnerability=${numeric(kpis?.freeze_vulnerability).toFixed(3)}`,
        ],
      }
    }
    if (axis.id.endsWith('efficiency')) {
      return {
        id: axis.id,
        title: axis.title,
        description: axis.description,
        status: numeric(kpis?.action_success_rate) > 0 ? 'tested' : 'mock',
        source: 'cogames-diagnose',
        evidence: [
          `action_success_rate=${numeric(kpis?.action_success_rate).toFixed(3)}`,
          `resource_efficiency_per_step=${numeric(kpis?.resource_efficiency_per_step).toFixed(3)}`,
        ],
      }
    }
    if (axis.id.endsWith('control')) {
      return {
        id: axis.id,
        title: axis.title,
        description: axis.description,
        status: numeric(kpis?.junction_control_rate) > 0 ? 'tested' : 'mock',
        source: 'cogames-diagnose',
        evidence: [
          `junction_control_rate=${numeric(kpis?.junction_control_rate).toFixed(3)}`,
          `alignment_stability=${numeric(kpis?.alignment_stability).toFixed(3)}`,
        ],
      }
    }
    return {
      id: axis.id,
      title: axis.title,
      description: axis.description,
      status: data.derived?.outcome?.evidence_sufficient ? 'tested' : 'mock',
      source: 'cogames-diagnose',
      evidence: [
        `outcome.verdict=${String(data.derived?.outcome?.verdict ?? 'unknown')}`,
        `outcome.evidence_sufficient=${String(Boolean(data.derived?.outcome?.evidence_sufficient))}`,
      ],
    }
  })

  const dashboardDiagnosticNodes: SkillTreeNode[] =
    diagnostics.length === 0
      ? [
          {
            id: 'eval.dashboard.kpis.none',
            title: 'No KPI diagnostics emitted',
            description: 'No dashboard KPI diagnostics were emitted in current sampled episodes.',
            status: 'tested',
            source: 'dashboard',
            evidence: ['kpi.diagnostics=[]'],
          },
        ]
      : diagnostics.map((entry, index) => ({
          id: `eval.dashboard.kpis.${index}`,
          title: entry,
          description: 'KPI-based dashboard diagnostic.',
          status: 'observed',
          source: 'dashboard',
          evidence: [`diagnostic_index=${index}`],
        }))

  const failureNodes: SkillTreeNode[] = [
    {
      id: 'eval.dashboard.failures.timeout',
      title: 'Timeout failures',
      description: 'Timeout job failures in sampled window.',
      status: numeric(failures?.timeout_failures) > 0 ? 'observed' : 'tested',
      source: 'dashboard',
      evidence: [`count=${numeric(failures?.timeout_failures)}`],
    },
    {
      id: 'eval.dashboard.failures.oom',
      title: 'OOM failures',
      description: 'OOM job failures in sampled window.',
      status: numeric(failures?.oom_failures) > 0 ? 'observed' : 'tested',
      source: 'dashboard',
      evidence: [`count=${numeric(failures?.oom_failures)}`],
    },
    {
      id: 'eval.dashboard.failures.crash',
      title: 'Crash failures',
      description: 'Crash/policy error failures in sampled window.',
      status: numeric(failures?.crash_failures) > 0 ? 'observed' : 'tested',
      source: 'dashboard',
      evidence: [`count=${numeric(failures?.crash_failures)}`],
    },
  ]

  return {
    id: 'eval.root',
    title: 'Eval Skill Tree',
    description: 'Policy skill readiness tree from dashboard evidence plus cogames-diagnose catalogs.',
    status: 'tested',
    source: 'dashboard',
    children: [
      {
        id: 'eval.core',
        title: 'Core mechanics',
        description: 'Core mechanic-level eval readiness.',
        status: 'tested',
        source: 'dashboard',
        children: [
          {
            id: 'eval.core.mining',
            title: 'Mining',
            description: 'Resource extraction/deposit throughput.',
            status: mechanics.mining,
            source: 'dashboard',
            evidence: [
              `resource_efficiency_per_step=${numeric(kpis?.resource_efficiency_per_step).toFixed(3)}`,
              `resource_retention=${numeric(kpis?.resource_retention).toFixed(3)}`,
            ],
          },
          {
            id: 'eval.core.aligning',
            title: 'Aligning',
            description: 'Junction control/retention behavior.',
            status: mechanics.aligning,
            source: 'dashboard',
            evidence: [
              `junction_control_rate=${numeric(kpis?.junction_control_rate).toFixed(3)}`,
              `alignment_stability=${numeric(kpis?.alignment_stability).toFixed(3)}`,
            ],
          },
          {
            id: 'eval.core.scrambling',
            title: 'Scrambling',
            description: 'Enemy disruption behavior.',
            status: mechanics.scrambling,
            source: 'dashboard',
            evidence: [`profile_aggressive=${numeric(kpis?.profile_aggressive).toFixed(1)}`],
          },
          {
            id: 'eval.core.scouting',
            title: 'Scouting',
            description: 'Exploration/mobility behavior.',
            status: mechanics.scouting,
            source: 'dashboard',
            evidence: [
              `move_efficiency=${numeric(kpis?.move_efficiency).toFixed(3)}`,
              `profile_mobile_scout=${numeric(kpis?.profile_mobile_scout).toFixed(1)}`,
            ],
          },
          {
            id: 'eval.core.coordination',
            title: 'Coordination',
            description: 'Cross-role coordination evidence.',
            status: mechanics.coordination,
            source: 'dashboard',
            evidence: [
              `outcome.verdict=${String(data.derived?.outcome?.verdict ?? 'unknown')}`,
              `outcome.evidence_sufficient=${String(Boolean(data.derived?.outcome?.evidence_sufficient))}`,
            ],
          },
        ],
      },
      {
        id: 'eval.diagnose',
        title: 'Cogames diagnose catalog',
        description: 'Diagnose axes and probes represented in tree form.',
        status: 'mock',
        source: 'cogames-diagnose',
        children: [
          {
            id: 'eval.diagnose.axes',
            title: 'Stage-1 axes',
            description: 'Stability, efficiency, control, and social coordination axes.',
            status: 'tested',
            source: 'cogames-diagnose',
            children: diagnoseAxes,
          },
          {
            id: 'eval.diagnose.probes',
            title: 'Probe catalog',
            description: 'Probe-level nodes cataloged for future direct hookup.',
            status: 'mock',
            source: 'cogames-diagnose',
            children: [
              {
                id: 'eval.diagnose.probe.food_under_pressure',
                title: 'Probe: food_under_pressure',
                description: 'Stress stability when high-value resources appear under pressure.',
                status: 'mock',
                source: 'cogames-diagnose',
              },
              {
                id: 'eval.diagnose.probe.junction_light_shift',
                title: 'Probe: junction_light_shift',
                description: 'Assess retarget speed when control priorities shift mid-episode.',
                status: 'mock',
                source: 'cogames-diagnose',
              },
            ],
          },
        ],
      },
      {
        id: 'eval.dashboard',
        title: 'Dashboard diagnostics/signals',
        description: 'Diagnostics currently emitted by dashboard pipelines.',
        status: diagnostics.length > 0 ? 'observed' : 'tested',
        source: 'dashboard',
        children: [
          {
            id: 'eval.dashboard.kpis',
            title: 'KPI diagnostics',
            description: 'Rule-based KPI diagnostics.',
            status: diagnostics.length > 0 ? 'observed' : 'tested',
            source: 'dashboard',
            children: dashboardDiagnosticNodes,
          },
          {
            id: 'eval.dashboard.failures',
            title: 'Failure diagnostics',
            description: 'Failure category diagnostics from sampled window.',
            status:
              numeric(failures?.timeout_failures) + numeric(failures?.oom_failures) + numeric(failures?.crash_failures) > 0
                ? 'observed'
                : 'tested',
            source: 'dashboard',
            children: failureNodes,
          },
        ],
      },
    ],
  }
}

function trainTree(): SkillTreeNode {
  return {
    id: 'train.root',
    title: 'Train Skill Tree',
    description: 'Curriculum and join coverage tree for training readiness.',
    status: 'tested',
    source: 'training',
    children: [
      {
        id: 'train.atomic',
        title: 'Atomic curricula',
        description: 'Per-mechanic curricula coverage.',
        status: 'tested',
        source: 'training',
        children: [
          {
            id: 'train.atomic.miner',
            title: 'Miner curriculum',
            description: 'Dedicated miner helper exists (`cogsguard.miner`).',
            status: 'demonstrated',
            source: 'training',
            evidence: ['recipes/experiment/cogsguard.py::miner'],
          },
          {
            id: 'train.atomic.aligner',
            title: 'Aligner curriculum',
            description: 'Dedicated aligner helper exists (`cogsguard.aligner`).',
            status: 'demonstrated',
            source: 'training',
            evidence: ['recipes/experiment/cogsguard.py::aligner'],
          },
          {
            id: 'train.atomic.scout',
            title: 'Scout curriculum',
            description: 'Dedicated scout helper exists (`cogsguard.scout`).',
            status: 'demonstrated',
            source: 'training',
            evidence: ['recipes/experiment/cogsguard.py::scout'],
          },
          {
            id: 'train.atomic.scrambler',
            title: 'Scrambler curriculum',
            description: 'Dedicated scrambler helper is planned in training-tree rollout.',
            status: 'planned',
            source: 'training',
          },
        ],
      },
      {
        id: 'train.joins',
        title: 'Join curricula',
        description: 'Combinatorial joins and role-switch chains.',
        status: 'planned',
        source: 'training',
        children: [
          {
            id: 'train.joins.scout_plus_miner',
            title: 'Join: scout + miner',
            description: 'Find resources, acquire gear, and execute sustained mining loop.',
            status: 'planned',
            source: 'training',
          },
          {
            id: 'train.joins.mining_plus_aligning',
            title: 'Join: mining + aligning',
            description: 'Balance mining throughput with junction control pressure.',
            status: 'planned',
            source: 'training',
          },
          {
            id: 'train.joins.role_switch',
            title: 'Join: role-switch chains',
            description: 'Longer chains of choose/switch/change role actions.',
            status: 'planned',
            source: 'training',
          },
        ],
      },
    ],
  }
}

function flattenTree(node: SkillTreeNode): SkillTreeNode[] {
  return [node, ...(node.children ?? []).flatMap(flattenTree)]
}

function collectNodeIds(node: SkillTreeNode): Set<string> {
  return new Set(flattenTree(node).map((entry) => entry.id))
}

function findNodeById(node: SkillTreeNode, targetId: string): SkillTreeNode | null {
  if (node.id === targetId) return node
  for (const child of node.children ?? []) {
    const found = findNodeById(child, targetId)
    if (found) return found
  }
  return null
}

function filterTree(node: SkillTreeNode, query: string, status: TreeStatusFilter, source: TreeSourceFilter): SkillTreeNode | null {
  const normalized = query.trim().toLowerCase()
  const qMatch =
    normalized.length === 0 ||
    [node.title, node.description, ...(node.evidence ?? [])].join(' ').toLowerCase().includes(normalized)
  const statusMatch = status === 'all' || node.status === status
  const sourceMatch = source === 'all' || node.source === source
  const selfMatch = qMatch && statusMatch && sourceMatch

  const children = (node.children ?? [])
    .map((child) => filterTree(child, normalized, status, source))
    .filter((child): child is SkillTreeNode => child !== null)

  if (!selfMatch && children.length === 0) return null

  return {
    ...node,
    children,
  }
}

function statusCounts(nodes: SkillTreeNode[]): Record<SkillNodeStatus, number> {
  const counts: Record<SkillNodeStatus, number> = {
    demonstrated: 0,
    observed: 0,
    tested: 0,
    mock: 0,
    planned: 0,
    missing: 0,
  }
  for (const node of nodes) counts[node.status] += 1
  return counts
}

function deriveEvalCoverageRows(data: DashboardResponse): CoverageRow[] {
  const mechanics = mechanicStatuses(data)
  const episodes = Array.isArray(data.episodes) ? data.episodes : []
  const hasUnevenTeams = episodes.some((episode) => {
    const composition = episode.team_composition
    if (typeof composition !== 'string' || !composition.includes('v')) return false
    const [leftRaw, rightRaw] = composition.split('v')
    const left = Number.parseInt(leftRaw ?? '', 10)
    const right = Number.parseInt(rightRaw ?? '', 10)
    return Number.isFinite(left) && Number.isFinite(right) && left !== right
  })

  function row(label: string, status: SkillNodeStatus, source: SkillNodeSource, description: string): CoverageRow {
    return {
      id: `eval.matrix.${label.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`,
      label,
      source,
      description,
      cells: [
        {
          axisId: 'clips_on',
          status: episodes.length > 0 ? status : 'missing',
          evidence: episodes.length > 0 ? 'Episodes sampled.' : 'No episodes sampled.',
        },
        {
          axisId: 'clips_off',
          status: status === 'demonstrated' ? 'tested' : 'mock',
          evidence: 'Clips-off tagging not yet wired in standalone UI.',
        },
        {
          axisId: 'cogs_set',
          status: numeric(data.selection?.sampled_episode_count) > 0 ? 'tested' : 'missing',
          evidence:
            numeric(data.selection?.sampled_episode_count) > 0
              ? `sampled_episode_count=${numeric(data.selection?.sampled_episode_count)}`
              : 'No sampled episodes.',
        },
        {
          axisId: 'uneven_teams',
          status: hasUnevenTeams ? 'observed' : 'mock',
          evidence: hasUnevenTeams ? 'Uneven teams observed in sample.' : 'No uneven teams observed.',
        },
        {
          axisId: 'sparse_resources',
          status: 'mock',
          evidence: 'Sparse-resource tagging hookup pending.',
        },
        {
          axisId: 'prevalent_resources',
          status: 'mock',
          evidence: 'Prevalent-resource tagging hookup pending.',
        },
      ],
    }
  }

  return [
    row('Mining', mechanics.mining, 'dashboard', 'Resource extraction/deposit behavior coverage.'),
    row('Aligning', mechanics.aligning, 'dashboard', 'Junction control behavior coverage.'),
    row('Scrambling', mechanics.scrambling, 'dashboard', 'Enemy disruption behavior coverage.'),
    row('Scouting', mechanics.scouting, 'dashboard', 'Exploration/mobility behavior coverage.'),
    row('Coordination', mechanics.coordination, 'cogames-diagnose', 'Cross-role social behavior coverage.'),
  ]
}

function deriveTrainCoverageRows(): CoverageRow[] {
  function row(
    id: string,
    label: string,
    source: SkillNodeSource,
    description: string,
    values: Partial<Record<string, SkillNodeStatus>>
  ): CoverageRow {
    return {
      id,
      label,
      source,
      description,
      cells: TRAIN_AXES.map((axis) => ({
        axisId: axis.id,
        status: values[axis.id] ?? 'planned',
        evidence: axis.label,
      })),
    }
  }

  return [
    row('train.matrix.miner', 'Miner', 'training', 'Miner curriculum coverage.', {
      curriculum_defined: 'demonstrated',
      eval_defined: 'tested',
    }),
    row('train.matrix.aligner', 'Aligner', 'training', 'Aligner curriculum coverage.', {
      curriculum_defined: 'demonstrated',
      eval_defined: 'tested',
    }),
    row('train.matrix.scout', 'Scout', 'training', 'Scout curriculum coverage.', {
      curriculum_defined: 'demonstrated',
      eval_defined: 'tested',
    }),
    row('train.matrix.scrambler', 'Scrambler', 'training', 'Scrambler curriculum coverage.', {
      curriculum_defined: 'planned',
      eval_defined: 'planned',
    }),
    row('train.matrix.scout_plus_miner', 'Join: Scout + Miner', 'training', 'Join curriculum coverage.', {
      joins_defined: 'planned',
      variants_clips: 'planned',
      variants_cogs: 'planned',
      variants_teams: 'planned',
      variants_resources: 'planned',
    }),
  ]
}

const TreeNodeView: FC<{
  node: SkillTreeNode
  expandedNodeIds: Set<string>
  onToggle: (id: string) => void
  onSelect: (id: string) => void
  selectedNodeId: string | null
}> = ({ node, expandedNodeIds, onToggle, onSelect, selectedNodeId }) => {
  const hasChildren = Boolean(node.children?.length)
  const isExpanded = expandedNodeIds.has(node.id)
  const isSelected = selectedNodeId === node.id

  return (
    <div className="skill-node-wrap">
      <div className={`skill-node ${isSelected ? 'skill-node-selected' : ''}`}>
        <div className="skill-node-head">
          {hasChildren ? (
            <button type="button" onClick={() => onToggle(node.id)} className="skill-toggle" aria-label="Toggle node">
              {isExpanded ? '−' : '+'}
            </button>
          ) : (
            <span className="skill-leaf-dot">•</span>
          )}
          <button type="button" className="skill-title-btn" onClick={() => onSelect(node.id)}>
            {node.title}
          </button>
          <span className={`badge badge-status status-${node.status}`}>{statusLabel(node.status)}</span>
          <span className="badge badge-source">{sourceLabel(node.source)}</span>
        </div>
        <p className="skill-desc">{node.description}</p>
      </div>
      {hasChildren && isExpanded ? (
        <div className="skill-children">
          {node.children!.map((child) => (
            <TreeNodeView
              key={child.id}
              node={child}
              expandedNodeIds={expandedNodeIds}
              onToggle={onToggle}
              onSelect={onSelect}
              selectedNodeId={selectedNodeId}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export const SkillTreePanel: FC<{ mode: SkillTreeMode; data: DashboardResponse }> = ({ mode, data }) => {
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<TreeStatusFilter>('all')
  const [sourceFilter, setSourceFilter] = useState<TreeSourceFilter>('all')
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [view, setView] = useState<SkillTreeView>('tree')
  const [expandedNodeIds, setExpandedNodeIds] = useState<Set<string>>(new Set())

  const root = useMemo(() => (mode === 'eval' ? evalTree(data) : trainTree()), [data, mode])
  const filteredRoot = useMemo(() => filterTree(root, query, statusFilter, sourceFilter), [query, root, sourceFilter, statusFilter])
  const filteredNodes = useMemo(() => (filteredRoot ? flattenTree(filteredRoot) : []), [filteredRoot])
  const allNodes = useMemo(() => flattenTree(root), [root])
  const counts = useMemo(() => statusCounts(filteredNodes), [filteredNodes])
  const totalCounts = useMemo(() => statusCounts(allNodes), [allNodes])
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return root
    return findNodeById(root, selectedNodeId) ?? root
  }, [root, selectedNodeId])
  const missingNodes = useMemo(
    () =>
      allNodes
        .filter((node) => (!node.children || node.children.length === 0) && (node.status === 'mock' || node.status === 'planned'))
        .slice(0, 14),
    [allNodes]
  )

  const axes = mode === 'eval' ? EVAL_AXES : TRAIN_AXES
  const rows = useMemo(() => {
    const baseRows = mode === 'eval' ? deriveEvalCoverageRows(data) : deriveTrainCoverageRows()
    return baseRows.filter((row) => {
      const q = query.trim().toLowerCase()
      const qMatch = q.length === 0 || [row.label, row.description].join(' ').toLowerCase().includes(q)
      const sourceMatch = sourceFilter === 'all' || row.source === sourceFilter
      const statusMatch = statusFilter === 'all' || row.cells.some((cell) => cell.status === statusFilter)
      return qMatch && sourceMatch && statusMatch
    })
  }, [data, mode, query, sourceFilter, statusFilter])

  useEffect(() => {
    setExpandedNodeIds(collectNodeIds(root))
  }, [root])

  useEffect(() => {
    if (!selectedNodeId || !findNodeById(root, selectedNodeId)) {
      setSelectedNodeId(root.id)
    }
  }, [root, selectedNodeId])

  const onToggle = (id: string) => {
    setExpandedNodeIds((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="grid" style={{ gap: 12 }}>
      <section className="card">
        <div className="skill-controls">
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search skill nodes..." />
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as TreeStatusFilter)}>
            {STATUS_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value as TreeSourceFilter)}>
            {SOURCE_FILTER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button type="button" onClick={() => setView('tree')}>
            Dendrogram
          </button>
          <button type="button" onClick={() => setView('matrix')}>
            Coverage matrix
          </button>
          <button type="button" onClick={() => filteredRoot && setExpandedNodeIds(collectNodeIds(filteredRoot))}>
            Expand all
          </button>
          <button type="button" onClick={() => filteredRoot && setExpandedNodeIds(new Set([filteredRoot.id]))}>
            Collapse all
          </button>
        </div>
      </section>

      <section className="card">
        <div className="skill-legend">
          <span className="badge badge-status status-demonstrated">
            Demonstrated {counts.demonstrated}/{totalCounts.demonstrated}
          </span>
          <span className="badge badge-status status-observed">
            Observed {counts.observed}/{totalCounts.observed}
          </span>
          <span className="badge badge-status status-tested">
            Tested {counts.tested}/{totalCounts.tested}
          </span>
          <span className="badge badge-status status-mock">
            Mock {counts.mock}/{totalCounts.mock}
          </span>
          <span className="badge badge-status status-planned">
            Planned {counts.planned}/{totalCounts.planned}
          </span>
          <span className="badge badge-status status-missing">
            Missing {counts.missing}/{totalCounts.missing}
          </span>
        </div>
      </section>

      {view === 'tree' ? (
        <section className="skill-layout">
          <div className="card">
            {filteredRoot ? (
              <TreeNodeView
                node={filteredRoot}
                expandedNodeIds={expandedNodeIds}
                onToggle={onToggle}
                onSelect={setSelectedNodeId}
                selectedNodeId={selectedNodeId}
              />
            ) : (
              <p style={{ margin: 0 }}>No nodes match current filters.</p>
            )}
          </div>

          <div className="grid" style={{ gap: 12 }}>
            <article className="card">
              <p className="panel-label">Selected node</p>
              <h3 style={{ marginTop: 6 }}>{selectedNode.title}</h3>
              <p>{selectedNode.description}</p>
              <div className="skill-legend">
                <span className={`badge badge-status status-${selectedNode.status}`}>{statusLabel(selectedNode.status)}</span>
                <span className="badge badge-source">{sourceLabel(selectedNode.source)}</span>
              </div>
              {selectedNode.evidence && selectedNode.evidence.length > 0 ? (
                <>
                  <h4>Evidence</h4>
                  <ul>
                    {selectedNode.evidence.map((entry) => (
                      <li key={`${selectedNode.id}-${entry}`}>
                        <code>{entry}</code>
                      </li>
                    ))}
                  </ul>
                </>
              ) : null}
            </article>

            <article className="card">
              <p className="panel-label">Missing diagnostics queue</p>
              {missingNodes.length === 0 ? (
                <p style={{ marginBottom: 0 }}>No mock/planned leaves.</p>
              ) : (
                <div className="grid" style={{ gap: 8 }}>
                  {missingNodes.map((node) => (
                    <div key={node.id} className="queue-item">
                      <div className="queue-head">
                        <strong>{node.title}</strong>
                        <span className={`badge badge-status status-${node.status}`}>{statusLabel(node.status)}</span>
                      </div>
                      <p style={{ margin: '6px 0 0' }}>{node.description}</p>
                    </div>
                  ))}
                </div>
              )}
            </article>
          </div>
        </section>
      ) : (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>Coverage matrix</h3>
          <p>Coverage across variants and curriculum/eval dimensions.</p>
          <div style={{ overflowX: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Skill</th>
                  {axes.map((axis) => (
                    <th key={axis.id}>{axis.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <strong>{row.label}</strong>
                      <p style={{ margin: '6px 0 0' }}>{row.description}</p>
                    </td>
                    {axes.map((axis) => {
                      const cell = row.cells.find((entry) => entry.axisId === axis.id)
                      const status = cell?.status ?? 'missing'
                      return (
                        <td key={`${row.id}-${axis.id}`}>
                          <span className={`badge badge-status status-${status}`}>{statusLabel(status)}</span>
                          <p style={{ margin: '6px 0 0' }}>{cell?.evidence ?? 'No data'}</p>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  )
}
