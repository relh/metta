'use client'

import { FC, useContext, useMemo, useState } from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Cell,
} from 'recharts'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import { AppContext } from '@/app/(main)/AppContext'
import type { DashboardResponse, DashboardKpis } from '@/lib/repo'

// === Tab Navigation ===

type Tab = 'overview' | 'episodes' | 'opponents'
const TABS: { key: Tab; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'episodes', label: 'Episodes' },
  { key: 'opponents', label: 'Opponents' },
]

// === KPI Card ===

const KpiCard: FC<{ label: string; value: string; detail?: string; severity?: 'good' | 'warn' | 'bad' }> = ({
  label,
  value,
  detail,
  severity,
}) => {
  const borderColor =
    severity === 'good'
      ? 'border-green-400'
      : severity === 'warn'
        ? 'border-yellow-400'
        : severity === 'bad'
          ? 'border-red-400'
          : 'border-gray-200'
  return (
    <div className={`bg-white border-2 ${borderColor} rounded-lg p-4 text-center`}>
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
      {detail && <p className="text-xs text-gray-500 mt-1">{detail}</p>}
    </div>
  )
}

// === SVG Radar Chart ===

const RADAR_LABELS = ['Aggressive', 'Defensive', 'Resource\nHoarder', 'Junction\nHunter', 'Mobile\nScout']
const RADAR_KEYS = [
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

const RadarChart: FC<{ kpis: DashboardKpis; size?: number }> = ({ kpis, size = 250 }) => {
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
            className="text-[10px] fill-gray-600"
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

type SortDir = 'asc' | 'desc'

function SortHeader({
  label,
  sortKey,
  currentSort,
  currentDir,
  onSort,
}: {
  label: string
  sortKey: string
  currentSort: string
  currentDir: SortDir
  onSort: (key: string) => void
}) {
  const active = currentSort === sortKey
  return (
    <th
      className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 select-none"
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

function opponentColorMap(names: string[]): Record<string, string> {
  const sorted = [...new Set(names)].sort()
  const map: Record<string, string> = {}
  sorted.forEach((name, i) => {
    map[name] = OPPONENT_COLORS[i % OPPONENT_COLORS.length]
  })
  return map
}

// === KPI Comparison Chart ===

type KpiComparisonRow = {
  label: string
  value: number
  min: number
  max: number
  range: number
}

const KPI_COMPARISON_FIELDS: { key: keyof DashboardKpis; label: string; scale: number }[] = [
  { key: 'move_efficiency', label: 'Move Efficiency', scale: 100 },
  { key: 'action_success_rate', label: 'Action Success', scale: 100 },
  { key: 'resource_retention', label: 'Resource Retention', scale: 100 },
  { key: 'junction_control_rate', label: 'Junction Control', scale: 100 },
  { key: 'freeze_vulnerability', label: 'Freeze Vuln.', scale: 100 },
  { key: 'noop_rate', label: 'Noop Rate', scale: 100 },
  { key: 'reward_consistency', label: 'Reward Consistency', scale: 100 },
  { key: 'reward_nonzero_pct', label: 'Reward Non-Zero %', scale: 100 },
]

// === Severity helper ===

function kpiSeverity(value: number, good: number, bad: number, higherBetter = true): 'good' | 'warn' | 'bad' {
  if (higherBetter) {
    if (value >= good) return 'good'
    if (value <= bad) return 'bad'
    return 'warn'
  }
  if (value <= good) return 'good'
  if (value >= bad) return 'bad'
  return 'warn'
}

// === Main Dashboard ===

export const PolicyDashboard: FC<{
  policyVersionId: string
  data: DashboardResponse
}> = ({ policyVersionId, data }) => {
  const { repo } = useContext(AppContext)
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [analysis, setAnalysis] = useState<string | null>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [showAnalysis, setShowAnalysis] = useState(true)

  // Episode table sorting
  const [episodeSort, setEpisodeSort] = useState<string>('reward')
  const [episodeSortDir, setEpisodeSortDir] = useState<SortDir>('desc')

  const { policy, episodes, derived } = data
  const kpis = derived.kpis
  const teamComp = derived.team_comp
  const opponentMetrics = derived.opponent_metrics

  const completedEpisodes = episodes.filter((e) => e.status === 'completed')

  // Opponent colors
  const colorMap = useMemo(() => opponentColorMap(episodes.map((e) => e.opponent_name)), [episodes])

  // Reward scatter data
  const rewardScatterData = useMemo(
    () =>
      completedEpisodes.map((ep, i) => ({
        index: i,
        reward: ep.reward,
        opponent: ep.opponent_name,
        team: ep.team_composition,
        steps: ep.steps,
        fill: colorMap[ep.opponent_name] ?? '#94a3b8',
      })),
    [completedEpisodes, colorMap]
  )

  // KPI comparison data (policy value vs per-opponent min/max)
  const kpiComparisonData = useMemo((): KpiComparisonRow[] => {
    const oppEntries = Object.values(opponentMetrics)
    if (oppEntries.length === 0) return []

    return KPI_COMPARISON_FIELDS.map(({ key, label, scale }) => {
      const policyValue = (kpis[key] as number) * scale

      // Compute per-opponent values for this KPI from avg_metrics
      const oppValues: number[] = []
      for (const opp of oppEntries) {
        const m = opp.avg_metrics
        let val = 0
        switch (key) {
          case 'move_efficiency': {
            const ms = m['action.move.success'] ?? 0
            const mf = m['action.move.failed'] ?? 0
            val = ms + mf > 0 ? (ms / (ms + mf)) * scale : 0
            break
          }
          case 'action_success_rate': {
            const totalSuccess = Object.entries(m)
              .filter(([k]) => k.startsWith('action.') && k.endsWith('.success'))
              .reduce((s, [, v]) => s + v, 0)
            const failed = m['action.failed'] ?? 0
            const total = totalSuccess + failed
            val = total > 0 ? ((total - failed) / total) * scale : 0
            break
          }
          case 'resource_retention': {
            const amount = ['carbon', 'heart', 'oxygen', 'silicon', 'germanium'].reduce(
              (s, r) => s + (m[`${r}.amount`] ?? 0),
              0
            )
            const gained = ['carbon', 'heart', 'oxygen', 'silicon', 'germanium'].reduce(
              (s, r) => s + (m[`${r}.gained`] ?? 0),
              0
            )
            val = gained > 0 ? (amount / gained) * scale : 0
            break
          }
          case 'junction_control_rate': {
            const ja = m['junction.aligned_by_agent'] ?? 0
            const js = m['junction.scrambled_by_agent'] ?? 0
            val = ja + js > 0 ? (ja / (ja + js)) * scale : 0
            break
          }
          case 'freeze_vulnerability': {
            // Not directly available per-opponent from avg_metrics without steps
            val = policyValue // fallback
            break
          }
          case 'noop_rate': {
            const noop = m['action.noop.success'] ?? 0
            const totalA = Object.entries(m)
              .filter(([k]) => k.startsWith('action.') && k.endsWith('.success'))
              .reduce((s, [, v]) => s + v, 0)
            const totalAF = totalA + (m['action.failed'] ?? 0)
            val = totalAF > 0 ? (noop / totalAF) * scale : 0
            break
          }
          default:
            val = policyValue
        }
        oppValues.push(val)
      }

      const min = Math.min(...oppValues)
      const max = Math.max(...oppValues)

      return {
        label,
        value: policyValue,
        min,
        max,
        range: max - min,
      }
    })
  }, [kpis, opponentMetrics])

  // Sort episodes
  const handleEpisodeSort = (key: string) => {
    if (episodeSort === key) {
      setEpisodeSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setEpisodeSort(key)
      setEpisodeSortDir('desc')
    }
  }

  const sortedEpisodes = [...episodes].sort((a, b) => {
    let aVal: number | string
    let bVal: number | string
    switch (episodeSort) {
      case 'reward':
        aVal = a.reward
        bVal = b.reward
        break
      case 'steps':
        aVal = a.steps
        bVal = b.steps
        break
      case 'opponent':
        aVal = a.opponent_name
        bVal = b.opponent_name
        break
      case 'team_comp':
        aVal = a.team_composition
        bVal = b.team_composition
        break
      default:
        aVal = a.reward
        bVal = b.reward
    }
    if (typeof aVal === 'string') {
      return episodeSortDir === 'asc' ? aVal.localeCompare(bVal as string) : (bVal as string).localeCompare(aVal)
    }
    return episodeSortDir === 'asc' ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number)
  })

  // Claude analysis handler
  const handleRunAnalysis = async () => {
    setAnalysisLoading(true)
    setAnalysisError(null)
    const summary = {
      policy: {
        name: policy.name,
        version: policy.version,
        rank: policy.rank,
        score: policy.score,
        matches: policy.matches,
      },
      episode_count: episodes.length,
      completed_count: completedEpisodes.length,
      season: data.season,
      kpis: {
        avg_reward: kpis.avg_reward,
        move_efficiency: kpis.move_efficiency,
        action_success_rate: kpis.action_success_rate,
        vibe_change_rate: kpis.vibe_change_rate,
        resource_retention: kpis.resource_retention,
        freeze_vulnerability: kpis.freeze_vulnerability,
        junction_control_rate: kpis.junction_control_rate,
        alignment_stability: kpis.alignment_stability,
        net_alignment_rate: kpis.net_alignment_rate,
        noop_rate: kpis.noop_rate,
        resource_efficiency_per_step: kpis.resource_efficiency_per_step,
        hearts_to_junction_rate: kpis.hearts_to_junction_rate,
        reward_consistency: kpis.reward_consistency,
        reward_nonzero_pct: kpis.reward_nonzero_pct,
      },
      strategy_profile: {
        aggressive: kpis.profile_aggressive,
        defensive: kpis.profile_defensive,
        resource_hoarder: kpis.profile_resource_hoarder,
        junction_hunter: kpis.profile_junction_hunter,
        mobile_scout: kpis.profile_mobile_scout,
      },
      diagnostics: kpis.diagnostics,
      team_comp: Object.fromEntries(
        teamComp.map((tc) => [tc.composition, { count: tc.count, avg_reward: tc.avg_reward }])
      ),
      opponents: Object.fromEntries(
        Object.entries(opponentMetrics).map(([opp, stats]) => [
          opp,
          { count: stats.count, avg_reward: stats.avg_reward, strategy_profile: stats.strategy_profile },
        ])
      ),
    }
    try {
      const result = await repo.getDashboardAnalysis(policyVersionId, summary)
      setAnalysis(result.analysis)
    } catch (err: any) {
      setAnalysisError(err.message || 'Analysis failed')
    } finally {
      setAnalysisLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header info */}
      <Card>
        <div className="flex flex-wrap gap-6 text-sm text-gray-600">
          <span>
            <strong>{policy.name}</strong> v{policy.version}
          </span>
          {policy.rank && <span>Rank: #{policy.rank}</span>}
          {policy.score !== null && <span>Score: {policy.score?.toFixed(3)}</span>}
          <span>Episodes: {episodes.length}</span>
          <span>Completed: {completedEpisodes.length}</span>
        </div>
      </Card>

      {/* Tab Navigation */}
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.key
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* === Overview Tab === */}
      {activeTab === 'overview' && (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KpiCard
              label="Avg Reward"
              value={kpis.avg_reward.toFixed(2)}
              severity={kpiSeverity(kpis.avg_reward, 2.0, 0.5)}
            />
            <KpiCard
              label="Move Efficiency"
              value={`${(kpis.move_efficiency * 100).toFixed(0)}%`}
              severity={kpiSeverity(kpis.move_efficiency, 0.8, 0.5)}
            />
            <KpiCard
              label="Action Success"
              value={`${(kpis.action_success_rate * 100).toFixed(0)}%`}
              severity={kpiSeverity(kpis.action_success_rate, 0.9, 0.7)}
            />
            <KpiCard
              label="Resource Retention"
              value={`${(kpis.resource_retention * 100).toFixed(0)}%`}
              severity={kpiSeverity(kpis.resource_retention, 0.5, 0.2)}
            />
            <KpiCard
              label="Freeze Vuln."
              value={`${(kpis.freeze_vulnerability * 100).toFixed(1)}%`}
              severity={kpiSeverity(kpis.freeze_vulnerability, 0.05, 0.15, false)}
            />
            <KpiCard
              label="Junction Control"
              value={`${(kpis.junction_control_rate * 100).toFixed(0)}%`}
              severity={kpiSeverity(kpis.junction_control_rate, 0.6, 0.2)}
            />
            <KpiCard
              label="Noop Rate"
              value={`${(kpis.noop_rate * 100).toFixed(1)}%`}
              severity={kpiSeverity(kpis.noop_rate, 0.1, 0.25, false)}
            />
            <KpiCard
              label="Reward Consistency"
              value={`${(kpis.reward_consistency * 100).toFixed(0)}%`}
              severity={kpiSeverity(kpis.reward_consistency, 0.6, 0.2)}
            />
          </div>

          {/* Diagnostics */}
          {kpis.diagnostics.length > 0 && (
            <Card title="Diagnostics">
              <ul className="space-y-2">
                {kpis.diagnostics.map((d, i) => {
                  const isWarning = d.includes('High') || d.includes('Declining') || d.includes('Over-reliance')
                  return (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span
                        className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${isWarning ? 'bg-yellow-400' : 'bg-blue-400'}`}
                      />
                      <span className="text-gray-700">{d}</span>
                    </li>
                  )
                })}
              </ul>
            </Card>
          )}

          {/* Strategy Profile + KPI Comparison side by side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card title="Strategy Profile">
              <RadarChart kpis={kpis} size={250} />
              <div className="grid grid-cols-2 gap-2 mt-4 text-sm">
                {RADAR_KEYS.map((key) => (
                  <div key={key} className="flex justify-between px-2">
                    <span className="text-gray-600 capitalize">{key.replace('profile_', '').replace('_', ' ')}</span>
                    <span className="font-mono text-gray-900">{(kpis[key] ?? 0).toFixed(1)}</span>
                  </div>
                ))}
              </div>
            </Card>

            {kpiComparisonData.length > 0 && (
              <Card title="KPI Comparison (vs Opponents)">
                <ResponsiveContainer width="100%" height={KPI_COMPARISON_FIELDS.length * 36 + 40}>
                  <ComposedChart
                    layout="vertical"
                    data={kpiComparisonData}
                    margin={{ top: 5, right: 20, bottom: 5, left: 100 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} />
                    <YAxis type="category" dataKey="label" tick={{ fontSize: 12 }} width={95} />
                    <Tooltip
                      content={({ payload }: { payload?: ReadonlyArray<{ payload: KpiComparisonRow }> }) => {
                        if (!payload?.length) return null
                        const d = payload[0].payload
                        return (
                          <div className="bg-white border border-gray-200 rounded shadow-lg p-2 text-xs">
                            <p className="font-medium">{d.label}</p>
                            <p>Policy: {d.value.toFixed(1)}%</p>
                            <p>
                              Opponent range: {d.min.toFixed(1)}% - {d.max.toFixed(1)}%
                            </p>
                          </div>
                        )
                      }}
                    />
                    <Bar dataKey="range" stackId="range" fill="#e5e7eb" barSize={8} radius={4}>
                      {kpiComparisonData.map((_, i) => (
                        <Cell key={i} />
                      ))}
                    </Bar>
                    <Scatter dataKey="value" fill="#3b82f6" r={6} />
                  </ComposedChart>
                </ResponsiveContainer>
                <p className="text-xs text-gray-500 mt-2 text-center">
                  Blue dots = policy value, gray bars = opponent range (min-max)
                </p>
              </Card>
            )}
          </div>

          {/* Team Composition */}
          <Card title="Team Composition">
            {teamComp.length === 0 ? (
              <p className="text-sm text-gray-500">No team composition data</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Comp</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Count</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Avg Reward</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Move Eff.</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Junctions</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Resources</th>
                  </tr>
                </thead>
                <tbody>
                  {teamComp.map((tc) => (
                    <tr key={tc.composition} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="px-3 py-2 font-mono font-bold">{tc.composition}</td>
                      <td className="px-3 py-2">{tc.count}</td>
                      <td className="px-3 py-2 font-mono">{tc.avg_reward.toFixed(2)}</td>
                      <td className="px-3 py-2 font-mono">{(tc.avg_move_efficiency * 100).toFixed(0)}%</td>
                      <td className="px-3 py-2 font-mono">{tc.avg_junction_aligned.toFixed(1)}</td>
                      <td className="px-3 py-2 font-mono">{tc.avg_resource_gained.toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          {/* Claude Analysis */}
          <Card title="AI Analysis">
            {!analysis && !analysisLoading && (
              <div className="text-center py-4">
                <button
                  onClick={handleRunAnalysis}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
                >
                  Run AI Analysis
                </button>
                <p className="text-xs text-gray-500 mt-2">
                  Uses Claude to analyze policy performance and suggest improvements (10-30s)
                </p>
              </div>
            )}
            {analysisLoading && (
              <div className="flex items-center justify-center gap-2 py-8">
                <Spinner />
                <span className="text-sm text-gray-500">Running AI analysis...</span>
              </div>
            )}
            {analysisError && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">{analysisError}</div>
            )}
            {analysis && (
              <div>
                <button
                  onClick={() => setShowAnalysis(!showAnalysis)}
                  className="text-sm text-blue-600 hover:text-blue-800 mb-2"
                >
                  {showAnalysis ? 'Hide' : 'Show'} Analysis
                </button>
                {showAnalysis && (
                  <pre className="whitespace-pre-wrap text-sm text-gray-800 leading-relaxed font-sans bg-gray-50 rounded-lg p-4 overflow-x-auto">
                    {analysis}
                  </pre>
                )}
              </div>
            )}
          </Card>
        </>
      )}

      {/* === Episodes Tab === */}
      {activeTab === 'episodes' && (
        <>
          {/* Reward Scatter Chart */}
          {completedEpisodes.length > 0 && (
            <Card title="Reward Over Time">
              <ResponsiveContainer width="100%" height={300}>
                <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="number"
                    dataKey="index"
                    name="Episode"
                    label={{ value: 'Episode', position: 'bottom', offset: 0 }}
                  />
                  <YAxis type="number" dataKey="reward" name="Reward" />
                  <ReferenceLine
                    y={kpis.avg_reward}
                    stroke="#f59e0b"
                    strokeDasharray="5 5"
                    label={{
                      value: `avg ${kpis.avg_reward.toFixed(2)}`,
                      position: 'right',
                      fill: '#f59e0b',
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    content={({
                      payload,
                    }: {
                      payload?: ReadonlyArray<{ payload: (typeof rewardScatterData)[number] }>
                    }) => {
                      if (!payload?.length) return null
                      const d = payload[0].payload
                      return (
                        <div className="bg-white border border-gray-200 rounded shadow-lg p-2 text-xs">
                          <p className="font-medium">{d.opponent}</p>
                          <p>Reward: {d.reward.toFixed(3)}</p>
                          <p>Team: {d.team}</p>
                          <p>Steps: {d.steps}</p>
                        </div>
                      )
                    }}
                  />
                  <Scatter data={rewardScatterData} shape="circle">
                    {rewardScatterData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
              {/* Legend */}
              <div className="flex flex-wrap gap-3 mt-2 px-2">
                {Object.entries(colorMap).map(([name, color]) => (
                  <div key={name} className="flex items-center gap-1 text-xs text-gray-600">
                    <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: color }} />
                    {name}
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Episode Table */}
          <Card title={`Episodes (${episodes.length})`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <SortHeader
                      label="Opponent"
                      sortKey="opponent"
                      currentSort={episodeSort}
                      currentDir={episodeSortDir}
                      onSort={handleEpisodeSort}
                    />
                    <SortHeader
                      label="Team"
                      sortKey="team_comp"
                      currentSort={episodeSort}
                      currentDir={episodeSortDir}
                      onSort={handleEpisodeSort}
                    />
                    <SortHeader
                      label="Reward"
                      sortKey="reward"
                      currentSort={episodeSort}
                      currentDir={episodeSortDir}
                      onSort={handleEpisodeSort}
                    />
                    <SortHeader
                      label="Steps"
                      sortKey="steps"
                      currentSort={episodeSort}
                      currentDir={episodeSortDir}
                      onSort={handleEpisodeSort}
                    />
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedEpisodes.slice(0, 50).map((ep) => (
                    <tr key={ep.episode_id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="px-3 py-2">
                        <span
                          className="inline-block w-2 h-2 rounded-full mr-2"
                          style={{ backgroundColor: colorMap[ep.opponent_name] ?? '#94a3b8' }}
                        />
                        {ep.opponent_name} v{ep.opponent_version}
                      </td>
                      <td className="px-3 py-2 font-mono">{ep.team_composition}</td>
                      <td
                        className={`px-3 py-2 font-mono ${ep.reward < 0.5 ? 'text-red-600' : ep.reward > 2.0 ? 'text-green-600' : ''}`}
                      >
                        {ep.reward.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 font-mono">{ep.steps}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${ep.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}
                        >
                          {ep.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {episodes.length > 50 && (
                <p className="text-xs text-gray-500 mt-2 px-3">Showing 50 of {episodes.length} episodes</p>
              )}
            </div>
          </Card>
        </>
      )}

      {/* === Opponents Tab === */}
      {activeTab === 'opponents' && (
        <>
          {Object.keys(opponentMetrics).length > 0 ? (
            <Card title="Opponent Breakdown">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Opponent</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Games</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Avg Reward</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Total Reward</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Win Rate</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Agg</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Def</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Res</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Jnc</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Mob</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(opponentMetrics)
                    .sort(([, a], [, b]) => b.avg_reward - a.avg_reward)
                    .map(([opp, stats]) => {
                      // Compute win rate from episodes
                      const oppEps = completedEpisodes.filter((e) => e.opponent_name === opp)
                      const wins = oppEps.filter((e) => e.reward > 0.5).length
                      const winRate = oppEps.length > 0 ? wins / oppEps.length : 0
                      return (
                        <tr key={opp} className="border-b border-gray-100 hover:bg-gray-50">
                          <td className="px-3 py-2 font-medium">
                            <span
                              className="inline-block w-2 h-2 rounded-full mr-2"
                              style={{ backgroundColor: colorMap[opp] ?? '#94a3b8' }}
                            />
                            {opp}
                          </td>
                          <td className="px-3 py-2">{stats.count}</td>
                          <td
                            className={`px-3 py-2 font-mono ${stats.avg_reward < 0.5 ? 'text-red-600' : stats.avg_reward > 2.0 ? 'text-green-600' : ''}`}
                          >
                            {stats.avg_reward.toFixed(2)}
                          </td>
                          <td className="px-3 py-2 font-mono">{stats.total_reward.toFixed(2)}</td>
                          <td
                            className={`px-3 py-2 font-mono ${winRate < 0.4 ? 'text-red-600' : winRate > 0.6 ? 'text-green-600' : ''}`}
                          >
                            {(winRate * 100).toFixed(0)}%
                          </td>
                          <td className="px-3 py-2 font-mono text-xs">
                            {(stats.strategy_profile.aggressive ?? 0).toFixed(0)}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs">
                            {(stats.strategy_profile.defensive ?? 0).toFixed(0)}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs">
                            {(stats.strategy_profile.resource_hoarder ?? 0).toFixed(0)}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs">
                            {(stats.strategy_profile.junction_hunter ?? 0).toFixed(0)}
                          </td>
                          <td className="px-3 py-2 font-mono text-xs">
                            {(stats.strategy_profile.mobile_scout ?? 0).toFixed(0)}
                          </td>
                        </tr>
                      )
                    })}
                </tbody>
              </table>
            </Card>
          ) : (
            <Card>
              <p className="text-sm text-gray-500 text-center py-8">No opponent data available</p>
            </Card>
          )}
        </>
      )}
    </div>
  )
}
