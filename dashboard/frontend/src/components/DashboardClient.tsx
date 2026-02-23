'use client'

import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  DASHBOARD_API_BASE_URL,
  type DashboardActionSummary,
  type DashboardAnalysisResponse,
  type DashboardConfidenceSummary,
  type DashboardEpisode,
  type DashboardFailures,
  type DashboardInstrumentationSummary,
  type DashboardMatchupSlice,
  type DashboardMatchupSummary,
  type DashboardOrchestrationSummary,
  type DashboardPatternSummary,
  type DashboardResponse,
  type DashboardRolePercentilesResponse,
  type DashboardStatsInventorySummary,
  type DashboardTeamCompStats,
  type DashboardTrendExplorerSummary,
  type DashboardTrendPoint,
  type DashboardTrendSummary,
  type DashboardUnsupportedSummary,
  type DiagnoseDoctorNote,
  type DiagnoseManifest,
  type DiagnoseRunSummary,
  fetchDiagnoseDoctorNote,
  fetchDiagnoseManifest,
  fetchDiagnoseRuns,
  fetchDashboardAnalysis,
  fetchDashboardData,
  fetchDashboardDefaultPolicyVersion,
  fetchDashboardRolePercentiles,
} from '../lib/api'
import { AnalysisLoadingQuips, AnalysisRichText } from './AnalysisRichText'
import { CogamesDiagnosePanel } from './CogamesDiagnosePanel'
import { RolePercentilesPanel } from './RolePercentilesPanel'
import { SkillTreePanel } from './SkillTreePanel'

type DashboardTab =
  | 'overview'
  | 'episodes'
  | 'opponents'
  | 'health'
  | 'roles'
  | 'capabilities'
  | 'cogames_diagnose'
  | 'analysis'

type EpisodeStatusFilter = 'all' | 'completed' | 'failed'
type EpisodeSortKey = 'created_at' | 'opponent' | 'team' | 'reward' | 'steps' | 'noop_rate'
type SortDir = 'asc' | 'desc'

const DASHBOARD_TABS: DashboardTab[] = [
  'overview',
  'capabilities',
  'roles',
  'opponents',
  'episodes',
  'health',
  'cogames_diagnose',
  'analysis',
]

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

const DASHBOARD_FEEDBACK_ISSUE_URL = 'https://github.com/Metta-AI/metta/issues/new'

const SORT_HEADER_BUTTON_STYLE: CSSProperties = {
  background: 'transparent',
  border: 0,
  padding: 0,
  color: 'inherit',
  fontSize: 12,
  fontWeight: 600,
}

type OpponentSummaryRow = {
  opponent: string
  count: number
  completed: number
  avgReward: number | null
  totalReward: number | null
  winRate: number | null
  bestProfile: string | null
  strategyProfile: Record<string, number> | null
  source: 'derived' | 'episodes'
}

function parseDashboardTab(value: string | null): DashboardTab | null {
  if (!value) return null
  const normalized = value.trim().toLowerCase()
  const canonical =
    normalized === 'ai_analysis' || normalized === 'ai-analysis' || normalized === 'aianalysis'
      ? 'analysis'
      : normalized
  return DASHBOARD_TABS.find((tab) => tab === canonical) ?? null
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return value
}

function toFiniteNumberOrZero(value: unknown): number {
  return toFiniteNumber(value) ?? 0
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((entry) => String(entry))
}

function formatSigned(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}`
}

function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return `${(value * 100).toFixed(digits)}%`
}

function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return value.toFixed(digits)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function manifestTimestamp(manifest: DiagnoseManifest | null | undefined): number {
  if (!manifest?.created_at) return Number.NEGATIVE_INFINITY
  const timestamp = Date.parse(manifest.created_at)
  return Number.isFinite(timestamp) ? timestamp : Number.NEGATIVE_INFINITY
}

function runLikelyMatchesPolicy(run: DiagnoseRunSummary, policy: DashboardResponse['policy']): boolean {
  if (!run.manifest) return false
  const policyVersionId = String(policy.id).toLowerCase()
  const policyName = String(policy.name).toLowerCase()
  const policyVersion = String(policy.version)
  const haystack = [run.manifest.policy, run.manifest.command, run.manifest.run_id].join(' ').toLowerCase()
  return (
    haystack.includes(policyVersionId) ||
    haystack.includes(`${policyName}:v${policyVersion}`) ||
    haystack.includes(`${policyName} v${policyVersion}`) ||
    haystack.includes(policyName)
  )
}

function metricNumber(episode: DashboardEpisode, key: string): number {
  const metrics = episode.metrics
  if (!metrics || typeof metrics !== 'object' || Array.isArray(metrics)) return 0
  return toFiniteNumberOrZero((metrics as Record<string, unknown>)[key])
}

function episodeNoopRate(episode: DashboardEpisode): number {
  const noop = metricNumber(episode, 'action.noop.success')
  const failed = metricNumber(episode, 'action.failed')
  const metrics = episode.metrics
  if (!metrics || typeof metrics !== 'object' || Array.isArray(metrics)) return 0

  let successTotal = 0
  for (const [key, value] of Object.entries(metrics)) {
    if (!key.startsWith('action.') || !key.endsWith('.success')) continue
    successTotal += toFiniteNumberOrZero(value)
  }

  const total = successTotal + failed
  if (total <= 0) return 0
  return noop / total
}

function sortEpisodes(rows: DashboardEpisode[], sortKey: EpisodeSortKey, sortDir: SortDir): DashboardEpisode[] {
  const direction = sortDir === 'asc' ? 1 : -1
  return [...rows].sort((a, b) => {
    if (sortKey === 'created_at') {
      const left = String(a.created_at ?? '')
      const right = String(b.created_at ?? '')
      return left.localeCompare(right) * direction
    }
    if (sortKey === 'opponent') {
      const left = String(a.opponent_name ?? '')
      const right = String(b.opponent_name ?? '')
      return left.localeCompare(right) * direction
    }
    if (sortKey === 'team') {
      const left = String(a.team_composition ?? '')
      const right = String(b.team_composition ?? '')
      return left.localeCompare(right) * direction
    }
    if (sortKey === 'reward') {
      const left = toFiniteNumber(a.reward ?? a.avg_reward) ?? Number.NEGATIVE_INFINITY
      const right = toFiniteNumber(b.reward ?? b.avg_reward) ?? Number.NEGATIVE_INFINITY
      return (left - right) * direction
    }
    if (sortKey === 'steps') {
      const left = toFiniteNumber(a.steps) ?? -1
      const right = toFiniteNumber(b.steps) ?? -1
      return (left - right) * direction
    }

    const left = episodeNoopRate(a)
    const right = episodeNoopRate(b)
    return (left - right) * direction
  })
}

function kpiSeverity(
  value: number | null,
  goodThreshold: number,
  badThreshold: number,
  higherIsBetter = true
): 'good' | 'warn' | 'bad' {
  if (value === null) return 'warn'
  if (higherIsBetter) {
    if (value >= goodThreshold) return 'good'
    if (value <= badThreshold) return 'bad'
    return 'warn'
  }
  if (value <= goodThreshold) return 'good'
  if (value >= badThreshold) return 'bad'
  return 'warn'
}

function severityStyle(severity: 'good' | 'warn' | 'bad'): CSSProperties {
  if (severity === 'good') {
    return {
      borderColor: 'var(--kpi-good-border)',
      background: 'var(--kpi-good-bg)',
    }
  }
  if (severity === 'bad') {
    return {
      borderColor: 'var(--kpi-bad-border)',
      background: 'var(--kpi-bad-bg)',
    }
  }
  return {
    borderColor: 'var(--kpi-warn-border)',
    background: 'var(--kpi-warn-bg)',
  }
}

function formatTrendValue(value: number | null | undefined, metricKey: string): string {
  if (value === null || value === undefined) return '-'
  if (metricKey === 'rank') return `#${Math.round(value)}`
  return value.toFixed(3)
}

function isAnalysisKeyMissingError(message: string | null): boolean {
  if (!message) return false
  const lower = message.toLowerCase()
  return lower.includes('anthropic_api_key') || lower.includes('x-anthropic-api-key')
}

function bestStrategyLabel(strategyProfile: Record<string, number> | null): string | null {
  if (!strategyProfile) return null
  let bestLabel: string | null = null
  let bestValue = Number.NEGATIVE_INFINITY
  for (const [key, value] of Object.entries(strategyProfile)) {
    if (!Number.isFinite(value)) continue
    if (value > bestValue) {
      bestValue = value
      bestLabel = key
    }
  }
  return bestLabel
}

function opponentColorMap(names: string[]): Record<string, string> {
  const unique = [...new Set(names)].sort()
  const map: Record<string, string> = {}
  for (let i = 0; i < unique.length; i += 1) {
    map[unique[i]] = OPPONENT_COLORS[i % OPPONENT_COLORS.length]
  }
  return map
}

function asTeamCompRows(value: unknown): DashboardTeamCompStats[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => entry && typeof entry === 'object' && !Array.isArray(entry))
    .map((entry) => entry as DashboardTeamCompStats)
}

function asMatchupSlices(value: unknown): DashboardMatchupSlice[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => entry && typeof entry === 'object' && !Array.isArray(entry))
    .map((entry) => entry as DashboardMatchupSlice)
}

function asTrendPoints(value: unknown): DashboardTrendPoint[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((entry) => entry && typeof entry === 'object' && !Array.isArray(entry))
    .map((entry) => entry as DashboardTrendPoint)
}

function asTrendExplorer(value: unknown): DashboardTrendExplorerSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardTrendExplorerSummary
}

function asConfidence(value: unknown): DashboardConfidenceSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardConfidenceSummary
}

function asPattern(value: unknown): DashboardPatternSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardPatternSummary
}

function asFailures(value: unknown): DashboardFailures {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as DashboardFailures
}

