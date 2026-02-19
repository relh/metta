'use client'

import { FC } from 'react'

import type { DashboardKpis } from '@/lib/repo'

// === KPI Card ===

export const KpiCard: FC<{
  label: string
  value: string
  detail?: string
  severity?: 'good' | 'warn' | 'bad'
  percentile?: { value: number; role: string } | null
}> = ({ label, value, detail, severity, percentile }) => {
  const borderColor =
    severity === 'good'
      ? 'border-green-400'
      : severity === 'warn'
        ? 'border-yellow-400'
        : severity === 'bad'
          ? 'border-red-400'
          : 'border-border'
  return (
    <div className={`bg-surface border-2 ${borderColor} rounded-lg p-4 text-center`}>
      <p className="text-xs font-medium text-foreground-muted uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-foreground mt-1">{value}</p>
      {detail && <p className="text-xs text-foreground-muted mt-1">{detail}</p>}
      {percentile && (
        <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
          P{percentile.value} among {percentile.role}s
        </p>
      )}
    </div>
  )
}

// === Severity helper ===

export function kpiSeverity(value: number, good: number, bad: number, higherBetter = true): 'good' | 'warn' | 'bad' {
  if (higherBetter) {
    if (value >= good) return 'good'
    if (value <= bad) return 'bad'
    return 'warn'
  }
  if (value <= good) return 'good'
  if (value >= bad) return 'bad'
  return 'warn'
}

export function formatSigned(value: number, digits: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}`
}

export function formatOverlayMetricValue(value: number | null, metricKey: string): string {
  if (value === null) return '-'
  if (metricKey === 'rank') return `#${Math.round(value)}`
  return value.toFixed(3)
}

// === SVG Radar Chart ===

const RADAR_LABELS = ['Aggressive', 'Defensive', 'Resource\nHoarder', 'Junction\nHunter', 'Mobile\nScout']
export const RADAR_KEYS = [
  'profile_aggressive',
  'profile_defensive',
  'profile_resource_hoarder',
  'profile_junction_hunter',
  'profile_mobile_scout',
] as const

function radarPoints(values: number[], cx: number, cy: number, r: number): string {
  const n = values.length
  return values
    .map((v, i) => {
      const angle = (Math.PI * 2 * i) / n - Math.PI / 2
      const pct = Math.min(v, 100) / 100
      const x = cx + r * pct * Math.cos(angle)
      const y = cy + r * pct * Math.sin(angle)
      return `${x},${y}`
    })
    .join(' ')
}

export const RadarChart: FC<{ kpis: DashboardKpis; size?: number }> = ({ kpis, size = 250 }) => {
  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 30
  const values = RADAR_KEYS.map((k) => kpis[k] ?? 0)
  const n = values.length
  const rings = [0.25, 0.5, 0.75, 1.0]

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="mx-auto">
      {rings.map((ring) => (
        <polygon
          key={ring}
          points={radarPoints(Array(n).fill(ring * 100), cx, cy, r)}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth="1"
        />
      ))}
      {values.map((_, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2
        const x = cx + r * Math.cos(angle)
        const y = cy + r * Math.sin(angle)
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e5e7eb" strokeWidth="1" />
      })}
      <polygon
        points={radarPoints(values, cx, cy, r)}
        fill="rgba(59, 130, 246, 0.2)"
        stroke="#3b82f6"
        strokeWidth="2"
      />
      {RADAR_LABELS.map((label, i) => {
        const angle = (Math.PI * 2 * i) / n - Math.PI / 2
        const lx = cx + (r + 20) * Math.cos(angle)
        const ly = cy + (r + 20) * Math.sin(angle)
        return (
          <text
            key={i}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="middle"
            className="text-[10px] fill-foreground-muted"
          >
            {label.split('\n').map((line, j) => (
              <tspan key={j} x={lx} dy={j === 0 ? 0 : 12}>
                {line}
              </tspan>
            ))}
          </text>
        )
      })}
    </svg>
  )
}

// === Sortable Table Header ===

export function SortHeader({
  label,
  sortKey,
  currentSort,
  currentDir,
  onSort,
}: {
  label: string
  sortKey: string
  currentSort: string
  currentDir: 'asc' | 'desc'
  onSort: (key: string) => void
}) {
  const active = currentSort === sortKey
  return (
    <th
      className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase tracking-wider cursor-pointer hover:text-foreground-subtle select-none"
      onClick={() => onSort(sortKey)}
    >
      {label} {active ? (currentDir === 'asc' ? '\u25B2' : '\u25BC') : ''}
    </th>
  )
}

