'use client'

import { FC, useMemo } from 'react'
import { ComposedChart, Bar, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import type { DashboardKpis, DashboardResponse } from '@/lib/repo'

import { AnalysisMarkdown } from './AnalysisMarkdown'

import {
  ANALYSIS_QUIPS,
  KPI_COMPARISON_FIELDS,
  KpiCard,
  type KpiComparisonRow,
  RADAR_KEYS,
  RadarChart,
  formatSigned,
  kpiSeverity,
  opponentKpiValue,
} from './shared'

export const InterReplaySummary: FC<{
  data: DashboardResponse
  showHeader?: boolean
  analysis: string | null
  analysisLoading: boolean
  analysisError: string | null
  showAnalysis: boolean
  analysisDataSources: string[]
  onRunAnalysis: () => void
  onToggleAnalysis: () => void
}> = ({
  data,
  showHeader = true,
  analysis,
  analysisLoading,
  analysisError,
  showAnalysis,
  analysisDataSources,
  onRunAnalysis,
  onToggleAnalysis,
}) => {
  const { policy, episodes, derived } = data
  const kpis = derived.kpis
  const teamComp = derived.team_comp
  const opponentMetrics = derived.opponent_metrics
  const outcome = derived.outcome
  const outcomeRankDelta = outcome?.delta.rank_delta
  const outcomeScoreDelta = outcome?.delta.score_delta
  const completedEpisodes = episodes.filter((e) => e.status === 'completed')
  const failedEpisodes = episodes.filter((e) => e.status === 'failed')

  const quip = useMemo(() => {
    const template = ANALYSIS_QUIPS[Math.floor(Math.random() * ANALYSIS_QUIPS.length)]
    return template({ policy: policy.name })
  }, [policy.name])

  // KPI comparison data (policy value vs per-opponent min/max)
  const kpiComparisonData = useMemo((): KpiComparisonRow[] => {
    const oppEntries = Object.values(opponentMetrics)
    if (oppEntries.length === 0) return []

    return KPI_COMPARISON_FIELDS.map(({ key, label, scale }) => {
      const policyValue = (kpis[key] as number) * scale
      const oppValues = oppEntries.map((opp) => opponentKpiValue(opp.avg_metrics, key, scale, policyValue))
      const min = Math.min(...oppValues)
      const max = Math.max(...oppValues)
      return { label, value: policyValue, min, max, range: max - min }
    })
  }, [kpis, opponentMetrics])

  return (
    <>
      {showHeader && (
        <Card>
          <div className="flex flex-wrap gap-6 text-sm text-foreground-muted">
            <span>
              <strong>{policy.name}</strong> v{policy.version}
            </span>
            {outcome && (
              <span
                className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${
                  outcome.verdict === 'helped'
                    ? 'bg-green-100 text-green-700'
                    : outcome.verdict === 'hurt'
                      ? 'bg-red-100 text-red-700'
                      : 'bg-yellow-100 text-yellow-700'
                }`}
              >
                Outcome: {outcome.verdict.toUpperCase()}
              </span>
            )}
            {policy.rank && <span>Rank: #{policy.rank}</span>}
            {policy.score !== null && <span>Score: {policy.score?.toFixed(3)}</span>}
            {outcomeRankDelta !== null && outcomeRankDelta !== undefined && (
              <span>Rank &Delta;: {formatSigned(outcomeRankDelta, 0)}</span>
            )}
            {outcomeScoreDelta !== null && outcomeScoreDelta !== undefined && (
              <span>Score &Delta;: {formatSigned(outcomeScoreDelta, 3)}</span>
            )}
            {outcome?.baseline && <span>Baseline: v{outcome.baseline.version}</span>}
            <span>Episodes: {episodes.length}</span>
            <span>Completed: {completedEpisodes.length}</span>
            <span>Failed: {failedEpisodes.length}</span>
          </div>
          {outcome && <p className="text-xs text-foreground-muted mt-2">{outcome.reason}</p>}
        </Card>
      )}

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
                  <span className="text-foreground-subtle">{d}</span>
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
                <span className="text-foreground-muted capitalize">
                  {key.replace('profile_', '').replace('_', ' ')}
                </span>
                <span className="font-mono text-foreground">{(kpis[key] ?? 0).toFixed(1)}</span>
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
                  content={(props: { payload?: ReadonlyArray<{ payload: KpiComparisonRow }> }) => {
                    const payload = props.payload
                    if (!payload?.length) return null
                    const d = payload[0].payload as KpiComparisonRow
                    return (
                      <div className="bg-surface border border-border-strong rounded shadow-xl p-2 text-xs text-foreground">
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
            <p className="text-xs text-foreground-muted mt-2 text-center">
              Blue dots = policy value, gray bars = opponent range (min-max)
            </p>
          </Card>
        )}
      </div>

      {/* Team Composition */}
      <Card title="Team Composition">
        {teamComp.length === 0 ? (
          <p className="text-sm text-foreground-muted">No team composition data</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Comp</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Count</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Avg Reward</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Move Eff.</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Junctions</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Resources</th>
              </tr>
            </thead>
            <tbody>
              {teamComp.map((tc) => (
                <tr key={tc.composition} className="border-b border-border-subtle hover:bg-surface-alt">
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

      {/* FUTURE: Role Percentile Cards (aligner/miner/scrambler/scout)
          When Nishad's API ships: rolePercentiles from DashboardDerived
          Per-role: population percentile, P10/P50/P90, team percentile */}

      {/* AI Analysis */}
      <Card title="AI Analysis">
        {!analysis && !analysisLoading && (
          <div className="text-center py-4">
            <button
              onClick={onRunAnalysis}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              Run AI Analysis
            </button>
            <p className="text-xs text-foreground-muted mt-2">
              Uses Claude to analyze policy performance and suggest improvements
            </p>
          </div>
        )}
        {analysisLoading && (
          <div className="py-6 text-center space-y-2">
            <div className="flex justify-center">
              <Spinner />
            </div>
            <p className="text-sm text-foreground-subtle">{quip}</p>
            <p className="text-xs text-foreground-muted">This can take 10-30s.</p>
          </div>
        )}
        {analysisError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700">{analysisError}</div>
        )}
        {analysis && (
          <div>
            <div className="flex flex-wrap items-center gap-3 mb-2">
              <button
                onClick={onToggleAnalysis}
                className="text-sm text-foreground-muted hover:text-foreground underline underline-offset-2 bg-transparent border-0 p-0 cursor-pointer"
              >
                {showAnalysis ? 'Hide' : 'Show'} Analysis
              </button>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-foreground-muted">
                <span>Based on:</span>
                {analysisDataSources.map((src) => (
                  <span key={src} className="inline-block px-1.5 py-0.5 rounded bg-surface-alt text-foreground-subtle">
                    {src.replace('_', ' ')}
                  </span>
                ))}
              </div>
              <button
                onClick={onRunAnalysis}
                className="ml-auto px-3 py-1.5 border border-border-strong rounded text-xs font-medium text-foreground-subtle hover:bg-surface-alt"
              >
                Re-run
              </button>
            </div>
            {showAnalysis && (
              <div className="prose prose-sm max-w-none bg-surface-alt rounded-lg p-4 overflow-x-auto">
                <AnalysisMarkdown text={analysis} data={data} />
              </div>
            )}
          </div>
        )}
      </Card>
    </>
  )
}