function asMatchup(value: unknown): DashboardMatchupSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardMatchupSummary
}

function asUnsupported(value: unknown): DashboardUnsupportedSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardUnsupportedSummary
}

function asInstrumentation(value: unknown): DashboardInstrumentationSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardInstrumentationSummary
}

function asStatsInventory(value: unknown): DashboardStatsInventorySummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardStatsInventorySummary
}

function asActions(value: unknown): DashboardActionSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardActionSummary
}

function asOrchestration(value: unknown): DashboardOrchestrationSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardOrchestrationSummary
}

function buildDashboardFeedbackUrl(
  payload: {
    policyVersionId: string
    policyLabel: string
    activeTab: string
    dashboardUrl: string
    generatedAt: string
  } | null
): string {
  if (!payload) return DASHBOARD_FEEDBACK_ISSUE_URL
  const title = `[Policy Dashboard] ${payload.policyLabel} (${payload.policyVersionId})`
  const body = [
    '## Summary',
    '<describe the issue or request>',
    '',
    '## Dashboard Context',
    `- Policy version ID: ${payload.policyVersionId}`,
    `- Policy: ${payload.policyLabel}`,
    `- Active tab: ${payload.activeTab}`,
    `- Generated at: ${payload.generatedAt}`,
    `- Dashboard URL: ${payload.dashboardUrl}`,
  ].join('\n')
  return `${DASHBOARD_FEEDBACK_ISSUE_URL}?${new URLSearchParams({ title, body }).toString()}`
}

function KPIStatCard({
  label,
  value,
  detail,
  severity,
}: {
  label: string
  value: string
  detail?: string
  severity: 'good' | 'warn' | 'bad'
}) {
  return (
    <article className="card" style={{ padding: 12, borderWidth: 2, ...severityStyle(severity) }}>
      <p
        style={{
          margin: 0,
          fontSize: 12,
          letterSpacing: 0.3,
          textTransform: 'uppercase',
          color: 'var(--kpi-label-ink)',
        }}
      >
        {label}
      </p>
      <p style={{ margin: '6px 0 0', fontSize: 24, fontWeight: 700 }}>{value}</p>
      {detail && <p style={{ margin: '6px 0 0', fontSize: 12, color: 'var(--kpi-detail-ink)' }}>{detail}</p>}
    </article>
  )
}