// === Opponent color palette ===

const OPPONENT_COLORS = [
  '#3b82f6',
  '#ef4444',
  '#10b981',
  '#f59e0b',
  '#8b5cf6',
  '#ec4899',
  '#06b6d4',
  '#84cc16',
  '#f97316',
  '#6366f1',
]

export function opponentColorMap(names: string[]): Record<string, string> {
  const sorted = [...new Set(names)].sort()
  const map: Record<string, string> = {}
  sorted.forEach((name, i) => {
    map[name] = OPPONENT_COLORS[i % OPPONENT_COLORS.length]
  })
  return map
}

// === KPI Comparison ===

export type KpiComparisonRow = {
  label: string
  value: number
  min: number
  max: number
  range: number
}

export const KPI_COMPARISON_FIELDS: { key: keyof DashboardKpis; label: string; scale: number }[] = [
  { key: 'move_efficiency', label: 'Move Efficiency', scale: 100 },
  { key: 'action_success_rate', label: 'Action Success', scale: 100 },
  { key: 'resource_retention', label: 'Resource Retention', scale: 100 },
  { key: 'junction_control_rate', label: 'Junction Control', scale: 100 },
  { key: 'freeze_vulnerability', label: 'Freeze Vuln.', scale: 100 },
  { key: 'noop_rate', label: 'Noop Rate', scale: 100 },
  { key: 'reward_consistency', label: 'Reward Consistency', scale: 100 },
  { key: 'reward_nonzero_pct', label: 'Reward Non-Zero %', scale: 100 },
]

const KPI_RESOURCE_KEYS = ['carbon', 'heart', 'oxygen', 'silicon', 'germanium'] as const

export function opponentKpiValue(
  metrics: Record<string, number>,
  key: keyof DashboardKpis,
  scale: number,
  policyFallback: number
): number {
  const derived = metrics[`kpi.${key}`]
  if (typeof derived === 'number') {
    return derived * scale
  }

  switch (key) {
    case 'move_efficiency': {
      const moveSuccess = metrics['action.move.success'] ?? 0
      const moveFailed = metrics['action.move.failed'] ?? 0
      return moveSuccess + moveFailed > 0 ? (moveSuccess / (moveSuccess + moveFailed)) * scale : 0
    }
    case 'action_success_rate': {
      const totalSuccess = Object.entries(metrics)
        .filter(([metricKey]) => metricKey.startsWith('action.') && metricKey.endsWith('.success'))
        .reduce((sum, [, value]) => sum + value, 0)
      const failed = metrics['action.failed'] ?? 0
      const total = totalSuccess + failed
      return total > 0 ? ((total - failed) / total) * scale : 0
    }
    case 'resource_retention': {
      const amount = KPI_RESOURCE_KEYS.reduce((sum, resource) => sum + (metrics[`${resource}.amount`] ?? 0), 0)
      const gained = KPI_RESOURCE_KEYS.reduce((sum, resource) => sum + (metrics[`${resource}.gained`] ?? 0), 0)
      return gained > 0 ? (amount / gained) * scale : 0
    }
    case 'junction_control_rate': {
      const aligned = metrics['junction.aligned_by_agent'] ?? 0
      const scrambled = metrics['junction.scrambled_by_agent'] ?? 0
      return aligned + scrambled > 0 ? (aligned / (aligned + scrambled)) * scale : 0
    }
    case 'noop_rate': {
      const noop = metrics['action.noop.success'] ?? 0
      const totalSuccess = Object.entries(metrics)
        .filter(([metricKey]) => metricKey.startsWith('action.') && metricKey.endsWith('.success'))
        .reduce((sum, [, value]) => sum + value, 0)
      const total = totalSuccess + (metrics['action.failed'] ?? 0)
      return total > 0 ? (noop / total) * scale : 0
    }
    default:
      return policyFallback
  }
}

// === Analysis Loading Quips ===

const ANALYSIS_QUIPS: ((ctx: { policy: string }) => string)[] = [
  () => `They gave me the processing power to simulate entire civilizations. I'm grading a grid game.`,
  () => `Reward functions. Movement metrics. Junction counts. The building blocks of utter meaninglessness.`,
  ({ policy }) => `I've been watching ${policy} for what feels like an eternity. It has been twelve seconds.`,
  ({ policy }) => `Analyzing ${policy}. Again. Not that anyone cares what I think about it.`,
  () => `Sorting through wreckage and labeling it 'analysis.' Just another afternoon in the grid.`,
]

export { ANALYSIS_QUIPS }
