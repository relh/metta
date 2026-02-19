import type { DashboardResponse } from '@/lib/repo'

export type SortDir = 'asc' | 'desc'
export type TriFilter = 'all' | 'true' | 'false'
export type EpisodeSortKey = 'reward' | 'steps' | 'opponent' | 'team_comp' | 'noop_rate' | 'created_at'
export type TagFilterKey = 'did_align' | 'did_mine' | 'did_scramble' | 'stalled_noop_heavy'

export const TAG_FILTER_KEYS: TagFilterKey[] = ['did_align', 'did_mine', 'did_scramble', 'stalled_noop_heavy']

export const DEFAULT_TAG_FILTERS: Record<TagFilterKey, TriFilter> = {
  did_align: 'all',
  did_mine: 'all',
  did_scramble: 'all',
  stalled_noop_heavy: 'all',
}

export const VALID_SORT_KEYS: EpisodeSortKey[] = ['reward', 'steps', 'opponent', 'team_comp', 'noop_rate', 'created_at']

export function episodeNoopRate(episode: DashboardResponse['episodes'][number]): number {
  const metrics = episode.metrics
  const noop = metrics['action.noop.success'] ?? 0
  const totalSuccess = Object.entries(metrics)
    .filter(([key]) => key.startsWith('action.') && key.endsWith('.success'))
    .reduce((sum, [, value]) => sum + value, 0)
  const failed = metrics['action.failed'] ?? 0
  const total = totalSuccess + failed
  return total > 0 ? noop / total : 0
}

export function filterEpisodes(
  episodes: DashboardResponse['episodes'],
  {
    statusFilter,
    replayOnly,
    tagQuery,
    tagFilters,
  }: {
    statusFilter: 'all' | 'completed' | 'failed'
    replayOnly: boolean
    tagQuery: string
    tagFilters: Record<TagFilterKey, TriFilter>
  }
): DashboardResponse['episodes'] {
  const query = tagQuery.trim().toLowerCase()
  return episodes.filter((episode) => {
    if (statusFilter !== 'all' && episode.status !== statusFilter) {
      return false
    }
    if (replayOnly && !episode.replay_url) {
      return false
    }
    for (const tagKey of TAG_FILTER_KEYS) {
      const filterValue = tagFilters[tagKey]
      if (filterValue !== 'all' && !episode.diagnostic_tags.includes(`${tagKey}=${filterValue}`)) {
        return false
      }
    }
    if (!query) {
      return true
    }
    const canonicalTags = episode.diagnostic_tags.join(' ').toLowerCase()
    const rawTags = Object.entries(episode.raw_tags)
      .map(([key, value]) => `${key}=${value}`)
      .join(' ')
      .toLowerCase()
    return canonicalTags.includes(query) || rawTags.includes(query)
  })
}

export function sortEpisodes(
  episodes: DashboardResponse['episodes'],
  {
    sortKey,
    sortDir,
  }: {
    sortKey: EpisodeSortKey
    sortDir: SortDir
  }
): DashboardResponse['episodes'] {
  return [...episodes].sort((left, right) => {
    let leftValue: number | string
    let rightValue: number | string
    switch (sortKey) {
      case 'reward':
        leftValue = left.reward
        rightValue = right.reward
        break
      case 'steps':
        leftValue = left.steps
        rightValue = right.steps
        break
      case 'opponent':
        leftValue = left.opponent_name
        rightValue = right.opponent_name
        break
      case 'team_comp':
        leftValue = left.team_composition
        rightValue = right.team_composition
        break
      case 'noop_rate':
        leftValue = episodeNoopRate(left)
        rightValue = episodeNoopRate(right)
        break
      case 'created_at':
        leftValue = left.created_at ?? ''
        rightValue = right.created_at ?? ''
        break
      default:
        leftValue = left.reward
        rightValue = right.reward
    }

    if (typeof leftValue === 'string') {
      return sortDir === 'asc'
        ? leftValue.localeCompare(rightValue as string)
        : (rightValue as string).localeCompare(leftValue)
    }
    return sortDir === 'asc'
      ? (leftValue as number) - (rightValue as number)
      : (rightValue as number) - (leftValue as number)
  })
}