export function DashboardClient() {
  const [policyVersionId, setPolicyVersionId] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [analysisApiKey, setAnalysisApiKey] = useState('')
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [analysis, setAnalysis] = useState<DashboardAnalysisResponse | null>(null)
  const [rolePercentiles, setRolePercentiles] = useState<DashboardRolePercentilesResponse | null>(null)
  const [roleLoading, setRoleLoading] = useState(false)
  const [roleError, setRoleError] = useState<string | null>(null)
  const rolePercentilesCacheRef = useRef<Map<string, DashboardRolePercentilesResponse>>(new Map())
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview')

  const [statusFilter, setStatusFilter] = useState<EpisodeStatusFilter>('all')
  const [replayOnly, setReplayOnly] = useState(false)
  const [tagQuery, setTagQuery] = useState('')
  const [episodeSort, setEpisodeSort] = useState<EpisodeSortKey>('reward')
  const [episodeSortDir, setEpisodeSortDir] = useState<SortDir>('desc')

  const [selectedTrendMetric, setSelectedTrendMetric] = useState('score')
  const [showAnalysis, setShowAnalysis] = useState(true)
  const [diagnoseRuns, setDiagnoseRuns] = useState<DiagnoseRunSummary[]>([])
  const [diagnoseLoading, setDiagnoseLoading] = useState(false)
  const [diagnoseError, setDiagnoseError] = useState<string | null>(null)
  const [selectedDiagnoseRunId, setSelectedDiagnoseRunId] = useState<string | null>(null)
  const [diagnoseManifest, setDiagnoseManifest] = useState<DiagnoseManifest | null>(null)
  const [diagnoseNote, setDiagnoseNote] = useState<DiagnoseDoctorNote | null>(null)
  const [diagnoseNoteLoading, setDiagnoseNoteLoading] = useState(false)
  const [diagnoseNoteError, setDiagnoseNoteError] = useState<string | null>(null)

  const activateTab = useCallback((tab: DashboardTab) => {
    setActiveTab(tab)
    if (typeof window !== 'undefined') {
      const url = new URL(window.location.href)
      if (url.searchParams.get('tab') !== tab) {
        url.searchParams.set('tab', tab)
        window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
      }
    }
  }, [])

  const episodes = useMemo(() => (Array.isArray(data?.episodes) ? data.episodes : []), [data])
  const completedEpisodes = useMemo(() => episodes.filter((episode) => episode.status === 'completed'), [episodes])
  const failedEpisodes = useMemo(() => episodes.filter((episode) => episode.status === 'failed'), [episodes])

  const diagnostics = useMemo(() => asStringArray(data?.derived?.kpis?.diagnostics), [data])
  const failures = useMemo(() => asFailures(data?.derived?.failures), [data])
  const matchup = useMemo(() => asMatchup(data?.derived?.matchup), [data])
  const trend = useMemo<DashboardTrendSummary | null>(() => {
    if (!data?.derived?.trend || typeof data.derived.trend !== 'object' || Array.isArray(data.derived.trend))
      return null
    return data.derived.trend
  }, [data])
  const trendExplorer = useMemo(() => asTrendExplorer(data?.derived?.trend_explorer), [data])
  const confidence = useMemo(() => asConfidence(data?.derived?.confidence), [data])
  const patterns = useMemo(() => asPattern(data?.derived?.patterns), [data])
  const unsupported = useMemo(() => asUnsupported(data?.derived?.unsupported), [data])
  const instrumentation = useMemo(() => asInstrumentation(data?.derived?.instrumentation), [data])
  const statsInventory = useMemo(() => asStatsInventory(data?.derived?.stats_inventory), [data])
  const actionSummary = useMemo(() => asActions(data?.derived?.actions), [data])
  const orchestration = useMemo(() => asOrchestration(data?.derived?.orchestration), [data])

  const opponentRows = useMemo<OpponentSummaryRow[]>(() => {
    const metrics = data?.derived?.opponent_metrics
    if (metrics && typeof metrics === 'object' && !Array.isArray(metrics)) {
      const rows: OpponentSummaryRow[] = []
      for (const [opponent, stats] of Object.entries(metrics)) {
        if (!stats || typeof stats !== 'object' || Array.isArray(stats)) continue
        const count = toFiniteNumber((stats as Record<string, unknown>).count) ?? 0
        if (count <= 0) continue

        const avgReward = toFiniteNumber((stats as Record<string, unknown>).avg_reward)
        const totalReward = toFiniteNumber((stats as Record<string, unknown>).total_reward)
        let strategyProfile: Record<string, number> | null = null
        const rawStrategy = (stats as Record<string, unknown>).strategy_profile
        if (rawStrategy && typeof rawStrategy === 'object' && !Array.isArray(rawStrategy)) {
          strategyProfile = {}
          for (const [key, value] of Object.entries(rawStrategy)) {
            const parsed = toFiniteNumber(value)
            if (parsed !== null) strategyProfile[key] = parsed
          }
        }

        const relatedCompleted = completedEpisodes.filter((episode) => episode.opponent_name === opponent)
        const wins = relatedCompleted.filter(
          (episode) => (toFiniteNumber(episode.reward ?? episode.avg_reward) ?? 0) > 0.5
        ).length
        const winRate = relatedCompleted.length > 0 ? wins / relatedCompleted.length : null

        rows.push({
          opponent,
          count,
          completed: relatedCompleted.length,
          avgReward,
          totalReward,
          winRate,
          bestProfile: bestStrategyLabel(strategyProfile),
          strategyProfile,
          source: 'derived',
        })
      }

      if (rows.length > 0) {
        return rows.sort(
          (a, b) => (b.avgReward ?? Number.NEGATIVE_INFINITY) - (a.avgReward ?? Number.NEGATIVE_INFINITY)
        )
      }
    }

    const fallback = new Map<
      string,
      { count: number; completed: number; rewardTotal: number; rewardCount: number; wins: number }
    >()
    for (const episode of episodes) {
      const opponent = String(episode.opponent_name ?? 'unknown')
      const row = fallback.get(opponent) ?? { count: 0, completed: 0, rewardTotal: 0, rewardCount: 0, wins: 0 }
      row.count += 1
      if (episode.status === 'completed') {
        row.completed += 1
        const reward = toFiniteNumber(episode.reward ?? episode.avg_reward)
        if (reward !== null) {
          row.rewardTotal += reward
          row.rewardCount += 1
          if (reward > 0.5) row.wins += 1
        }
      }
      fallback.set(opponent, row)
    }

    const rows = [...fallback.entries()].map(([opponent, row]) => ({
      opponent,
      count: row.count,
      completed: row.completed,
      avgReward: row.rewardCount > 0 ? row.rewardTotal / row.rewardCount : null,
      totalReward: row.rewardCount > 0 ? row.rewardTotal : null,
      winRate: row.completed > 0 ? row.wins / row.completed : null,
      bestProfile: null,
      strategyProfile: null,
      source: 'episodes' as const,
    }))

    return rows.sort((a, b) => (b.avgReward ?? Number.NEGATIVE_INFINITY) - (a.avgReward ?? Number.NEGATIVE_INFINITY))
  }, [completedEpisodes, data, episodes])

  const colorMap = useMemo(
    () => opponentColorMap(episodes.map((episode) => String(episode.opponent_name ?? 'unknown'))),
    [episodes]
  )

  const bestWorstOpponents = useMemo(() => {
    if (opponentRows.length === 0) return null
    const withReward = opponentRows.filter((row) => row.avgReward !== null)
    if (withReward.length === 0) return null

    let best = withReward[0]
    let worst = withReward[0]
    for (const row of withReward) {
      if ((row.avgReward ?? Number.NEGATIVE_INFINITY) > (best.avgReward ?? Number.NEGATIVE_INFINITY)) best = row
      if ((row.avgReward ?? Number.POSITIVE_INFINITY) < (worst.avgReward ?? Number.POSITIVE_INFINITY)) worst = row
    }

    return { best, worst }
  }, [opponentRows])

  const filteredEpisodes = useMemo(() => {
    const query = tagQuery.trim().toLowerCase()
    return episodes.filter((episode) => {
      if (statusFilter !== 'all' && episode.status !== statusFilter) return false
      if (replayOnly && !episode.replay_url) return false
      if (!query) return true

      const diagnosticTags = asStringArray(episode.diagnostic_tags)
      const rawTags = episode.raw_tags
      const keyValueTags: string[] = []
      if (rawTags && typeof rawTags === 'object' && !Array.isArray(rawTags)) {
        for (const [key, value] of Object.entries(rawTags)) {
          keyValueTags.push(`${key}=${String(value)}`)
        }
      }

      const haystack = [...diagnosticTags, ...keyValueTags].join(' ').toLowerCase()
      return haystack.includes(query)
    })
  }, [episodes, replayOnly, statusFilter, tagQuery])

  const sortedEpisodes = useMemo(
    () => sortEpisodes(filteredEpisodes, episodeSort, episodeSortDir),
    [episodeSort, episodeSortDir, filteredEpisodes]
  )

  const topTagStats = useMemo(() => {
    const counts = new Map<string, number>()
    const updateCount = (tag: string) => {
      if (!tag) return
      counts.set(tag, (counts.get(tag) ?? 0) + 1)
    }
    for (const episode of episodes) {
      const seen = new Set<string>()
      for (const tag of asStringArray(episode.behavior_tags)) {
        if (seen.has(tag)) continue
        seen.add(tag)
        updateCount(tag)
      }
    }
    return [...counts.entries()]
      .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
      .slice(0, 24)
      .map(([tag, count]) => ({
        tag,
        count,
        coverage: episodes.length > 0 ? count / episodes.length : 0,
      }))
  }, [episodes])

  const replayLookupByRef = useMemo(() => {
    const lookup: Record<string, string> = {}
    for (const episode of episodes) {
      if (!episode.replay_url) continue
      const replayUrl = String(episode.replay_url)
      const episodeId = String(episode.episode_id ?? episode.id ?? '').trim()
      if (episodeId) lookup[episodeId] = replayUrl
      const jobId = String(episode.job_id ?? '').trim()
      if (jobId) lookup[jobId] = replayUrl
    }
    return lookup
  }, [episodes])

  const teamCompRows = useMemo(() => asTeamCompRows(data?.derived?.team_comp), [data])
  const trendPoints = useMemo(() => asTrendPoints(trend?.points), [trend])

  const trendSeries = useMemo(() => {
    if (!trendExplorer?.series || !Array.isArray(trendExplorer.series)) return []
    return trendExplorer.series
  }, [trendExplorer])

  const selectedTrendSeries = useMemo(() => {
    if (trendSeries.length === 0) return null
    return trendSeries.find((series) => series.key === selectedTrendMetric) ?? trendSeries[0]
  }, [selectedTrendMetric, trendSeries])

  const selectedTrendOverlay = useMemo(() => {
    if (!trendExplorer?.metric_overlays || !Array.isArray(trendExplorer.metric_overlays) || !selectedTrendSeries)
      return null
    return trendExplorer.metric_overlays.find((overlay) => overlay.key === selectedTrendSeries.key) ?? null
  }, [selectedTrendSeries, trendExplorer])

  const selectedTrendPatternGroups = useMemo(() => {
    if (
      !trendExplorer?.submission_patterns ||
      !Array.isArray(trendExplorer.submission_patterns) ||
      !selectedTrendSeries
    ) {
      return []
    }
    return trendExplorer.submission_patterns.filter((pattern) => pattern.metric_key === selectedTrendSeries.key)
  }, [selectedTrendSeries, trendExplorer])

  const feedbackUrl = useMemo(() => {
    if (!data) return DASHBOARD_FEEDBACK_ISSUE_URL
    const dashboardUrl = typeof window === 'undefined' ? '/policy-dashboard' : window.location.href
    return buildDashboardFeedbackUrl({
      policyVersionId: String(data.policy?.id ?? ''),
      policyLabel: `${String(data.policy?.name ?? 'unknown')} v${String(data.policy?.version ?? '?')}`,
      activeTab,
      dashboardUrl,
      generatedAt: String(data.generated_at ?? '-'),
    })
  }, [activeTab, data])

  useEffect(() => {
    if (trendSeries.length === 0) return
    if (trendSeries.some((series) => series.key === selectedTrendMetric)) return
    const defaultMetric = trendExplorer?.selected_metric ?? trendSeries[0].key
    setSelectedTrendMetric(defaultMetric)
  }, [selectedTrendMetric, trendExplorer?.selected_metric, trendSeries])

  const loadDashboardData = useCallback(async (rawPolicyVersionId: string) => {
    const trimmedPolicyVersionId = rawPolicyVersionId.trim()
    if (!trimmedPolicyVersionId) return

    setError(null)
    setAnalysisError(null)
    setAnalysis(null)
    setRolePercentiles(null)
    setRoleError(null)
    setRoleLoading(false)
    setLoading(true)
    try {
      const response = await fetchDashboardData(trimmedPolicyVersionId)
      setData(response)
      if (typeof window !== 'undefined') {
        const url = new URL(window.location.href)
        if (url.searchParams.get('policyVersionId') !== trimmedPolicyVersionId) {
          url.searchParams.set('policyVersionId', trimmedPolicyVersionId)
          window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  const onLoad = async () => {
    await loadDashboardData(policyVersionId)
  }

  const onRunAnalysis = async () => {
    if (!policyVersionId.trim()) return
    setAnalysisError(null)
    setAnalysisLoading(true)
    try {
      const response = await fetchDashboardAnalysis(policyVersionId.trim(), analysisApiKey)
      setAnalysis(response)
      setShowAnalysis(true)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setAnalysisError(message)
    } finally {
      setAnalysisLoading(false)
    }
  }

  const onEpisodeSort = (sortKey: EpisodeSortKey) => {
    if (episodeSort === sortKey) {
      setEpisodeSortDir((current) => (current === 'asc' ? 'desc' : 'asc'))
      return
    }
    setEpisodeSort(sortKey)
    setEpisodeSortDir('desc')
  }

  const onExportEpisodes = () => {
    if (!data || typeof window === 'undefined') return

    const payload = {
      exported_at: new Date().toISOString(),
      policy: data.policy ?? {},
      season: data.season,
      generated_at: data.generated_at,
      selection: data.selection ?? {},
      filters: {
        status: statusFilter,
        replay_only: replayOnly,
        tag_query: tagQuery,
      },
      sort: { key: episodeSort, direction: episodeSortDir },
      episode_count: sortedEpisodes.length,
      episodes: sortedEpisodes,
    }

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `dashboard-${String(data.policy?.name ?? 'policy')}-v${String(data.policy?.version ?? 'x')}-episodes.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    if (activeTab !== 'roles') return
    const loadedPolicyVersionId = data?.policy?.id
    if (!loadedPolicyVersionId) return
    const policyVersionKey = String(loadedPolicyVersionId)
    const generatedAt = typeof data?.generated_at === 'string' ? data.generated_at : ''
    const cacheKey = generatedAt ? `${policyVersionKey}:${generatedAt}` : null

    const cachedPercentiles = cacheKey ? rolePercentilesCacheRef.current.get(cacheKey) : undefined
    if (cacheKey && cachedPercentiles !== undefined) {
      setRolePercentiles(cachedPercentiles)
      setRoleLoading(false)
      setRoleError(null)
      return
    }

    let cancelled = false
    setRoleLoading(true)
    setRoleError(null)

    void fetchDashboardRolePercentiles(policyVersionKey)
      .then((response) => {
        if (cancelled) return
        if (cacheKey) {
          rolePercentilesCacheRef.current.set(cacheKey, response)
        }
        setRolePercentiles(response)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setRoleError(err instanceof Error ? err.message : String(err))
        setRolePercentiles(null)
      })
      .finally(() => {
        if (cancelled) return
        setRoleLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeTab, data?.policy?.id, data?.generated_at])

  useEffect(() => {
    if (!data) {
      setDiagnoseRuns([])
      setSelectedDiagnoseRunId(null)
      setDiagnoseManifest(null)
      setDiagnoseNote(null)
      setDiagnoseError(null)
      setDiagnoseNoteError(null)
      return
    }

    let cancelled = false
    setDiagnoseLoading(true)
    setDiagnoseError(null)

    void fetchDiagnoseRuns()
      .then((response) => {
        if (cancelled) return
        const sortedRuns = [...response.runs].sort((left, right) => {
          const byCreatedAt = manifestTimestamp(right.manifest) - manifestTimestamp(left.manifest)
          if (byCreatedAt !== 0) return byCreatedAt
          return right.run_id.localeCompare(left.run_id)
        })

        setDiagnoseRuns(sortedRuns)
        setSelectedDiagnoseRunId((current) => {
          if (current && sortedRuns.some((run) => run.run_id === current)) return current
          const preferred =
            sortedRuns.find((run) => runLikelyMatchesPolicy(run, data.policy)) ??
            sortedRuns.find((run) => Boolean(run.manifest)) ??
            sortedRuns[0]
          return preferred?.run_id ?? null
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setDiagnoseRuns([])
        setSelectedDiagnoseRunId(null)
        setDiagnoseManifest(null)
        setDiagnoseNote(null)
        setDiagnoseError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (cancelled) return
        setDiagnoseLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [data])

  useEffect(() => {
    if (!selectedDiagnoseRunId) {
      setDiagnoseManifest(null)
      setDiagnoseNote(null)
      setDiagnoseNoteError(null)
      return
    }

    let cancelled = false
    setDiagnoseNoteLoading(true)
    setDiagnoseNoteError(null)
    setDiagnoseManifest(diagnoseRuns.find((run) => run.run_id === selectedDiagnoseRunId)?.manifest ?? null)

    void Promise.allSettled([
      fetchDiagnoseDoctorNote(selectedDiagnoseRunId),
      fetchDiagnoseManifest(selectedDiagnoseRunId),
    ])
      .then((results) => {
        if (cancelled) return
        const [noteResult, manifestResult] = results

        if (noteResult.status === 'fulfilled') {
          setDiagnoseNote(noteResult.value)
        } else {
          setDiagnoseNote(null)
          const message = noteResult.reason instanceof Error ? noteResult.reason.message : String(noteResult.reason)
          setDiagnoseNoteError(message)
        }

        if (manifestResult.status === 'fulfilled') {
          setDiagnoseManifest(manifestResult.value)
        }
      })
      .finally(() => {
        if (cancelled) return
        setDiagnoseNoteLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [diagnoseRuns, selectedDiagnoseRunId])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const initialPolicyVersionId = params.get('policyVersionId')?.trim()
    const initialTab = parseDashboardTab(params.get('tab'))

    if (initialTab) setActiveTab(initialTab)

    let cancelled = false
    const initialize = async () => {
      if (initialPolicyVersionId) {
        setPolicyVersionId(initialPolicyVersionId)
        await loadDashboardData(initialPolicyVersionId)
        return
      }

      try {
        const response = await fetchDashboardDefaultPolicyVersion()
        const defaultPolicyVersionId = response.policy_version_id?.trim()
        if (!defaultPolicyVersionId || cancelled) return
        setPolicyVersionId(defaultPolicyVersionId)
        await loadDashboardData(defaultPolicyVersionId)
      } catch {
        // Leave manual entry as fallback when default lookup is unavailable.
      }
    }

    void initialize()
    return () => {
      cancelled = true
    }
  }, [loadDashboardData])

  const kpis = data?.derived?.kpis
  const avgReward = toFiniteNumber(kpis?.avg_reward ?? kpis?.mean_reward)
  const moveEfficiency = toFiniteNumber(kpis?.move_efficiency)
  const actionSuccess = toFiniteNumber(kpis?.action_success_rate)
  const resourceRetention = toFiniteNumber(kpis?.resource_retention)
  const freezeVulnerability = toFiniteNumber(kpis?.freeze_vulnerability)
  const junctionControl = toFiniteNumber(kpis?.junction_control_rate)
  const noopRate = toFiniteNumber(kpis?.noop_rate)
  const rewardConsistency = toFiniteNumber(kpis?.reward_consistency)

  return (
    <main className="grid dashboard-shell" style={{ gap: 16 }}>
      <section className="card dashboard-control-card grid" style={{ gap: 12 }}>
        <div className="dashboard-control-head">
          <div>
            <h1 className="dashboard-title-line">
              <span>Policy Dashboard</span>
              <span className="dashboard-title-subline">
                Performance, diagnose, and skill-tree evaluation in one view.
              </span>
            </h1>
          </div>
          <p style={{ margin: 0, color: '#6f86a6', fontSize: 12 }}>
            backend: <code>{DASHBOARD_API_BASE_URL}</code>
          </p>
        </div>
        <div className="dashboard-policy-row">
          <label htmlFor="policy-version-id" className="dashboard-policy-label">
            Policy version id:
          </label>
          <input
            id="policy-version-id"
            className="dashboard-policy-input"
            placeholder="UUID"
            value={policyVersionId}
            onChange={(event) => setPolicyVersionId(event.target.value)}
          />
          <button type="button" className="primary-btn" onClick={onLoad} disabled={loading || !policyVersionId.trim()}>
            {loading ? 'Loading...' : 'Load dashboard data'}
          </button>
        </div>
        {error && (
          <p style={{ margin: 0, color: '#b42318' }}>
            <strong>Error:</strong> {error}
          </p>
        )}
      </section>

      {data && (
        <>
          <section className="card" style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 14 }}>
            <span>
              <strong>{String(data.policy?.name ?? 'Unknown policy')}</strong> v{String(data.policy?.version ?? '?')}
            </span>
            <span>Season: {String(data.season ?? '-')}</span>
            <span>
              Rank: {data.policy?.rank === null || data.policy?.rank === undefined ? '-' : `#${data.policy?.rank}`}
            </span>
            <span>Score: {formatNumber(toFiniteNumber(data.policy?.score), 3)}</span>
            <span>Episodes: {episodes.length}</span>
            <span>Completed: {completedEpisodes.length}</span>
            <span>Failed: {failedEpisodes.length}</span>
            <span>Generated: {formatDateTime(data.generated_at)}</span>
            {data.derived?.outcome?.verdict && (
              <span>
                Outcome: <strong style={{ textTransform: 'uppercase' }}>{String(data.derived.outcome.verdict)}</strong>
              </span>
            )}
          </section>

          <section className="tab-row">
            <button
              type="button"
              onClick={() => activateTab('overview')}
              className={activeTab === 'overview' ? 'active-tab' : ''}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => activateTab('capabilities')}
              className={activeTab === 'capabilities' ? 'active-tab' : ''}
            >
              Capabilities
            </button>
            <button
              type="button"
              onClick={() => activateTab('roles')}
              className={activeTab === 'roles' ? 'active-tab' : ''}
            >
              Parses
            </button>
            <button
              type="button"
              onClick={() => activateTab('opponents')}
              className={activeTab === 'opponents' ? 'active-tab' : ''}
            >
              Opponents
            </button>
            <button
              type="button"
              onClick={() => activateTab('episodes')}
              className={activeTab === 'episodes' ? 'active-tab' : ''}
            >
              Episodes
            </button>
            <button
              type="button"
              onClick={() => activateTab('health')}
              className={activeTab === 'health' ? 'active-tab' : ''}
            >
              Health
            </button>
            <button
              type="button"
              onClick={() => activateTab('cogames_diagnose')}
              className={activeTab === 'cogames_diagnose' ? 'active-tab' : ''}
            >
              Diagnose
            </button>
            <button
              type="button"
              onClick={() => activateTab('analysis')}
              className={activeTab === 'analysis' ? 'active-tab' : ''}
            >
              Analysis
            </button>
          </section>

          {activeTab === 'overview' && (
            <>
              <section
                className="grid"
                style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}
              >
                <KPIStatCard
                  label="Avg Reward"
                  value={formatNumber(avgReward, 2)}
                  severity={kpiSeverity(avgReward, 2.0, 0.5)}
                />
                <KPIStatCard
                  label="Move Efficiency"
                  value={formatPercent(moveEfficiency, 0)}
                  severity={kpiSeverity(moveEfficiency, 0.8, 0.5)}
                />
                <KPIStatCard
                  label="Action Success"
                  value={formatPercent(actionSuccess, 0)}
                  severity={kpiSeverity(actionSuccess, 0.9, 0.7)}
                />
                <KPIStatCard
                  label="Resource Retention"
                  value={formatPercent(resourceRetention, 0)}
                  severity={kpiSeverity(resourceRetention, 0.5, 0.2)}
                />
                <KPIStatCard
                  label="Freeze Vulnerability"
                  value={formatPercent(freezeVulnerability, 1)}
                  severity={kpiSeverity(freezeVulnerability, 0.05, 0.15, false)}
                />
                <KPIStatCard
                  label="Junction Control"
                  value={formatPercent(junctionControl, 0)}
                  severity={kpiSeverity(junctionControl, 0.6, 0.2)}
                />
                <KPIStatCard
                  label="Noop Rate"
                  value={formatPercent(noopRate, 1)}
                  severity={kpiSeverity(noopRate, 0.1, 0.25, false)}
                />
                <KPIStatCard
                  label="Reward Consistency"
                  value={formatPercent(rewardConsistency, 0)}
                  severity={kpiSeverity(rewardConsistency, 0.6, 0.2)}
                />
              </section>

              {data.derived?.outcome && (
                <section className="card">
                  <h2 style={{ marginTop: 0 }}>Outcome Summary</h2>
                  <p style={{ marginTop: 0 }}>
                    {String(data.derived.outcome.reason ?? 'No outcome summary provided.')}
                  </p>
                  <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 13 }}>
                    <span>
                      Evidence: <strong>{data.derived.outcome.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                    </span>
                    <span>
                      Score delta:{' '}
                      <code>{formatSigned(toFiniteNumber(data.derived.outcome.delta?.score_delta), 3)}</code>
                    </span>
                    <span>
                      Rank delta: <code>{formatSigned(toFiniteNumber(data.derived.outcome.delta?.rank_delta), 0)}</code>
                    </span>
                    <span>
                      Baseline: v
                      {data.derived.outcome.baseline?.version === null ||
                      data.derived.outcome.baseline?.version === undefined
                        ? '-'
                        : data.derived.outcome.baseline.version}
                    </span>
                  </div>
                </section>
              )}

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Diagnostics ({diagnostics.length})</h2>
                {diagnostics.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No diagnostics emitted.</p>
                ) : (
                  <ul style={{ marginBottom: 0, display: 'grid', gap: 6 }}>
                    {diagnostics.map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))}
                  </ul>
                )}
              </section>

              {(unsupported || instrumentation) && (
                <section className="card" style={{ display: 'grid', gap: 10 }}>
                  <h2 style={{ margin: 0 }}>Data Quality Gates</h2>
                  {unsupported?.has_unsupported_state ? (
                    <div className="grid" style={{ gap: 8 }}>
                      <p style={{ margin: 0, color: '#b42318' }}>
                        Unsupported-state warnings detected ({(unsupported.issues ?? []).length}).
                      </p>
                      <div style={{ overflowX: 'auto' }}>
                        <table>
                          <thead>
                            <tr>
                              <th>Issue</th>
                              <th>Severity</th>
                              <th>Coverage</th>
                              <th>Next Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(unsupported.issues ?? []).map((issue) => (
                              <tr key={String(issue.code ?? issue.message ?? 'unsupported')}>
                                <td>{String(issue.message ?? issue.code ?? '-')}</td>
                                <td>{String(issue.severity ?? 'warn')}</td>
                                <td>
                                  {String(toFiniteNumber(issue.affected_count) ?? 0)}/
                                  {String(toFiniteNumber(issue.total_count) ?? 0)}
                                </td>
                                <td>{String(issue.recommended_action ?? '-')}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  ) : (
                    <p style={{ margin: 0 }}>Unsupported-state checks are clean for the sampled episode set.</p>
                  )}

                  {instrumentation && (
                    <div className="grid" style={{ gap: 8 }}>
                      <p style={{ margin: 0 }}>
                        Instrumentation: <strong>{instrumentation.compliant ? 'compliant' : 'incomplete'}</strong> ·
                        score <code>{formatPercent(toFiniteNumber(instrumentation.score), 0)}</code> · template{' '}
                        <code>{String(instrumentation.template_version ?? '-')}</code>
                      </p>
                      {(instrumentation.checks ?? []).length > 0 && (
                        <details>
                          <summary>Instrumentation Checks ({(instrumentation.checks ?? []).length})</summary>
                          <div style={{ overflowX: 'auto', marginTop: 10 }}>
                            <table>
                              <thead>
                                <tr>
                                  <th>Key</th>
                                  <th>Kind</th>
                                  <th>Status</th>
                                  <th>Coverage</th>
                                  <th>Message</th>
                                </tr>
                              </thead>
                              <tbody>
                                {(instrumentation.checks ?? []).map((check) => (
                                  <tr key={String(check.key ?? 'check')}>
                                    <td>
                                      <code>{String(check.key ?? '-')}</code>
                                    </td>
                                    <td>{String(check.kind ?? '-')}</td>
                                    <td>{String(check.status ?? '-')}</td>
                                    <td>{formatPercent(toFiniteNumber(check.coverage), 0)}</td>
                                    <td>{String(check.message ?? '-')}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        </details>
                      )}
                    </div>
                  )}
                </section>
              )}

              {actionSummary && (
                <section className="card" style={{ display: 'grid', gap: 8 }}>
                  <h2 style={{ margin: 0 }}>Next Actions</h2>
                  <p style={{ margin: 0 }}>
                    <strong>{String(actionSummary.headline ?? 'No action summary available.')}</strong>
                  </p>
                  <p style={{ margin: 0, fontSize: 13 }}>
                    Rollout gate: <code>{String(actionSummary.rollout_recommendation ?? '-')}</code>
                  </p>
                  {(actionSummary.actions ?? []).length > 0 && (
                    <ul style={{ margin: 0 }}>
                      {(actionSummary.actions ?? []).map((action) => (
                        <li key={action}>{action}</li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              {orchestration && (
                <section className="card" style={{ display: 'grid', gap: 8 }}>
                  <h2 style={{ margin: 0 }}>Experiment Orchestration</h2>
                  <p style={{ margin: 0 }}>
                    {String(orchestration.headline ?? '-')} · mode <code>{String(orchestration.mode ?? '-')}</code>
                  </p>
                  {(orchestration.experiments ?? []).length > 0 && (
                    <div className="grid" style={{ gap: 8 }}>
                      {(orchestration.experiments ?? []).map((experiment) => (
                        <article key={String(experiment.id ?? 'exp')} className="diagnose-list-item">
                          <p style={{ marginTop: 0, marginBottom: 4 }}>
                            <strong>
                              P{String(toFiniteNumber(experiment.priority) ?? 0)} {String(experiment.title ?? '-')}
                            </strong>
                          </p>
                          <p style={{ margin: '0 0 6px', fontSize: 13 }}>{String(experiment.objective ?? '-')}</p>
                          <p style={{ margin: '0 0 6px', fontSize: 12, color: '#546b8a' }}>
                            {String(experiment.rationale ?? '-')}
                          </p>
                          {(experiment.actions ?? []).length > 0 && (
                            <ul style={{ margin: 0 }}>
                              {(experiment.actions ?? []).map((action) => (
                                <li key={action}>{action}</li>
                              ))}
                            </ul>
                          )}
                        </article>
                      ))}
                    </div>
                  )}
                </section>
              )}

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Team Composition</h2>
                {teamCompRows.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No team composition data available.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Composition</th>
                          <th>Count</th>
                          <th>Avg Reward</th>
                          <th>Move Eff.</th>
                          <th>Avg Junction Aligned</th>
                          <th>Avg Resource Gained</th>
                        </tr>
                      </thead>
                      <tbody>
                        {teamCompRows.map((row) => (
                          <tr key={String(row.composition ?? 'unknown')}>
                            <td>
                              <code>{String(row.composition ?? '-')}</code>
                            </td>
                            <td>{toFiniteNumber(row.count) ?? '-'}</td>
                            <td>{formatNumber(toFiniteNumber(row.avg_reward), 2)}</td>
                            <td>{formatPercent(toFiniteNumber(row.avg_move_efficiency), 0)}</td>
                            <td>{formatNumber(toFiniteNumber(row.avg_junction_aligned), 2)}</td>
                            <td>{formatNumber(toFiniteNumber(row.avg_resource_gained), 0)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {trend && (
                <section className="card" style={{ display: 'grid', gap: 12 }}>
                  <h2 style={{ margin: 0 }}>Version Trend</h2>
                  <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 13 }}>
                    <span>
                      Direction:{' '}
                      <strong style={{ textTransform: 'uppercase' }}>
                        {String(trend.direction ?? 'insufficient')}
                      </strong>
                    </span>
                    <span>
                      Score delta: <code>{formatSigned(toFiniteNumber(trend.score_delta_from_oldest), 3)}</code>
                    </span>
                    <span>
                      Rank delta: <code>{formatSigned(toFiniteNumber(trend.rank_delta_from_oldest), 0)}</code>
                    </span>
                    <span>
                      Evidence: <strong>{trend.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                    </span>
                  </div>
                  <p style={{ margin: 0 }}>{String(trend.reason ?? '')}</p>

                  {trendPoints.length > 0 && (
                    <div style={{ overflowX: 'auto' }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Version</th>
                            <th>Score</th>
                            <th>Rank</th>
                            <th>Matches</th>
                          </tr>
                        </thead>
                        <tbody>
                          {trendPoints.map((point) => (
                            <tr key={String(point.id ?? `${point.name}-${point.version}`)}>
                              <td>
                                <code>v{String(point.version ?? '-')}</code>
                              </td>
                              <td>{formatNumber(toFiniteNumber(point.score), 3)}</td>
                              <td>{point.rank === null || point.rank === undefined ? '-' : `#${point.rank}`}</td>
                              <td>{toFiniteNumber(point.matches) ?? '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}

                  {selectedTrendSeries && (
                    <details>
                      <summary>Trend Explorer</summary>
                      <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
                        <label style={{ display: 'grid', gap: 6, maxWidth: 360 }}>
                          Metric
                          <select
                            value={selectedTrendSeries.key}
                            onChange={(event) => setSelectedTrendMetric(event.target.value)}
                          >
                            {trendSeries.map((series) => (
                              <option key={series.key} value={series.key}>
                                {series.label}
                              </option>
                            ))}
                          </select>
                        </label>
                        <p style={{ margin: 0, fontSize: 13 }}>
                          <strong style={{ textTransform: 'uppercase' }}>
                            {String(selectedTrendSeries.direction ?? 'insufficient')}
                          </strong>
                          : {String(selectedTrendSeries.reason ?? 'No trend reason provided.')}
                        </p>

                        {selectedTrendOverlay && (
                          <div className="card" style={{ background: 'var(--panel-soft-bg-1)' }}>
                            <p style={{ marginTop: 0, marginBottom: 8 }}>
                              Team vs Population Overlay ({selectedTrendOverlay.signal ?? 'insufficient'})
                            </p>
                            <p style={{ marginTop: 0, marginBottom: 8, fontSize: 13 }}>
                              {selectedTrendOverlay.reason ?? '-'}
                            </p>
                            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
                              <span>
                                Current:{' '}
                                <code>
                                  {formatTrendValue(selectedTrendOverlay.current_value, selectedTrendSeries.key)}
                                </code>
                              </span>
                              <span>
                                Team mean:{' '}
                                <code>
                                  {formatTrendValue(selectedTrendOverlay.team?.mean ?? null, selectedTrendSeries.key)}
                                </code>
                              </span>
                              <span>
                                Population mean:{' '}
                                <code>
                                  {formatTrendValue(
                                    selectedTrendOverlay.population?.mean ?? null,
                                    selectedTrendSeries.key
                                  )}
                                </code>
                              </span>
                              <span>
                                Delta vs team:{' '}
                                <code>
                                  {formatSigned(
                                    toFiniteNumber(selectedTrendOverlay.delta_vs_team_mean),
                                    selectedTrendSeries.key === 'rank' ? 0 : 3
                                  )}
                                </code>
                              </span>
                              <span>
                                Delta vs population:{' '}
                                <code>
                                  {formatSigned(
                                    toFiniteNumber(selectedTrendOverlay.delta_vs_population_mean),
                                    selectedTrendSeries.key === 'rank' ? 0 : 3
                                  )}
                                </code>
                              </span>
                            </div>
                          </div>
                        )}

                        {Array.isArray(selectedTrendSeries.values) && Array.isArray(selectedTrendSeries.deltas) && (
                          <div style={{ overflowX: 'auto' }}>
                            <table>
                              <thead>
                                <tr>
                                  <th>Version</th>
                                  <th>Value</th>
                                  <th>Delta vs prev</th>
                                </tr>
                              </thead>
                              <tbody>
                                {((trendExplorer?.version_labels ?? []) as string[]).map((label, index) => {
                                  const value = selectedTrendSeries.values?.[index] ?? null
                                  const delta = selectedTrendSeries.deltas?.[index] ?? null
                                  return (
                                    <tr key={`${label}-${index}`}>
                                      <td>
                                        <code>{label}</code>
                                      </td>
                                      <td>{formatTrendValue(value, selectedTrendSeries.key)}</td>
                                      <td>
                                        {delta === null
                                          ? '-'
                                          : formatSigned(delta, selectedTrendSeries.key === 'rank' ? 0 : 3)}
                                      </td>
                                    </tr>
                                  )
                                })}
                              </tbody>
                            </table>
                          </div>
                        )}

                        {selectedTrendPatternGroups.length > 0 && (
                          <div className="card" style={{ background: 'var(--panel-soft-bg-2)' }}>
                            <h3 style={{ marginTop: 0 }}>Cross-Submission Pattern Groups</h3>
                            <div style={{ display: 'grid', gap: 8 }}>
                              {selectedTrendPatternGroups.map((group) => (
                                <article
                                  key={`${String(group.code ?? 'group')}-${String(group.metric_key ?? '')}-${String(group.title ?? '')}`}
                                  className="card"
                                  style={{ padding: 12 }}
                                >
                                  <p style={{ marginTop: 0, marginBottom: 6 }}>
                                    <strong>{String(group.title ?? group.code ?? 'Pattern')}</strong>{' '}
                                    <span style={{ color: '#4b617f' }}>
                                      ({String(group.count ?? 0)}, {String(group.severity ?? 'info')})
                                    </span>
                                  </p>
                                  <p style={{ margin: '0 0 4px', fontSize: 13 }}>{String(group.evidence ?? '')}</p>
                                  <p style={{ margin: '0 0 4px', fontSize: 13 }}>{String(group.next_action ?? '')}</p>
                                  <p style={{ margin: 0, fontSize: 12, color: '#4b617f' }}>
                                    Versions: {Array.isArray(group.versions) ? group.versions.join(', ') : '-'}
                                  </p>
                                </article>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </details>
                  )}
                </section>
              )}

              {confidence && (
                <section className="card" style={{ display: 'grid', gap: 8 }}>
                  <h2 style={{ margin: 0 }}>Confidence Intervals</h2>
                  <p style={{ margin: 0 }}>
                    Evidence: <strong>{confidence.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                  </p>
                  <details>
                    <summary>Interval Details</summary>
                    <div style={{ overflowX: 'auto', marginTop: 10 }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Metric</th>
                            <th>Point Δ</th>
                            <th>CI Low</th>
                            <th>CI High</th>
                            <th>Samples</th>
                            <th>Interpretation</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(confidence.intervals ?? []).map((interval) => (
                            <tr key={String(interval.key ?? interval.label ?? 'interval')}>
                              <td>{String(interval.label ?? interval.key ?? '-')}</td>
                              <td>{formatSigned(toFiniteNumber(interval.point_estimate), 3)}</td>
                              <td>{formatNumber(toFiniteNumber(interval.lower), 3)}</td>
                              <td>{formatNumber(toFiniteNumber(interval.upper), 3)}</td>
                              <td>
                                {(toFiniteNumber(interval.current_samples) ?? 0).toString()}/
                                {(toFiniteNumber(interval.baseline_samples) ?? 0).toString()}
                              </td>
                              <td>{String(interval.interpretation ?? '-')}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </details>
                  {(confidence.recommended_actions ?? []).length > 0 && (
                    <ul style={{ margin: 0 }}>
                      {(confidence.recommended_actions ?? []).map((action) => (
                        <li key={action}>{action}</li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              {patterns?.evidence_sufficient && (
                <section className="card" style={{ display: 'grid', gap: 10 }}>
                  <h2 style={{ margin: 0 }}>Pattern Extraction</h2>
                  <p style={{ margin: 0 }}>{String(patterns.headline ?? '-')}</p>
                  {(patterns.signals ?? []).length > 0 && (
                    <details>
                      <summary>Detected Signals ({(patterns.signals ?? []).length})</summary>
                      <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
                        {(patterns.signals ?? []).map((signal) => {
                          const severity = String(signal.severity ?? 'info')
                          const severityClass =
                            severity === 'high'
                              ? 'pattern-signal-high'
                              : severity === 'warn'
                                ? 'pattern-signal-warn'
                                : 'pattern-signal-info'
                          return (
                            <article
                              key={String(signal.code ?? signal.title ?? 'signal')}
                              className={`card pattern-signal-card ${severityClass}`}
                              style={{ padding: 12 }}
                            >
                              <p style={{ marginTop: 0, marginBottom: 6 }}>
                                <strong>{String(signal.title ?? signal.code ?? 'Signal')}</strong>{' '}
                                <span className="pattern-signal-meta" style={{ fontSize: 12 }}>
                                  ({String(signal.confidence ?? 'unknown')} confidence)
                                </span>
                              </p>
                              <p style={{ margin: '0 0 6px', fontSize: 13 }}>{String(signal.evidence ?? '')}</p>
                              <p style={{ margin: 0, fontSize: 13 }}>{String(signal.next_action ?? '')}</p>
                            </article>
                          )
                        })}
                      </div>
                    </details>
                  )}
                </section>
              )}

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Feedback</h2>
                <p style={{ marginTop: 0, marginBottom: 8, color: '#546b8a' }}>
                  Report dashboard bugs/features with policy+tab context prefilled.
                </p>
                <a href={feedbackUrl} target="_blank" rel="noreferrer">
                  Open dashboard feedback issue
                </a>
              </section>
            </>
          )}

          {activeTab === 'analysis' && (
            <section className="card">
              <div className="dashboard-title-line" style={{ marginBottom: 10 }}>
                <h2 style={{ margin: 0 }}>Analysis</h2>
                <span className="dashboard-title-subline">
                  Run diagnostics analysis to generate a natural-language summary.
                </span>
              </div>
              <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
                <label style={{ display: 'grid', gap: 6, maxWidth: 560 }}>
                  Anthropic API key (optional, bring your own)
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="sk-ant-..."
                    value={analysisApiKey}
                    onChange={(event) => setAnalysisApiKey(event.target.value)}
                  />
                </label>
                <p style={{ margin: 0, fontSize: 12, color: '#4b617f' }}>
                  Key is sent only with this analysis request as <code>X-Anthropic-Api-Key</code>; it is not persisted.
                </p>
                <div>
                  <button
                    type="button"
                    onClick={onRunAnalysis}
                    disabled={analysisLoading || loading || !policyVersionId.trim() || !data}
                  >
                    {analysis ? 'Re-run diagnostics analysis' : 'Run diagnostics analysis'}
                  </button>
                </div>
              </div>
              {analysisError && (
                <div className="card" style={{ padding: 12, borderColor: '#fecdca', background: '#fff7f6' }}>
                  <p style={{ marginTop: 0, marginBottom: 6, color: '#b42318' }}>
                    <strong>Analysis unavailable:</strong> {analysisError}
                  </p>
                  {isAnalysisKeyMissingError(analysisError) && (
                    <p style={{ margin: 0, fontSize: 13, color: '#6b2c2c' }}>
                      No shared key is configured for this backend. Bring your own key above, or run your own backend
                      with <code>ANTHROPIC_API_KEY</code> exported.
                    </p>
                  )}
                </div>
              )}
              {!analysis && !analysisLoading && (
                <div style={{ display: 'grid', gap: 8, marginTop: 4 }}>
                  <p style={{ margin: 0, color: '#546b8a' }}>
                    No analysis generated yet for this session. Run the action above when ready.
                  </p>
                </div>
              )}
              {analysisLoading && (
                <AnalysisLoadingQuips
                  policyName={String(data?.policy?.name ?? 'policy')}
                  opponentStats={data?.derived?.opponent_metrics ?? {}}
                />
              )}
              {analysis && (
                <div style={{ display: 'grid', gap: 10 }}>
                  <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
                    <button type="button" onClick={() => setShowAnalysis((value) => !value)}>
                      {showAnalysis ? 'Hide analysis' : 'Show analysis'}
                    </button>
                  </div>
                  <p style={{ margin: 0, fontSize: 12, color: '#4b617f' }}>
                    Data sources: {analysis.data_sources.join(', ') || '-'}
                  </p>
                  {showAnalysis &&
                    (data ? (
                      <AnalysisRichText
                        text={analysis.analysis}
                        episodes={episodes}
                        opponentStats={data.derived.opponent_metrics}
                      />
                    ) : (
                      <div
                        style={{
                          border: '1px solid var(--panel-soft-border)',
                          borderRadius: 10,
                          padding: 12,
                          background: 'var(--panel-soft-bg-1)',
                          whiteSpace: 'pre-wrap',
                        }}
                      >
                        {analysis.analysis}
                      </div>
                    ))}
                </div>
              )}
            </section>
          )}

          {activeTab === 'episodes' && (
            <>
              <section className="card grid" style={{ gap: 10 }}>
                <h2 style={{ marginTop: 0, marginBottom: 2 }}>Filters & Export</h2>
                <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
                  <label style={{ display: 'grid', gap: 6 }}>
                    Status
                    <select
                      value={statusFilter}
                      onChange={(event) => setStatusFilter(event.target.value as EpisodeStatusFilter)}
                    >
                      <option value="all">all</option>
                      <option value="completed">completed</option>
                      <option value="failed">failed</option>
                    </select>
                  </label>
                  <label style={{ display: 'grid', gap: 6 }}>
                    Tag Search
                    <input
                      placeholder="e.g. reward_tier=high"
                      value={tagQuery}
                      onChange={(event) => setTagQuery(event.target.value)}
                    />
                  </label>
                </div>
                <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={replayOnly}
                      onChange={(event) => setReplayOnly(event.target.checked)}
                      style={{ width: 16, height: 16 }}
                    />
                    Replay only
                  </label>
                  <button
                    type="button"
                    onClick={() => {
                      setStatusFilter('all')
                      setReplayOnly(false)
                      setTagQuery('')
                      setEpisodeSort('reward')
                      setEpisodeSortDir('desc')
                    }}
                  >
                    Reset filters
                  </button>
                  <button type="button" onClick={onExportEpisodes}>
                    Export filtered JSON
                  </button>
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: '#4b617f' }}>
                    {sortedEpisodes.length}/{episodes.length} rows • order: {String(data.selection?.ordering ?? 'n/a')}{' '}
                    • limit: {String(data.selection?.limit ?? 'n/a')}
                  </span>
                </div>
              </section>

              <section className="card">
                <h2 style={{ marginTop: 0 }}>
                  Episodes ({sortedEpisodes.length} filtered / {episodes.length} sampled)
                </h2>
                {sortedEpisodes.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No episodes match current filters.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>
                            <button
                              type="button"
                              onClick={() => onEpisodeSort('created_at')}
                              style={SORT_HEADER_BUTTON_STYLE}
                            >
                              Created {episodeSort === 'created_at' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
                            </button>
                          </th>
                          <th>
                            <button
                              type="button"
                              onClick={() => onEpisodeSort('opponent')}
                              style={SORT_HEADER_BUTTON_STYLE}
                            >
                              Opponent {episodeSort === 'opponent' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
                            </button>
                          </th>
                          <th>
                            <button
                              type="button"
                              onClick={() => onEpisodeSort('team')}
                              style={SORT_HEADER_BUTTON_STYLE}
                            >
                              Team {episodeSort === 'team' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
                            </button>
                          </th>
                          <th>
                            <button
                              type="button"
                              onClick={() => onEpisodeSort('reward')}
                              style={SORT_HEADER_BUTTON_STYLE}
                            >
                              Reward {episodeSort === 'reward' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
                            </button>
                          </th>
                          <th>
                            <button
                              type="button"
                              onClick={() => onEpisodeSort('steps')}
                              style={SORT_HEADER_BUTTON_STYLE}
                            >
                              Steps {episodeSort === 'steps' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
                            </button>
                          </th>
                          <th>
                            <button
                              type="button"
                              onClick={() => onEpisodeSort('noop_rate')}
                              style={SORT_HEADER_BUTTON_STYLE}
                            >
                              Noop % {episodeSort === 'noop_rate' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
                            </button>
                          </th>
                          <th>Status</th>
                          <th>Replay</th>
                          <th>Diagnostics</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sortedEpisodes.slice(0, 200).map((episode) => {
                          const id = String(
                            episode.episode_id ?? episode.id ?? `${episode.job_id ?? 'ep'}-${episode.created_at ?? ''}`
                          )
                          const reward = toFiniteNumber(episode.reward ?? episode.avg_reward)
                          const noop = episodeNoopRate(episode)
                          const tags = asStringArray(episode.diagnostic_tags)
                          return (
                            <tr key={id}>
                              <td>
                                <code>{formatDateTime(episode.created_at)}</code>
                              </td>
                              <td>
                                <span
                                  style={{
                                    display: 'inline-block',
                                    width: 8,
                                    height: 8,
                                    borderRadius: '50%',
                                    background: colorMap[String(episode.opponent_name ?? 'unknown')] ?? '#94a3b8',
                                    marginRight: 6,
                                  }}
                                />
                                {String(episode.opponent_name ?? '-')}
                                {episode.opponent_version === null || episode.opponent_version === undefined
                                  ? ''
                                  : ` v${episode.opponent_version}`}
                              </td>
                              <td>
                                <code>{String(episode.team_composition ?? '-')}</code>
                              </td>
                              <td>{formatNumber(reward, 3)}</td>
                              <td>{toFiniteNumber(episode.steps) ?? '-'}</td>
                              <td>{(noop * 100).toFixed(1)}%</td>
                              <td>{String(episode.status ?? '-')}</td>
                              <td>
                                {episode.replay_url ? (
                                  <a href={String(episode.replay_url)} target="_blank" rel="noreferrer">
                                    Open
                                  </a>
                                ) : (
                                  '-'
                                )}
                              </td>
                              <td style={{ maxWidth: 360 }}>{tags.join(', ') || '-'}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                    {sortedEpisodes.length > 200 && (
                      <p style={{ marginTop: 10, marginBottom: 0, fontSize: 12, color: '#4b617f' }}>
                        Showing first 200 rows of {sortedEpisodes.length} filtered episodes.
                      </p>
                    )}
                  </div>
                )}
              </section>
            </>
          )}

          {activeTab === 'opponents' && (
            <>
              <section className="grid two">
                <article className="card">
                  <h2 style={{ marginTop: 0 }}>Best Matchup</h2>
                  {bestWorstOpponents?.best ? (
                    <p style={{ marginBottom: 0 }}>
                      <strong>{bestWorstOpponents.best.opponent}</strong> (avg reward{' '}
                      {formatNumber(bestWorstOpponents.best.avgReward, 3)})
                    </p>
                  ) : (
                    <p style={{ marginBottom: 0 }}>No matchup reward data yet.</p>
                  )}
                </article>
                <article className="card">
                  <h2 style={{ marginTop: 0 }}>Worst Matchup</h2>
                  {bestWorstOpponents?.worst ? (
                    <p style={{ marginBottom: 0 }}>
                      <strong>{bestWorstOpponents.worst.opponent}</strong> (avg reward{' '}
                      {formatNumber(bestWorstOpponents.worst.avgReward, 3)})
                    </p>
                  ) : (
                    <p style={{ marginBottom: 0 }}>No matchup reward data yet.</p>
                  )}
                </article>
              </section>

              {matchup && (
                <section className="card" style={{ display: 'grid', gap: 10 }}>
                  <h2 style={{ margin: 0 }}>Matchup Diagnosis</h2>
                  <p style={{ margin: 0 }}>{String(matchup.reason ?? '-')}</p>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                    <div className="card" style={{ padding: 10 }}>
                      Current avg reward: <code>{formatNumber(toFiniteNumber(matchup.current_avg_reward), 3)}</code>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Baseline avg reward: <code>{formatNumber(toFiniteNumber(matchup.baseline_avg_reward), 3)}</code>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Global delta: <code>{formatSigned(toFiniteNumber(matchup.global_reward_delta), 3)}</code>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Evidence: <strong>{matchup.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Opponent spread: <code>{formatNumber(toFiniteNumber(matchup.opponent_spread), 3)}</code>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Best/Worst opponent:{' '}
                      <code>
                        {String(matchup.best_opponent ?? '-')} / {String(matchup.worst_opponent ?? '-')}
                      </code>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Composition spread: <code>{formatNumber(toFiniteNumber(matchup.composition_spread), 3)}</code>
                    </div>
                    <div className="card" style={{ padding: 10 }}>
                      Best/Worst composition:{' '}
                      <code>
                        {String(matchup.best_composition ?? '-')} / {String(matchup.worst_composition ?? '-')}
                      </code>
                    </div>
                  </div>
                </section>
              )}

              {matchup && asMatchupSlices(matchup.opponent_slices).length > 0 && (
                <section className="card">
                  <h2 style={{ marginTop: 0 }}>Matchup Slices (Current vs Baseline)</h2>
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Opponent</th>
                          <th>Current Avg</th>
                          <th>Baseline Avg</th>
                          <th>Delta vs Baseline</th>
                          <th>Delta vs Policy</th>
                        </tr>
                      </thead>
                      <tbody>
                        {asMatchupSlices(matchup.opponent_slices).map((slice) => (
                          <tr key={String(slice.key ?? 'slice')}>
                            <td>{String(slice.key ?? '-')}</td>
                            <td>
                              {formatNumber(toFiniteNumber(slice.avg_reward), 2)} ({toFiniteNumber(slice.count) ?? 0})
                            </td>
                            <td>
                              {slice.baseline_avg_reward === null || slice.baseline_avg_reward === undefined
                                ? '-'
                                : `${formatNumber(slice.baseline_avg_reward, 2)} (${toFiniteNumber(slice.baseline_count) ?? 0})`}
                            </td>
                            <td>{formatSigned(toFiniteNumber(slice.delta_vs_baseline), 2)}</td>
                            <td>{formatSigned(toFiniteNumber(slice.delta_vs_policy), 2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              {matchup && asMatchupSlices(matchup.composition_slices).length > 0 && (
                <section className="card">
                  <h2 style={{ marginTop: 0 }}>Composition Slices</h2>
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Composition</th>
                          <th>Current Avg</th>
                          <th>Baseline Avg</th>
                          <th>Delta vs Baseline</th>
                          <th>Delta vs Policy</th>
                        </tr>
                      </thead>
                      <tbody>
                        {asMatchupSlices(matchup.composition_slices).map((slice) => (
                          <tr key={String(slice.key ?? 'comp')}>
                            <td>
                              <code>{String(slice.key ?? '-')}</code>
                            </td>
                            <td>
                              {formatNumber(toFiniteNumber(slice.avg_reward), 2)} ({toFiniteNumber(slice.count) ?? 0})
                            </td>
                            <td>
                              {slice.baseline_avg_reward === null || slice.baseline_avg_reward === undefined
                                ? '-'
                                : `${formatNumber(slice.baseline_avg_reward, 2)} (${toFiniteNumber(slice.baseline_count) ?? 0})`}
                            </td>
                            <td>{formatSigned(toFiniteNumber(slice.delta_vs_baseline), 2)}</td>
                            <td>{formatSigned(toFiniteNumber(slice.delta_vs_policy), 2)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Opponent Breakdown</h2>
                {opponentRows.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No opponent metrics available.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Opponent</th>
                          <th>Games</th>
                          <th>Completed</th>
                          <th>Avg Reward</th>
                          <th>Total Reward</th>
                          <th>Win Rate</th>
                          <th>Agg</th>
                          <th>Def</th>
                          <th>Res</th>
                          <th>Jnc</th>
                          <th>Mob</th>
                          <th>Top Profile</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {opponentRows.map((row) => (
                          <tr key={row.opponent}>
                            <td>
                              <span
                                style={{
                                  display: 'inline-block',
                                  width: 8,
                                  height: 8,
                                  borderRadius: '50%',
                                  background: colorMap[row.opponent] ?? '#94a3b8',
                                  marginRight: 6,
                                }}
                              />
                              {row.opponent}
                            </td>
                            <td>{row.count}</td>
                            <td>{row.completed}</td>
                            <td>{formatNumber(row.avgReward, 2)}</td>
                            <td>{formatNumber(row.totalReward, 2)}</td>
                            <td>{formatPercent(row.winRate, 0)}</td>
                            <td>{formatNumber(toFiniteNumber(row.strategyProfile?.aggressive), 0)}</td>
                            <td>{formatNumber(toFiniteNumber(row.strategyProfile?.defensive), 0)}</td>
                            <td>{formatNumber(toFiniteNumber(row.strategyProfile?.resource_hoarder), 0)}</td>
                            <td>{formatNumber(toFiniteNumber(row.strategyProfile?.junction_hunter), 0)}</td>
                            <td>{formatNumber(toFiniteNumber(row.strategyProfile?.mobile_scout), 0)}</td>
                            <td>{row.bestProfile ?? '-'}</td>
                            <td>{row.source}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}

          {activeTab === 'health' && (
            <>
              <section
                className="grid"
                style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}
              >
                <KPIStatCard
                  label="Failed Episodes"
                  value={String(toFiniteNumber(failures.failed_episodes) ?? 0)}
                  detail={`${formatPercent(toFiniteNumber(failures.failed_rate), 1)} of sampled episodes`}
                  severity={kpiSeverity(toFiniteNumber(failures.failed_rate), 0.03, 0.1, false)}
                />
                <KPIStatCard
                  label="Timeout Failures"
                  value={String(toFiniteNumber(failures.timeout_failures) ?? 0)}
                  severity={(toFiniteNumber(failures.timeout_failures) ?? 0) > 0 ? 'bad' : 'good'}
                />
                <KPIStatCard
                  label="OOM Failures"
                  value={String(toFiniteNumber(failures.oom_failures) ?? 0)}
                  severity={(toFiniteNumber(failures.oom_failures) ?? 0) > 0 ? 'bad' : 'good'}
                />
                <KPIStatCard
                  label="Crash/Other"
                  value={String(
                    (toFiniteNumber(failures.crash_failures) ?? 0) + (toFiniteNumber(failures.other_failures) ?? 0)
                  )}
                  detail={`${String(toFiniteNumber(failures.crash_failures) ?? 0)} crash + ${String(toFiniteNumber(failures.other_failures) ?? 0)} other`}
                  severity={
                    (toFiniteNumber(failures.crash_failures) ?? 0) + (toFiniteNumber(failures.other_failures) ?? 0) > 0
                      ? 'bad'
                      : 'good'
                  }
                />
                <KPIStatCard
                  label="Freeze-Heavy"
                  value={String(toFiniteNumber(failures.freeze_heavy_completed) ?? 0)}
                  severity={(toFiniteNumber(failures.freeze_heavy_completed) ?? 0) > 0 ? 'warn' : 'good'}
                />
                <KPIStatCard
                  label="Noop-Heavy"
                  value={String(toFiniteNumber(failures.noop_heavy_completed) ?? 0)}
                  severity={(toFiniteNumber(failures.noop_heavy_completed) ?? 0) > 0 ? 'warn' : 'good'}
                />
              </section>

              {(statsInventory || topTagStats.length > 0) && (
                <section className="card" style={{ display: 'grid', gap: 10 }}>
                  <h2 style={{ margin: 0 }}>Tag + Instrumentation Inventory</h2>
                  {statsInventory && (
                    <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', fontSize: 13 }}>
                      <span>
                        Distinct metrics:{' '}
                        <code>{String(toFiniteNumber(statsInventory.distinct_metric_keys) ?? 0)}</code>
                      </span>
                      <span>
                        Distinct tags: <code>{String(toFiniteNumber(statsInventory.distinct_tag_keys) ?? 0)}</code>
                      </span>
                      <span>
                        Episodes:{' '}
                        <code>{String(toFiniteNumber(statsInventory.total_episodes) ?? episodes.length)}</code>
                      </span>
                    </div>
                  )}
                  {topTagStats.length > 0 ? (
                    <div style={{ overflowX: 'auto' }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Behavior Slice (Tag)</th>
                            <th>Count</th>
                            <th>Coverage</th>
                          </tr>
                        </thead>
                        <tbody>
                          {topTagStats.map((row) => (
                            <tr key={row.tag}>
                              <td>
                                <code>{row.tag}</code>
                              </td>
                              <td>{row.count}</td>
                              <td>{formatPercent(row.coverage, 0)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p style={{ margin: 0 }}>No diagnostic/raw tags found in sampled episodes.</p>
                  )}
                  {(statsInventory?.notes ?? []).length > 0 && (
                    <ul style={{ margin: 0 }}>
                      {(statsInventory?.notes ?? []).map((note) => (
                        <li key={note}>{note}</li>
                      ))}
                    </ul>
                  )}
                </section>
              )}

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Failed Episodes ({failedEpisodes.length})</h2>
                {failedEpisodes.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No failed episodes in the sampled data.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Job ID</th>
                          <th>Error Type</th>
                          <th>Error Message</th>
                          <th>Opponent</th>
                          <th>Team</th>
                          <th>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {failedEpisodes.map((episode) => {
                          const key = String(
                            episode.episode_id ??
                              episode.id ??
                              episode.job_id ??
                              `${episode.opponent_name ?? 'unknown'}-${episode.created_at ?? 'na'}-${episode.team_composition ?? 'na'}`
                          )
                          return (
                            <tr key={key}>
                              <td>
                                <code>{String(episode.job_id ?? '-')}</code>
                              </td>
                              <td>{String(episode.error_type ?? 'unknown')}</td>
                              <td>{String(episode.error_message ?? '-')}</td>
                              <td>{String(episode.opponent_name ?? '-')}</td>
                              <td>
                                <code>{String(episode.team_composition ?? '-')}</code>
                              </td>
                              <td>{formatDateTime(episode.created_at)}</td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {data.derived?.crash_dump && (
                <section className="card" style={{ display: 'grid', gap: 10 }}>
                  <h2 style={{ margin: 0 }}>Crash Dump Report</h2>
                  <p style={{ margin: 0 }}>{String(data.derived.crash_dump.headline ?? '-')}</p>

                  {(data.derived.crash_dump.signatures ?? []).length > 0 && (
                    <div
                      style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8 }}
                    >
                      {(data.derived.crash_dump.signatures ?? []).map((signature) => (
                        <article
                          key={String(signature.signature ?? signature.error_type ?? 'signature')}
                          className="card"
                          style={{ padding: 10 }}
                        >
                          <p style={{ marginTop: 0, marginBottom: 6 }}>
                            <strong>{String(signature.error_type ?? 'unknown')}</strong> ({String(signature.count ?? 0)}
                            )
                          </p>
                          <p style={{ margin: 0, fontSize: 12 }}>{String(signature.example_message ?? '-')}</p>
                        </article>
                      ))}
                    </div>
                  )}

                  {(data.derived.crash_dump.entries ?? []).length > 0 && (
                    <div style={{ overflowX: 'auto' }}>
                      <table>
                        <thead>
                          <tr>
                            <th>Job</th>
                            <th>Type</th>
                            <th>Message</th>
                            <th>Analyze Command</th>
                            <th>Replay</th>
                          </tr>
                        </thead>
                        <tbody>
                          {(data.derived.crash_dump.entries ?? []).map((entry) => (
                            <tr key={String(entry.episode_id ?? entry.job_id ?? 'entry')}>
                              <td>
                                <code>{String(entry.job_id ?? '-')}</code>
                              </td>
                              <td>{String(entry.error_type ?? 'unknown')}</td>
                              <td>{String(entry.error_message ?? '-')}</td>
                              <td>
                                <code>{String(entry.analysis_command ?? '-')}</code>
                              </td>
                              <td>
                                {entry.replay_url ? (
                                  <a href={String(entry.replay_url)} target="_blank" rel="noreferrer">
                                    Open
                                  </a>
                                ) : (
                                  '-'
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </section>
              )}
            </>
          )}

          {activeTab === 'roles' && (
            <RolePercentilesPanel roleData={rolePercentiles} loading={roleLoading} error={roleError} />
          )}
          {activeTab === 'capabilities' && (
            <SkillTreePanel data={data} diagnoseNote={diagnoseNote} diagnoseManifest={diagnoseManifest} />
          )}
          {activeTab === 'cogames_diagnose' && (
            <CogamesDiagnosePanel
              runs={diagnoseRuns}
              loading={diagnoseLoading}
              error={diagnoseError}
              selectedRunId={selectedDiagnoseRunId}
              onSelectRun={setSelectedDiagnoseRunId}
              note={diagnoseNote}
              noteLoading={diagnoseNoteLoading}
              noteError={diagnoseNoteError}
              manifest={diagnoseManifest}
              replayLookupByRef={replayLookupByRef}
              policyVersionId={data?.policy?.id ? String(data.policy.id) : null}
            />
          )}
        </>
      )}
    </main>
  )
}
