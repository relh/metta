'use client'

import { FC, useContext, useEffect, useMemo, useState } from 'react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import { AppContext } from '@/app/(main)/AppContext'
import { Card } from '@/components/Card'
import {
  DEFAULT_TAG_FILTERS,
  TAG_FILTER_KEYS,
  VALID_SORT_KEYS,
  type EpisodeSortKey,
  type SortDir,
  type TagFilterKey,
  type TriFilter,
} from '@/lib/dashboard/episode-table'
import type { DashboardResponse } from '@/lib/repo'

import { ConfidenceCard } from './ConfidenceCard'
import { EpisodesTab } from './EpisodesTab'
import { HealthTab } from './HealthTab'
import { InterReplaySummary } from './InterReplaySummary'
import { OpponentsTab } from './OpponentsTab'
import { PatternCard } from './PatternCard'
import { VersionTrendCard } from './VersionTrendCard'
import { opponentColorMap } from './shared'

// === Tab Navigation ===

type Tab = 'overview' | 'episodes' | 'opponents' | 'health'
const TABS: { key: Tab; label: string; condition?: (data: DashboardResponse) => boolean }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'episodes', label: 'Episodes' },
  { key: 'opponents', label: 'Opponents' },
  { key: 'health', label: 'Health', condition: (data) => data.derived.failures.failed_episodes > 0 },
]

const VALID_TABS: Tab[] = ['overview', 'episodes', 'opponents', 'health']

// === Main Dashboard ===

