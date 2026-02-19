'use client'

import { FC, useMemo } from 'react'

import { Card } from '@/components/Card'
import type { DashboardResponse } from '@/lib/repo'

import { formatOverlayMetricValue, formatSigned } from './shared'

export const VersionTrendCard: FC<{
  data: DashboardResponse
  selectedTrendMetric: string
  onSelectedTrendMetricChange: (metric: string) => void
}> = ({ data, selectedTrendMetric, onSelectedTrendMetricChange }) => {
  const trend = data.derived.trend
  const trendExplorer = data.derived.trend_explorer

  const selectedTrendSeries = useMemo(() => {
    if (!trendExplorer || trendExplorer.series.length === 0) return null
    return trendExplorer.series.find((series) => series.key === selectedTrendMetric) ?? trendExplorer.series[0]
  }, [trendExplorer, selectedTrendMetric])

  const selectedTrendOverlay = useMemo(() => {
    if (!trendExplorer || !selectedTrendSeries) return null
    return trendExplorer.metric_overlays.find((overlay) => overlay.key === selectedTrendSeries.key) ?? null
  }, [trendExplorer, selectedTrendSeries])

  const selectedMetricPatternGroups = useMemo(() => {
    if (!trendExplorer || !selectedTrendSeries) return []
    return trendExplorer.submission_patterns.filter((pattern) => pattern.metric_key === selectedTrendSeries.key)
  }, [trendExplorer, selectedTrendSeries])

  if (!trend) return null

  return (
    <Card title="Version Trend">
      {/* Always visible: direction + reason + mini table */}
      <div className="flex flex-wrap gap-4 text-xs text-foreground-muted mb-2">
        <span
          className={`text-sm font-semibold ${
            trend.direction === 'improving'
              ? 'text-green-700'
              : trend.direction === 'declining'
                ? 'text-red-700'
                : 'text-yellow-700'
          }`}
        >
          {trend.direction.toUpperCase()}
        </span>
        <span>
          Score &Delta;:{' '}
          <span className="font-mono">
            {trend.score_delta_from_oldest !== null ? formatSigned(trend.score_delta_from_oldest, 3) : '-'}
          </span>
        </span>
        <span>
          Rank &Delta;:{' '}
          <span className="font-mono">
            {trend.rank_delta_from_oldest !== null ? formatSigned(trend.rank_delta_from_oldest, 0) : '-'}
          </span>
        </span>
        <span>
          Evidence:{' '}
          <span className={trend.evidence_sufficient ? 'text-green-700' : 'text-yellow-700'}>
            {trend.evidence_sufficient ? 'sufficient' : 'limited'}
          </span>
        </span>
      </div>
      <p className="text-sm text-foreground">{trend.reason}</p>

      <div className="overflow-x-auto mt-3">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Version</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Score</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Rank</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Matches</th>
            </tr>
          </thead>
          <tbody>
            {trend.points.map((point) => (
              <tr key={point.id} className="border-b border-border-subtle hover:bg-surface-alt">
                <td className="px-3 py-2 font-mono">v{point.version}</td>
                <td className="px-3 py-2 font-mono">{point.score !== null ? point.score.toFixed(3) : '-'}</td>
                <td className="px-3 py-2 font-mono">{point.rank !== null ? `#${point.rank}` : '-'}</td>
                <td className="px-3 py-2 font-mono">{point.matches}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Collapsible: Trend Explorer */}
      {trendExplorer && selectedTrendSeries && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-foreground-subtle hover:text-foreground">
            Trend Explorer
          </summary>
          <div className="mt-3 border border-border rounded p-3">
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-xs text-foreground-muted">
                Selected metric
                <select
                  value={selectedTrendSeries.key}
                  onChange={(e) => onSelectedTrendMetricChange(e.target.value)}
                  className="ml-2 border border-border-strong bg-surface rounded px-2 py-1 text-xs text-foreground"
                >
                  {trendExplorer.series.map((series) => (
                    <option key={series.key} value={series.key}>
                      {series.label}
                    </option>
                  ))}
                </select>
              </label>
              <span
                className={`text-xs font-semibold ${
                  selectedTrendSeries.direction === 'improving'
                    ? 'text-green-700'
                    : selectedTrendSeries.direction === 'declining'
                      ? 'text-red-700'
                      : selectedTrendSeries.direction === 'mixed'
                        ? 'text-yellow-700'
                        : 'text-foreground-muted'
                }`}
              >
                {selectedTrendSeries.direction.toUpperCase()}
              </span>
            </div>
            <p className="mt-2 text-xs text-foreground-muted">{selectedTrendSeries.reason}</p>

            {selectedTrendOverlay && (
              <div className="mt-3 rounded border border-border p-3 bg-surface-alt">
                <p className="text-xs font-semibold text-foreground-subtle">Team vs Population Overlay</p>
                <p
                  className={`mt-1 text-xs font-semibold ${
                    selectedTrendOverlay.signal === 'outperforming'
                      ? 'text-green-700'
                      : selectedTrendOverlay.signal === 'underperforming'
                        ? 'text-red-700'
                        : selectedTrendOverlay.signal === 'mixed'
                          ? 'text-yellow-700'
                          : 'text-foreground-muted'
                  }`}
                >
                  {selectedTrendOverlay.signal.toUpperCase()}
                </p>
                <p className="mt-1 text-xs text-foreground-muted">{selectedTrendOverlay.reason}</p>
                <div className="overflow-x-auto mt-2">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="px-2 py-1 text-left uppercase text-foreground-muted">Cohort</th>
                        <th className="px-2 py-1 text-left uppercase text-foreground-muted">Count</th>
                        <th className="px-2 py-1 text-left uppercase text-foreground-muted">Mean</th>
                        <th className="px-2 py-1 text-left uppercase text-foreground-muted">P10</th>
                        <th className="px-2 py-1 text-left uppercase text-foreground-muted">P90</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-b border-border-subtle">
                        <td className="px-2 py-1 font-medium">Current</td>
                        <td className="px-2 py-1">1</td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.current_value, selectedTrendSeries.key)}
                        </td>
                        <td className="px-2 py-1 font-mono">-</td>
                        <td className="px-2 py-1 font-mono">-</td>
                      </tr>
                      <tr className="border-b border-border-subtle">
                        <td className="px-2 py-1 font-medium">Team</td>
                        <td className="px-2 py-1">{selectedTrendOverlay.team.count}</td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.team.mean, selectedTrendSeries.key)}
                        </td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.team.p10, selectedTrendSeries.key)}
                        </td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.team.p90, selectedTrendSeries.key)}
                        </td>
                      </tr>
                      <tr>
                        <td className="px-2 py-1 font-medium">Population</td>
                        <td className="px-2 py-1">{selectedTrendOverlay.population.count}</td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.population.mean, selectedTrendSeries.key)}
                        </td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.population.p10, selectedTrendSeries.key)}
                        </td>
                        <td className="px-2 py-1 font-mono">
                          {formatOverlayMetricValue(selectedTrendOverlay.population.p90, selectedTrendSeries.key)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div className="mt-2 flex flex-wrap gap-3 text-xs text-foreground-muted">
                  <span>
                    &Delta; vs team mean:{' '}
                    <span className="font-mono">
                      {selectedTrendOverlay.delta_vs_team_mean === null
                        ? '-'
                        : formatSigned(
                            selectedTrendOverlay.delta_vs_team_mean,
                            selectedTrendSeries.key === 'rank' ? 0 : 3
                          )}
                    </span>
                  </span>
                  <span>
                    &Delta; vs population mean:{' '}
                    <span className="font-mono">
                      {selectedTrendOverlay.delta_vs_population_mean === null
                        ? '-'
                        : formatSigned(
                            selectedTrendOverlay.delta_vs_population_mean,
                            selectedTrendSeries.key === 'rank' ? 0 : 3
                          )}
                    </span>
                  </span>
                </div>
              </div>
            )}

            <div className="overflow-x-auto mt-2">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-2 py-1 text-left uppercase text-foreground-muted">Version</th>
                    <th className="px-2 py-1 text-left uppercase text-foreground-muted">Value</th>
                    <th className="px-2 py-1 text-left uppercase text-foreground-muted">Delta vs prev</th>
                  </tr>
                </thead>
                <tbody>
                  {trendExplorer.version_labels.map((label, idx) => {
                    const value = selectedTrendSeries.values[idx]
                    const delta = selectedTrendSeries.deltas[idx]
                    const valueText =
                      value === null
                        ? '-'
                        : selectedTrendSeries.key === 'rank'
                          ? `#${Math.round(value)}`
                          : value.toFixed(3)
                    const deltaText =
                      delta === null ? '-' : formatSigned(delta, selectedTrendSeries.key === 'rank' ? 0 : 3)
                    return (
                      <tr key={`${label}-${idx}`} className="border-b border-border-subtle">
                        <td className="px-2 py-1 font-mono">{label}</td>
                        <td className="px-2 py-1 font-mono">{valueText}</td>
                        <td className="px-2 py-1 font-mono">{deltaText}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {selectedMetricPatternGroups.length > 0 && (
            <div className="mt-3 rounded border border-indigo-200 bg-indigo-50 p-3">
              <p className="text-xs font-semibold text-indigo-800">Cross-Submission Pattern Groups</p>
              <div className="mt-2 space-y-2">
                {selectedMetricPatternGroups.map((group) => (
                  <div
                    key={`${group.code}-${group.versions.join(',')}`}
                    className="rounded border border-indigo-200 bg-surface p-2"
                  >
                    <p className="text-xs font-semibold text-foreground">
                      {group.title} ({group.count})
                    </p>
                    <p className="text-xs text-foreground-subtle mt-1">{group.evidence}</p>
                    <p className="text-xs text-foreground-subtle mt-1">{group.versions.join(', ')}</p>
                    <p className="text-xs text-foreground mt-1">{group.next_action}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </details>
      )}
    </Card>
  )
}
