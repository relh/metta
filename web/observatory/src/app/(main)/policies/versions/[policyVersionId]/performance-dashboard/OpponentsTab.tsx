'use client'

import { FC } from 'react'

import { Card } from '@/components/Card'
import type { DashboardResponse } from '@/lib/repo'

import { formatSigned } from './shared'

export const OpponentsTab: FC<{
  data: DashboardResponse
  colorMap: Record<string, string>
}> = ({ data, colorMap }) => {
  const matchup = data.derived.matchup
  const opponentMetrics = data.derived.opponent_metrics
  const episodes = data.episodes
  const completedEpisodes = episodes.filter((e) => e.status === 'completed')

  return (
    <>
      {/* Matchup Diagnosis */}
      {matchup && (
        <Card title="Matchup Diagnosis">
          <p className="text-sm text-foreground">{matchup.reason}</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3 text-xs text-foreground-muted">
            <div className="bg-surface-alt rounded p-2">
              Current avg reward:{' '}
              <span className="font-mono text-foreground">{matchup.current_avg_reward.toFixed(3)}</span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Baseline avg reward:{' '}
              <span className="font-mono text-foreground">
                {matchup.baseline_avg_reward !== null ? matchup.baseline_avg_reward.toFixed(3) : '-'}
              </span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Global delta:{' '}
              <span className="font-mono text-foreground">
                {matchup.global_reward_delta !== null ? formatSigned(matchup.global_reward_delta, 3) : '-'}
              </span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Evidence:{' '}
              <span className={`font-semibold ${matchup.evidence_sufficient ? 'text-green-700' : 'text-yellow-700'}`}>
                {matchup.evidence_sufficient ? 'sufficient' : 'limited'}
              </span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Opponent spread: <span className="font-mono text-foreground">{matchup.opponent_spread.toFixed(3)}</span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Best/Worst opponent:{' '}
              <span className="font-mono text-foreground">
                {(matchup.best_opponent ?? '-') + ' / ' + (matchup.worst_opponent ?? '-')}
              </span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Composition spread:{' '}
              <span className="font-mono text-foreground">{matchup.composition_spread.toFixed(3)}</span>
            </div>
            <div className="bg-surface-alt rounded p-2">
              Best/Worst composition:{' '}
              <span className="font-mono text-foreground">
                {(matchup.best_composition ?? '-') + ' / ' + (matchup.worst_composition ?? '-')}
              </span>
            </div>
          </div>
        </Card>
      )}

      {/* Matchup Slices */}
      {matchup && matchup.opponent_slices.length > 0 && (
        <Card title="Matchup Slices (Current vs Baseline)">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Opponent</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Current Avg</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Baseline Avg
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Delta</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Delta vs Policy
                </th>
              </tr>
            </thead>
            <tbody>
              {matchup.opponent_slices.map((slice) => (
                <tr key={slice.key} className="border-b border-border-subtle hover:bg-surface-alt">
                  <td className="px-3 py-2 font-medium">{slice.key}</td>
                  <td className="px-3 py-2 font-mono">
                    {slice.avg_reward.toFixed(2)} ({slice.count})
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {slice.baseline_avg_reward !== null && slice.baseline_count !== null
                      ? `${slice.baseline_avg_reward.toFixed(2)} (${slice.baseline_count})`
                      : '-'}
                  </td>
                  <td
                    className={`px-3 py-2 font-mono ${
                      slice.delta_vs_baseline !== null
                        ? slice.delta_vs_baseline < -0.2
                          ? 'text-red-600'
                          : slice.delta_vs_baseline > 0.2
                            ? 'text-green-600'
                            : ''
                        : ''
                    }`}
                  >
                    {slice.delta_vs_baseline !== null ? formatSigned(slice.delta_vs_baseline, 2) : '-'}
                  </td>
                  <td className="px-3 py-2 font-mono">{formatSigned(slice.delta_vs_policy, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Composition Slices */}
      {matchup && matchup.composition_slices.length > 0 && (
        <Card title="Composition Slices">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Composition</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Current Avg</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Baseline Avg
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Delta</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Delta vs Policy
                </th>
              </tr>
            </thead>
            <tbody>
              {matchup.composition_slices.map((slice) => (
                <tr key={slice.key} className="border-b border-border-subtle hover:bg-surface-alt">
                  <td className="px-3 py-2 font-mono font-bold">{slice.key}</td>
                  <td className="px-3 py-2 font-mono">
                    {slice.avg_reward.toFixed(2)} ({slice.count})
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {slice.baseline_avg_reward !== null && slice.baseline_count !== null
                      ? `${slice.baseline_avg_reward.toFixed(2)} (${slice.baseline_count})`
                      : '-'}
                  </td>
                  <td
                    className={`px-3 py-2 font-mono ${
                      slice.delta_vs_baseline !== null
                        ? slice.delta_vs_baseline < -0.2
                          ? 'text-red-600'
                          : slice.delta_vs_baseline > 0.2
                            ? 'text-green-600'
                            : ''
                        : ''
                    }`}
                  >
                    {slice.delta_vs_baseline !== null ? formatSigned(slice.delta_vs_baseline, 2) : '-'}
                  </td>
                  <td className="px-3 py-2 font-mono">{formatSigned(slice.delta_vs_policy, 2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* Opponent Breakdown */}
      {Object.keys(opponentMetrics).length > 0 ? (
        <Card title="Opponent Breakdown">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Opponent</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Games</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Avg Reward</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Total Reward
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Win Rate</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Agg</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Def</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Res</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Jnc</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Mob</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(opponentMetrics)
                .sort(([, a], [, b]) => b.avg_reward - a.avg_reward)
                .map(([opp, stats]) => {
                  const oppEps = completedEpisodes.filter((e) => e.opponent_name === opp)
                  const wins = oppEps.filter((e) => e.reward > 0.5).length
                  const winRate = oppEps.length > 0 ? wins / oppEps.length : 0
                  return (
                    <tr key={opp} className="border-b border-border-subtle hover:bg-surface-alt">
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
          <p className="text-sm text-foreground-muted text-center py-8">No opponent data available</p>
        </Card>
      )}
    </>
  )
}