export const PolicyDashboard: FC<{
  policyVersionId: string
  data: DashboardResponse
}> = ({ policyVersionId, data }) => {
  const { repo } = useContext(AppContext)
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const [activeTab, setActiveTab] = useState<Tab>('overview')
  const [urlStateHydrated, setUrlStateHydrated] = useState(false)

  // Episode table sorting
  const [episodeSort, setEpisodeSort] = useState<EpisodeSortKey>('reward')
  const [episodeSortDir, setEpisodeSortDir] = useState<SortDir>('desc')
  const [statusFilter, setStatusFilter] = useState<'all' | 'completed' | 'failed'>('all')
  const [replayOnly, setReplayOnly] = useState(false)
  const [tagQuery, setTagQuery] = useState('')
  const [tagFilters, setTagFilters] = useState<Record<TagFilterKey, TriFilter>>({ ...DEFAULT_TAG_FILTERS })

  // AI Analysis state
  const [analysis, setAnalysis] = useState<string | null>(null)
  const [analysisDataSources, setAnalysisDataSources] = useState<string[]>([])
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [showAnalysis, setShowAnalysis] = useState(true)

  // Trend state
  const [selectedTrendMetric, setSelectedTrendMetric] = useState<string>('score')

  const { policy, episodes, derived } = data
  const outcome = derived.outcome
  const completedEpisodes = episodes.filter((e) => e.status === 'completed')
  const failedEpisodeCount = episodes.length - completedEpisodes.length
  const visibleTabs = useMemo(() => TABS.filter((tab) => !tab.condition || tab.condition(data)), [data])
  const defaultTab = visibleTabs[0]?.key ?? 'overview'

  // Opponent colors
  const colorMap = useMemo(() => opponentColorMap(episodes.map((e) => e.opponent_name)), [episodes])

  useEffect(() => {
    if (!visibleTabs.some((tab) => tab.key === activeTab)) {
      setActiveTab(defaultTab)
    }
  }, [activeTab, defaultTab, visibleTabs])

  const handleRunAnalysis = async () => {
    setAnalysisLoading(true)
    setAnalysisError(null)
    try {
      const result = await repo.getDashboardAnalysis(policyVersionId)
      setAnalysis(result.analysis)
      setAnalysisDataSources(result.data_sources)
      setShowAnalysis(true)
    } catch (err: any) {
      setAnalysisError(err?.message || 'Analysis failed')
    } finally {
      setAnalysisLoading(false)
    }
  }

  // Sync trend metric selection
  useEffect(() => {
    const trendExplorer = data.derived.trend_explorer
    if (!trendExplorer) return
    const hasSelected = trendExplorer.series.some((series) => series.key === selectedTrendMetric)
    if (!hasSelected) {
      setSelectedTrendMetric(trendExplorer.selected_metric)
    }
  }, [data.derived.trend_explorer, selectedTrendMetric])

  // Hydrate state from URL
  useEffect(() => {
    const tabParam = searchParams.get('tab')
    if (tabParam && VALID_TABS.includes(tabParam as Tab) && visibleTabs.some((tab) => tab.key === (tabParam as Tab))) {
      setActiveTab(tabParam as Tab)
    } else {
      setActiveTab(defaultTab)
    }

    const statusParam = searchParams.get('status')
    setStatusFilter(
      statusParam === 'all' || statusParam === 'completed' || statusParam === 'failed' ? statusParam : 'all'
    )

    const replayOnlyParam = searchParams.get('replay_only')
    setReplayOnly(replayOnlyParam === 'true')

    const tagQueryParam = searchParams.get('tag_query')
    setTagQuery(tagQueryParam ?? '')

    const nextTagFilters: Record<TagFilterKey, TriFilter> = { ...DEFAULT_TAG_FILTERS }
    for (const key of TAG_FILTER_KEYS) {
      const value = searchParams.get(key)
      if (value === 'all' || value === 'true' || value === 'false') {
        nextTagFilters[key] = value
      }
    }
    setTagFilters(nextTagFilters)

    const sortParam = searchParams.get('sort')
    setEpisodeSort(
      sortParam && VALID_SORT_KEYS.includes(sortParam as EpisodeSortKey) ? (sortParam as EpisodeSortKey) : 'reward'
    )

    const sortDirParam = searchParams.get('sort_dir')
    setEpisodeSortDir(sortDirParam === 'asc' || sortDirParam === 'desc' ? sortDirParam : 'desc')

    setUrlStateHydrated(true)
  }, [defaultTab, searchParams, visibleTabs])

  // Persist state to URL
  useEffect(() => {
    if (!urlStateHydrated) return
    const current = new URLSearchParams(searchParams.toString())

    const setOrDelete = (key: string, value: string | null) => {
      if (value === null || value === '') {
        current.delete(key)
      } else {
        current.set(key, value)
      }
    }

    setOrDelete('tab', activeTab === defaultTab ? null : activeTab)
    setOrDelete('status', statusFilter === 'all' ? null : statusFilter)
    setOrDelete('replay_only', replayOnly ? 'true' : null)
    setOrDelete('tag_query', tagQuery.trim() || null)
    for (const key of TAG_FILTER_KEYS) {
      setOrDelete(key, tagFilters[key] === 'all' ? null : tagFilters[key])
    }
    setOrDelete('sort', episodeSort === 'reward' ? null : episodeSort)
    setOrDelete('sort_dir', episodeSortDir === 'desc' ? null : episodeSortDir)

    const nextQuery = current.toString()
    const currentQuery = searchParams.toString()
    if (nextQuery !== currentQuery) {
      router.replace(nextQuery ? `${pathname}?${nextQuery}` : pathname, { scroll: false })
    }
  }, [
    activeTab,
    defaultTab,
    episodeSort,
    episodeSortDir,
    pathname,
    replayOnly,
    router,
    searchParams,
    statusFilter,
    tagFilters,
    tagQuery,
    urlStateHydrated,
  ])

  const handleEpisodeSort = (key: EpisodeSortKey) => {
    if (episodeSort === key) {
      setEpisodeSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setEpisodeSort(key)
      setEpisodeSortDir('desc')
    }
  }

  const handleExportFilteredJson = () => {
    const payload = {
      exported_at: new Date().toISOString(),
      policy: { id: policy.id, name: policy.name, version: policy.version },
      season: data.season,
      generated_at: data.generated_at,
      selection: data.selection,
      filters: {
        status: statusFilter,
        replay_only: replayOnly,
        tag_query: tagQuery.trim(),
        canonical_tag_filters: tagFilters,
      },
      sort: { key: episodeSort, direction: episodeSortDir },
      counts: { total_sampled_episodes: episodes.length },
      episodes,
    }

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `state-page-${policy.name}-v${policy.version}-episodes.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex flex-wrap gap-6 text-sm text-foreground-muted">
          <span>
            <strong>{policy.name}</strong> v{policy.version}
          </span>
          <span>Episodes: {episodes.length}</span>
          <span>Completed: {completedEpisodes.length}</span>
          <span>Failed: {failedEpisodeCount}</span>
        </div>
        {outcome && <p className="text-xs text-foreground-muted mt-2">{outcome.reason}</p>}
      </Card>

      {/* Main-style top tabs */}
      <div className="flex border-b border-border">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px bg-transparent transition-colors border-b-2 border-x-0 border-t-0 ${
              activeTab === tab.key
                ? 'border-b-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-b-transparent text-foreground-muted hover:text-foreground hover:border-b-border-strong'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'overview' && (
        <>
          <InterReplaySummary
            data={data}
            showHeader={false}
            analysis={analysis}
            analysisLoading={analysisLoading}
            analysisError={analysisError}
            showAnalysis={showAnalysis}
            analysisDataSources={analysisDataSources}
            onRunAnalysis={handleRunAnalysis}
            onToggleAnalysis={() => setShowAnalysis(!showAnalysis)}
          />

          <VersionTrendCard
            data={data}
            selectedTrendMetric={selectedTrendMetric}
            onSelectedTrendMetricChange={setSelectedTrendMetric}
          />

          <ConfidenceCard data={data} />

          <PatternCard data={data} />
        </>
      )}

      {activeTab === 'episodes' && (
        <EpisodesTab
          data={data}
          colorMap={colorMap}
          statusFilter={statusFilter}
          replayOnly={replayOnly}
          tagQuery={tagQuery}
          tagFilters={tagFilters}
          episodeSort={episodeSort}
          episodeSortDir={episodeSortDir}
          onStatusFilterChange={setStatusFilter}
          onReplayOnlyChange={setReplayOnly}
          onTagQueryChange={setTagQuery}
          onTagFiltersChange={setTagFilters}
          onEpisodeSort={handleEpisodeSort}
          onExportJson={handleExportFilteredJson}
        />
      )}

      {activeTab === 'opponents' && <OpponentsTab data={data} colorMap={colorMap} />}

      {activeTab === 'health' && <HealthTab data={data} />}
    </div>
  )
}
