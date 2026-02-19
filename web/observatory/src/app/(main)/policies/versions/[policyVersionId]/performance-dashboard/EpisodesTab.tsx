'use client'

import { FC, useMemo } from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from 'recharts'

import { Card } from '@/components/Card'
import {
  DEFAULT_TAG_FILTERS,
  TAG_FILTER_KEYS,
  episodeNoopRate,
  filterEpisodes,
  sortEpisodes,
  type EpisodeSortKey,
  type SortDir,
  type TagFilterKey,
  type TriFilter,
} from '@/lib/dashboard/episode-table'
import type { DashboardResponse } from '@/lib/repo'

import { SortHeader } from './shared'

const TAG_FILTER_LABELS: Record<TagFilterKey, string> = {
  did_align: '`did_align`',
  did_mine: '`did_mine`',
  did_scramble: '`did_scramble`',
  stalled_noop_heavy: '`stalled_noop_heavy`',
}

export const EpisodesTab: FC<{
  data: DashboardResponse
  colorMap: Record<string, string>
  statusFilter: 'all' | 'completed' | 'failed'
  replayOnly: boolean
  tagQuery: string
  tagFilters: Record<TagFilterKey, TriFilter>
  episodeSort: EpisodeSortKey
  episodeSortDir: SortDir
  onStatusFilterChange: (v: 'all' | 'completed' | 'failed') => void
  onReplayOnlyChange: (v: boolean) => void
  onTagQueryChange: (v: string) => void
  onTagFiltersChange: (v: Record<TagFilterKey, TriFilter>) => void
  onEpisodeSort: (key: EpisodeSortKey) => void
  onExportJson: () => void
}> = ({
  data,
  colorMap,
  statusFilter,
  replayOnly,
  tagQuery,
  tagFilters,
  episodeSort,
  episodeSortDir,
  onStatusFilterChange,
  onReplayOnlyChange,
  onTagQueryChange,
  onTagFiltersChange,
  onEpisodeSort,
  onExportJson,
}) => {
  const { episodes } = data
  const kpis = data.derived.kpis

  const filteredEpisodes = useMemo(
    () => filterEpisodes(episodes, { statusFilter, replayOnly, tagQuery, tagFilters }),
    [episodes, statusFilter, replayOnly, tagQuery, tagFilters]
  )

  const sortedEpisodes = useMemo(
    () => sortEpisodes(filteredEpisodes, { sortKey: episodeSort, sortDir: episodeSortDir }),
    [filteredEpisodes, episodeSort, episodeSortDir]
  )

  const filteredCompletedEpisodes = filteredEpisodes.filter((episode) => episode.status === 'completed')

  const rewardScatterData = useMemo(
    () =>
      filteredCompletedEpisodes.map((ep, i) => ({
        index: i,
        reward: ep.reward,
        opponent: ep.opponent_name,
        team: ep.team_composition,
        steps: ep.steps,
        fill: colorMap[ep.opponent_name] ?? '#94a3b8',
      })),
    [filteredCompletedEpisodes, colorMap]
  )

  return (
    <>
      {/* Filters (collapsed by default) */}
      <details>
        <summary className="cursor-pointer text-sm font-medium text-foreground-subtle hover:text-foreground mb-3">
          Filters &amp; Export
        </summary>
        <Card>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            <label className="text-xs text-foreground-muted">
              Status
              <select
                value={statusFilter}
                onChange={(e) => onStatusFilterChange(e.target.value as 'all' | 'completed' | 'failed')}
                className="mt-1 w-full border border-border-strong bg-surface rounded px-2 py-1 text-sm text-foreground"
              >
                <option value="all">all</option>
                <option value="completed">completed</option>
                <option value="failed">failed</option>
              </select>
            </label>
            {TAG_FILTER_KEYS.map((key) => (
              <label key={key} className="text-xs text-foreground-muted">
                {TAG_FILTER_LABELS[key]}
                <select
                  value={tagFilters[key]}
                  onChange={(e) => onTagFiltersChange({ ...tagFilters, [key]: e.target.value as TriFilter })}
                  className="mt-1 w-full border border-border-strong bg-surface rounded px-2 py-1 text-sm text-foreground"
                >
                  <option value="all">all</option>
                  <option value="true">true</option>
                  <option value="false">false</option>
                </select>
              </label>
            ))}
            <label className="text-xs text-foreground-muted">
              Tag text search
              <input
                value={tagQuery}
                onChange={(e) => onTagQueryChange(e.target.value)}
                placeholder="e.g. aggression_bucket=large"
                className="mt-1 w-full border border-border-strong bg-surface rounded px-2 py-1 text-sm text-foreground"
              />
            </label>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="inline-flex items-center gap-2 text-xs text-foreground-subtle">
              <input type="checkbox" checked={replayOnly} onChange={(e) => onReplayOnlyChange(e.target.checked)} />
              replay-only rows
            </label>
            <button
              onClick={() => {
                onStatusFilterChange('all')
                onReplayOnlyChange(false)
                onTagQueryChange('')
                onTagFiltersChange({ ...DEFAULT_TAG_FILTERS })
              }}
              className="px-2 py-1 border border-border-strong rounded text-xs text-foreground-subtle hover:bg-surface-alt"
            >
              Reset filters
            </button>
            <button
              onClick={onExportJson}
              className="px-3 py-1.5 bg-blue-600 text-white rounded text-xs font-medium hover:bg-blue-700"
            >
              Export filtered JSON
            </button>
            <span className="text-xs text-foreground-muted">
              {sortedEpisodes.length}/{episodes.length} rows &bull; order: {data.selection.ordering} &bull; limit:{' '}
              {data.selection.limit}
            </span>
          </div>
        </Card>
      </details>

      {/* Reward Scatter Chart */}
      {filteredCompletedEpisodes.length > 0 && (
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
                content={(props: {
                  payload?: ReadonlyArray<{
                    payload: { opponent: string; reward: number; team: string; steps: number }
                  }>
                }) => {
                  const payload = props.payload
                  if (!payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="bg-surface border border-border-strong rounded shadow-xl p-2 text-xs text-foreground">
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
              <div key={name} className="flex items-center gap-1 text-xs text-foreground-muted">
                <span className="w-3 h-3 rounded-full inline-block" style={{ backgroundColor: color }} />
                {name}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Episode Table */}
      <Card title={`Episodes (${sortedEpisodes.length} filtered / ${episodes.length} sampled)`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <SortHeader
                  label="Created"
                  sortKey="created_at"
                  currentSort={episodeSort}
                  currentDir={episodeSortDir}
                  onSort={onEpisodeSort as (key: string) => void}
                />
                <SortHeader
                  label="Opponent"
                  sortKey="opponent"
                  currentSort={episodeSort}
                  currentDir={episodeSortDir}
                  onSort={onEpisodeSort as (key: string) => void}
                />
                <SortHeader
                  label="Team"
                  sortKey="team_comp"
                  currentSort={episodeSort}
                  currentDir={episodeSortDir}
                  onSort={onEpisodeSort as (key: string) => void}
                />
                <SortHeader
                  label="Reward"
                  sortKey="reward"
                  currentSort={episodeSort}
                  currentDir={episodeSortDir}
                  onSort={onEpisodeSort as (key: string) => void}
                />
                <SortHeader
                  label="Steps"
                  sortKey="steps"
                  currentSort={episodeSort}
                  currentDir={episodeSortDir}
                  onSort={onEpisodeSort as (key: string) => void}
                />
                <SortHeader
                  label="Noop %"
                  sortKey="noop_rate"
                  currentSort={episodeSort}
                  currentDir={episodeSortDir}
                  onSort={onEpisodeSort as (key: string) => void}
                />
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Status</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Replay</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Tags</th>
              </tr>
            </thead>
            <tbody>
              {sortedEpisodes.slice(0, 50).map((ep) => (
                <tr key={ep.episode_id} className="border-b border-border-subtle hover:bg-surface-alt">
                  <td className="px-3 py-2 font-mono text-xs">{ep.created_at ? ep.created_at.slice(0, 19) : '-'}</td>
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
                  <td className="px-3 py-2 font-mono">{(episodeNoopRate(ep) * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${ep.status === 'completed' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}
                    >
                      {ep.status}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {ep.replay_url ? (
                      <a
                        href={ep.replay_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:text-blue-800 text-xs font-medium"
                      >
                        open replay
                      </a>
                    ) : (
                      <span className="text-xs text-foreground-muted">-</span>
                    )}
                  </td>
                  <td className="px-3 py-2 max-w-[340px]">
                    <div className="flex flex-wrap gap-1">
                      {ep.diagnostic_tags.slice(0, 4).map((tag) => (
                        <span
                          key={tag}
                          className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-surface-alt text-foreground-subtle"
                        >
                          {tag}
                        </span>
                      ))}
                      {ep.diagnostic_tags.length > 4 && (
                        <span className="inline-block px-1.5 py-0.5 text-[10px] rounded bg-surface-alt text-foreground-subtle">
                          +{ep.diagnostic_tags.length - 4}
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sortedEpisodes.length > 50 && (
            <p className="text-xs text-foreground-muted mt-2 px-3">
              Showing 50 of {sortedEpisodes.length} filtered rows
            </p>
          )}
        </div>
      </Card>
    </>
  )
}
