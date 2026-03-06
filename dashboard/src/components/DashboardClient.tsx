'use client'

import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'

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
  type DashboardRoleMetricDef,
  type DashboardRolePercentilesResponse,
  type DashboardStatsInventorySummary,
  type DashboardTrendExplorerSummary,
  type DashboardTrendPoint,
  type DashboardTrendSummary,
  type DashboardUnsupportedSummary,
  type DiagnoseDoctorNote,
  type DiagnoseManifest,
  type DiagnoseRunSummary,
  type PantheonStory,
  fetchDiagnoseDoctorNote,
  fetchDiagnoseManifest,
  fetchDiagnoseRuns,
  fetchDashboardAnalysis,
  fetchDashboardData,
  fetchDashboardDefaultData,
  fetchDashboardRolePercentiles,
  fetchPantheonStories,
} from '../lib/api'
import { AnalysisLoadingQuips, AnalysisRichText } from './AnalysisRichText'
import { RolePercentilesPanel } from './RolePercentilesPanel'
import { SkillTreePanel } from './SkillTreePanel'

type DashboardTab = 'overview' | 'performance' | 'coordination' | 'capabilities' | 'pantheon'

type EpisodeStatusFilter = 'all' | 'completed' | 'failed'
type EpisodeSortKey = 'created_at' | 'opponent' | 'team' | 'reward' | 'steps' | 'noop_rate'
type SortDir = 'asc' | 'desc'

const DASHBOARD_TABS: DashboardTab[] = ['overview', 'capabilities', 'coordination', 'performance']

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

const METTASCOPE_REPLAY_URL_PREFIX = 'https://metta-ai.github.io/metta/mettascope/mettascope.html?replay='
const OVERVIEW_TREND_CHART_WIDTH = 560
const OVERVIEW_TREND_CHART_HEIGHT = 200
const OVERVIEW_PARSE_ROLES = ['aligner', 'miner', 'scrambler', 'scout'] as const
const OVERVIEW_PARSE_ROLE_LABELS: Record<string, string> = {
  aligner: 'Aligner',
  miner: 'Miner',
  scrambler: 'Scrambler',
  scout: 'Scout',
}
const OVERVIEW_PARSE_PRIORITY_METRICS: Record<(typeof OVERVIEW_PARSE_ROLES)[number], string[]> = {
  aligner: ['junction.aligned'],
  miner: ['germanium.deposited', 'silicon.deposited', 'carbon.deposited', 'oxygen.deposited'],
  scrambler: ['junction.scrambled'],
  scout: ['cell.visited'],
}
const PANTHEON_HALLS = ['fame', 'same', 'lame'] as const
const PANTHEON_HALL_LABELS: Record<(typeof PANTHEON_HALLS)[number], string> = {
  fame: 'Hall of Fame',
  same: 'Hall of Same',
  lame: 'Hall of Lame',
}

const DASHBOARD_FEEDBACK_ISSUE_URL = 'https://github.com/Metta-AI/metta/issues/new'
const DEFAULT_DASHBOARD_CACHE_KEY = '__default__'
const MAX_DASHBOARD_CACHE_ENTRIES = 6
const MAX_PERSISTED_DASHBOARD_CACHE_ENTRIES = 2
const DASHBOARD_PERSISTED_CACHE_STORAGE_KEY = 'policy-dashboard-response-cache:v1'
const ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY = 'policy-dashboard-role-percentiles-cache:v1'
const DASHBOARD_CACHE_TTL_MS = 30 * 60 * 1000
const dashboardResponseCache = new Map<string, DashboardResponse>()
const rolePercentilesCache = new Map<string, DashboardRolePercentilesResponse>()
const rolePercentilesInflightRequests = new Map<string, Promise<DashboardRolePercentilesResponse>>()
let dashboardCacheHydratedFromStorage = false
let rolePercentilesCacheHydratedFromStorage = false

type PersistedDashboardCacheEntry = {
  policyVersionId: string
  response: DashboardResponse
  isDefault?: boolean
}

type PersistedDashboardCachePayload = {
  version: 1
  apiBaseUrl: string
  savedAtMs: number
  entries: PersistedDashboardCacheEntry[]
}

type PersistedRolePercentilesCacheEntry = {
  cacheKey: string
  response: DashboardRolePercentilesResponse
}

type PersistedRolePercentilesCachePayload = {
  version: 1
  apiBaseUrl: string
  savedAtMs: number
  entries: PersistedRolePercentilesCacheEntry[]
}

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

type ReplaySpotlightMode = 'selected' | 'worst' | 'median' | 'best'
type OverviewTrendMetric = 'reward' | 'noop_rate' | 'steps' | 'resource_gained'
type TrainingFocus = 'mining' | 'aligning' | 'scouting' | 'coordination' | 'scrambling'

type OverviewTrendPoint = {
  id: string
  createdAt: string | null | undefined
  value: number
}

function parseDashboardTab(value: string | null): DashboardTab | null {
  if (!value) return null
  const normalized = value.trim().toLowerCase()
  return DASHBOARD_TABS.includes(normalized as DashboardTab) ? (normalized as DashboardTab) : null
}

function isTypingContextTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  const tagName = target.tagName
  return target.isContentEditable || tagName === 'INPUT' || tagName === 'TEXTAREA' || tagName === 'SELECT'
}

function browserLocalStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  const localStorage = (window as Window & { localStorage?: unknown }).localStorage as Partial<Storage> | undefined
  if (
    !localStorage ||
    typeof localStorage.getItem !== 'function' ||
    typeof localStorage.setItem !== 'function' ||
    typeof localStorage.removeItem !== 'function'
  ) {
    return null
  }
  return localStorage as Storage
}

function storageGetItem(key: string): string | null {
  const localStorage = browserLocalStorage()
  if (!localStorage) return null
  return localStorage.getItem(key)
}

function storageSetItem(key: string, value: string): void {
  const localStorage = browserLocalStorage()
  if (!localStorage) return
  localStorage.setItem(key, value)
}

function storageRemoveItem(key: string): void {
  const localStorage = browserLocalStorage()
  if (!localStorage) return
  localStorage.removeItem(key)
}

function cacheDashboardResponse(response: DashboardResponse, isDefault: boolean = false): void {
  hydrateDashboardCacheFromStorage()
  const policyVersionId = String(response.policy?.id ?? '').trim()
  if (!policyVersionId) return
  if (dashboardResponseCache.has(policyVersionId)) {
    dashboardResponseCache.delete(policyVersionId)
  }
  dashboardResponseCache.set(policyVersionId, response)
  if (isDefault) {
    dashboardResponseCache.set(DEFAULT_DASHBOARD_CACHE_KEY, response)
  }

  const nonDefaultKeys = [...dashboardResponseCache.keys()].filter((key) => key !== DEFAULT_DASHBOARD_CACHE_KEY)
  while (nonDefaultKeys.length > MAX_DASHBOARD_CACHE_ENTRIES) {
    const oldestKey = nonDefaultKeys.shift()
    if (!oldestKey) break
    dashboardResponseCache.delete(oldestKey)
  }

  persistDashboardCacheToStorage()
}

function getCachedDashboardResponse(policyVersionId: string): DashboardResponse | null {
  hydrateDashboardCacheFromStorage()
  return dashboardResponseCache.get(policyVersionId) ?? null
}

function getCachedDefaultDashboardResponse(): DashboardResponse | null {
  hydrateDashboardCacheFromStorage()
  return dashboardResponseCache.get(DEFAULT_DASHBOARD_CACHE_KEY) ?? null
}

function hydrateDashboardCacheFromStorage(): void {
  if (dashboardCacheHydratedFromStorage) return
  dashboardCacheHydratedFromStorage = true
  if (typeof window === 'undefined') return

  try {
    const raw = storageGetItem(DASHBOARD_PERSISTED_CACHE_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<PersistedDashboardCachePayload>
    if (parsed.version !== 1 || parsed.apiBaseUrl !== DASHBOARD_API_BASE_URL || !Array.isArray(parsed.entries)) {
      storageRemoveItem(DASHBOARD_PERSISTED_CACHE_STORAGE_KEY)
      return
    }
    if (Date.now() - Number(parsed.savedAtMs ?? 0) > DASHBOARD_CACHE_TTL_MS) {
      storageRemoveItem(DASHBOARD_PERSISTED_CACHE_STORAGE_KEY)
      return
    }

    for (const entry of parsed.entries) {
      const policyVersionId = String(entry?.policyVersionId ?? '').trim()
      if (!policyVersionId || !entry?.response || typeof entry.response !== 'object') continue
      dashboardResponseCache.set(policyVersionId, entry.response)
      if (entry.isDefault) {
        dashboardResponseCache.set(DEFAULT_DASHBOARD_CACHE_KEY, entry.response)
      }
    }

    const nonDefaultKeys = [...dashboardResponseCache.keys()].filter((key) => key !== DEFAULT_DASHBOARD_CACHE_KEY)
    while (nonDefaultKeys.length > MAX_DASHBOARD_CACHE_ENTRIES) {
      const oldestKey = nonDefaultKeys.shift()
      if (!oldestKey) break
      dashboardResponseCache.delete(oldestKey)
    }
  } catch {
    storageRemoveItem(DASHBOARD_PERSISTED_CACHE_STORAGE_KEY)
  }
}

function persistDashboardCacheToStorage(): void {
  if (typeof window === 'undefined') return

  const nonDefaultKeys = [...dashboardResponseCache.keys()]
    .filter((key) => key !== DEFAULT_DASHBOARD_CACHE_KEY)
    .slice(-MAX_PERSISTED_DASHBOARD_CACHE_ENTRIES)
  const entries: PersistedDashboardCacheEntry[] = []
  for (const key of nonDefaultKeys) {
    const response = dashboardResponseCache.get(key)
    if (!response) continue
    entries.push({ policyVersionId: key, response })
  }

  const defaultResponse = dashboardResponseCache.get(DEFAULT_DASHBOARD_CACHE_KEY)
  if (defaultResponse) {
    const defaultPolicyVersionId = String(defaultResponse.policy?.id ?? '').trim()
    if (defaultPolicyVersionId) {
      const existingEntry = entries.find((entry) => entry.policyVersionId === defaultPolicyVersionId)
      if (existingEntry) {
        existingEntry.isDefault = true
      } else {
        entries.push({ policyVersionId: defaultPolicyVersionId, response: defaultResponse, isDefault: true })
      }
    }
  }

  if (entries.length === 0) {
    storageRemoveItem(DASHBOARD_PERSISTED_CACHE_STORAGE_KEY)
    return
  }

  const payload: PersistedDashboardCachePayload = {
    version: 1,
    apiBaseUrl: DASHBOARD_API_BASE_URL,
    savedAtMs: Date.now(),
    entries,
  }

  try {
    storageSetItem(DASHBOARD_PERSISTED_CACHE_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // Best-effort cache only: ignore quota/storage errors.
  }
}

function rolePercentilesCacheKey(policyVersionIdRaw: string, generatedAtRaw: string | null | undefined): string | null {
  const policyVersionId = policyVersionIdRaw.trim()
  if (!policyVersionId) return null
  const generatedAt = typeof generatedAtRaw === 'string' ? generatedAtRaw.trim() : ''
  return generatedAt ? `${policyVersionId}:${generatedAt}` : policyVersionId
}

function hydrateRolePercentilesCacheFromStorage(): void {
  if (rolePercentilesCacheHydratedFromStorage) return
  rolePercentilesCacheHydratedFromStorage = true
  if (typeof window === 'undefined') return

  try {
    const raw = storageGetItem(ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as Partial<PersistedRolePercentilesCachePayload>
    if (parsed.version !== 1 || parsed.apiBaseUrl !== DASHBOARD_API_BASE_URL || !Array.isArray(parsed.entries)) {
      storageRemoveItem(ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY)
      return
    }
    if (Date.now() - Number(parsed.savedAtMs ?? 0) > DASHBOARD_CACHE_TTL_MS) {
      storageRemoveItem(ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY)
      return
    }

    for (const entry of parsed.entries) {
      const cacheKey = String(entry?.cacheKey ?? '').trim()
      if (!cacheKey || !entry?.response || typeof entry.response !== 'object') continue
      rolePercentilesCache.set(cacheKey, entry.response)
    }
  } catch {
    storageRemoveItem(ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY)
  }
}

function persistRolePercentilesCacheToStorage(): void {
  if (typeof window === 'undefined') return

  const entries = [...rolePercentilesCache.entries()]
    .slice(-MAX_DASHBOARD_CACHE_ENTRIES)
    .map(([cacheKey, response]) => ({
      cacheKey,
      response,
    }))

  if (entries.length === 0) {
    storageRemoveItem(ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY)
    return
  }

  const payload: PersistedRolePercentilesCachePayload = {
    version: 1,
    apiBaseUrl: DASHBOARD_API_BASE_URL,
    savedAtMs: Date.now(),
    entries,
  }

  try {
    storageSetItem(ROLE_PERCENTILES_PERSISTED_CACHE_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // Best-effort cache only: ignore quota/storage errors.
  }
}

function getCachedRolePercentiles(cacheKey: string): DashboardRolePercentilesResponse | null {
  hydrateRolePercentilesCacheFromStorage()
  return rolePercentilesCache.get(cacheKey) ?? null
}

function cacheRolePercentiles(cacheKey: string, response: DashboardRolePercentilesResponse): void {
  hydrateRolePercentilesCacheFromStorage()
  if (rolePercentilesCache.has(cacheKey)) {
    rolePercentilesCache.delete(cacheKey)
  }
  rolePercentilesCache.set(cacheKey, response)
  while (rolePercentilesCache.size > MAX_DASHBOARD_CACHE_ENTRIES) {
    const oldestKey = rolePercentilesCache.keys().next().value
    if (!oldestKey) break
    rolePercentilesCache.delete(oldestKey)
  }
  persistRolePercentilesCacheToStorage()
}

function getOrFetchRolePercentiles(
  cacheKey: string,
  policyVersionId: string
): Promise<DashboardRolePercentilesResponse> {
  const cached = getCachedRolePercentiles(cacheKey)
  if (cached) return Promise.resolve(cached)

  const inFlight = rolePercentilesInflightRequests.get(cacheKey)
  if (inFlight) return inFlight

  const request = fetchDashboardRolePercentiles(policyVersionId)
    .then((response) => {
      cacheRolePercentiles(cacheKey, response)
      return response
    })
    .finally(() => {
      rolePercentilesInflightRequests.delete(cacheKey)
    })
  rolePercentilesInflightRequests.set(cacheKey, request)
  return request
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

function sortDiagnoseRuns(runs: DiagnoseRunSummary[]): DiagnoseRunSummary[] {
  return [...runs].sort((left, right) => {
    const byCreatedAt = manifestTimestamp(right.manifest) - manifestTimestamp(left.manifest)
    if (byCreatedAt !== 0) return byCreatedAt
    return right.run_id.localeCompare(left.run_id)
  })
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

function episodeIdentifier(episode: DashboardEpisode): string {
  return String(episode.episode_id ?? episode.id ?? `${episode.job_id ?? 'ep'}-${episode.created_at ?? ''}`)
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

function kpiSeverityBandDetail(
  value: number | null,
  goodThreshold: number,
  badThreshold: number,
  higherIsBetter: boolean,
  formatThreshold: (threshold: number) => string
): string {
  if (value === null) return 'threshold context unavailable (missing value)'
  const good = formatThreshold(goodThreshold)
  const bad = formatThreshold(badThreshold)
  if (higherIsBetter) {
    if (value >= goodThreshold) return `green: at or above ${good}`
    if (value <= badThreshold) return `red: at or below ${bad}`
    return `yellow: between ${bad} and ${good}`
  }
  if (value <= goodThreshold) return `green: at or below ${good}`
  if (value >= badThreshold) return `red: at or above ${bad}`
  return `yellow: between ${good} and ${bad}`
}

export function percentileRank(value: number | null, sample: number[]): number | null {
  if (value === null || sample.length === 0) return null
  let lessOrEqual = 0
  let finiteCount = 0
  for (const entry of sample) {
    if (!Number.isFinite(entry)) continue
    finiteCount += 1
    if (entry <= value) lessOrEqual += 1
  }
  if (finiteCount === 0) return null
  if (lessOrEqual === 0) return 0
  return (lessOrEqual / finiteCount) * 100
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

function parsePercentilePillStyle(percentile: number | null): CSSProperties {
  if (percentile === null) return severityStyle('warn')
  if (percentile >= 90) return severityStyle('good')
  if (percentile >= 70) {
    return {
      borderColor: 'var(--signal-info-border)',
      background: 'var(--signal-info-bg)',
    }
  }
  if (percentile >= 40) return severityStyle('warn')
  return severityStyle('bad')
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

function normalizeReplayUrl(replayUrl: string | null | undefined): string | null {
  if (!replayUrl) return null
  if (replayUrl.startsWith(METTASCOPE_REPLAY_URL_PREFIX)) return replayUrl
  return `${METTASCOPE_REPLAY_URL_PREFIX}${replayUrl}`
}

function episodeResourceGained(episode: DashboardEpisode): number {
  const candidates = [
    metricNumber(episode, 'resource.gained'),
    metricNumber(episode, 'resource.total_gained'),
    metricNumber(episode, 'resources.gained'),
  ]
  return Math.max(...candidates, 0)
}

function buildOverviewTrendPoints(episodes: DashboardEpisode[], metric: OverviewTrendMetric): OverviewTrendPoint[] {
  const points: OverviewTrendPoint[] = []
  for (const episode of episodes) {
    let value: number | null = null
    if (metric === 'reward') value = toFiniteNumber(episode.reward ?? episode.avg_reward)
    if (metric === 'noop_rate') value = episodeNoopRate(episode)
    if (metric === 'steps') value = toFiniteNumber(episode.steps)
    if (metric === 'resource_gained') value = episodeResourceGained(episode)
    if (value === null) continue
    points.push({
      id: episodeIdentifier(episode),
      createdAt: episode.created_at,
      value,
    })
  }

  return points.sort((left, right) => {
    const leftTs = left.createdAt ? Date.parse(left.createdAt) : NaN
    const rightTs = right.createdAt ? Date.parse(right.createdAt) : NaN
    const leftFinite = Number.isFinite(leftTs)
    const rightFinite = Number.isFinite(rightTs)
    if (leftFinite && rightFinite) return leftTs - rightTs
    if (leftFinite) return -1
    if (rightFinite) return 1
    return left.id.localeCompare(right.id)
  })
}

function buildSparklinePath(points: OverviewTrendPoint[], width: number, height: number, pad: number): string {
  if (points.length === 0) return ''
  const values = points.map((point) => point.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = Math.max(max - min, 1e-9)
  const usableWidth = Math.max(width - pad * 2, 1)
  const usableHeight = Math.max(height - pad * 2, 1)

  return points
    .map((point, index) => {
      const x = pad + (points.length === 1 ? usableWidth / 2 : (usableWidth * index) / (points.length - 1))
      const normalizedY = (point.value - min) / span
      const y = height - pad - normalizedY * usableHeight
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

function estimateReplayFocusStep(episode: DashboardEpisode | null): number | null {
  if (!episode) return null
  const steps = toFiniteNumber(episode.steps)
  if (steps === null || steps <= 0) return null
  const tags = asStringArray(episode.diagnostic_tags).join(' ').toLowerCase()
  const lateFocus =
    episode.status === 'failed' || tags.includes('stalled_noop_heavy=true') || tags.includes('freeze_heavy')
  const ratio = lateFocus ? 0.75 : 0.5
  return Math.max(1, Math.round(steps * ratio))
}

function deriveTrainingFocus(kpis: DashboardResponse['derived']['kpis'] | undefined): TrainingFocus {
  if (!kpis) return 'coordination'
  const scores: Record<TrainingFocus, number> = {
    mining: Math.max(
      toFiniteNumber(kpis.resource_retention) ?? 0,
      Math.min((toFiniteNumber(kpis.resource_efficiency_per_step) ?? 0) * 25, 1)
    ),
    aligning: toFiniteNumber(kpis.junction_control_rate) ?? 0,
    scouting: toFiniteNumber(kpis.move_efficiency) ?? 0,
    coordination: Math.max(toFiniteNumber(kpis.reward_consistency) ?? 0, 1 - (toFiniteNumber(kpis.noop_rate) ?? 1)),
    scrambling: Math.max((toFiniteNumber(kpis.profile_aggressive) ?? 0) / 100, 0),
  }

  let weakest: TrainingFocus = 'coordination'
  let weakestScore = Number.POSITIVE_INFINITY
  for (const focus of Object.keys(scores) as TrainingFocus[]) {
    if (scores[focus] < weakestScore) {
      weakestScore = scores[focus]
      weakest = focus
    }
  }
  return weakest
}

function autoTrainingRecipeHint(
  focus: TrainingFocus,
  capabilityCodeAudit: DashboardResponse['derived']['capability_code_audit'] | undefined
): string {
  const capabilityIdByFocus: Record<TrainingFocus, string> = {
    mining: 'mining',
    aligning: 'aligning',
    scouting: 'scouting',
    coordination: 'coordination',
    scrambling: 'scrambling',
  }
  const auditedSource = capabilityCodeAudit?.capabilities?.[capabilityIdByFocus[focus]]?.training_source
  if (typeof auditedSource === 'string' && auditedSource.trim()) return auditedSource

  if (focus === 'mining') return 'recipes/experiment/cogsguard.py::miner'
  if (focus === 'aligning') return 'recipes/experiment/cogsguard.py::aligner'
  if (focus === 'scouting') return 'recipes/experiment/cogsguard.py::scout'
  if (focus === 'scrambling') return 'recipes/experiment/cogsguard.py::scrambler'
  return 'recipes/experiment/coggernaut.py::train'
}

function episodeTagTokens(episode: DashboardEpisode): string[] {
  const tokens = new Set<string>()
  for (const tag of asStringArray(episode.diagnostic_tags)) {
    tokens.add(tag.toLowerCase())
  }
  for (const tag of asStringArray(episode.behavior_tags)) {
    tokens.add(tag.toLowerCase())
  }
  const rawTags = episode.raw_tags
  if (rawTags && typeof rawTags === 'object' && !Array.isArray(rawTags)) {
    for (const [key, value] of Object.entries(rawTags)) {
      tokens.add(`${key}=${String(value)}`.toLowerCase())
    }
  }
  return [...tokens]
}

type TagFilterClause = {
  term: string
  negate: boolean
}

function parseStructuredTagQuery(query: string): TagFilterClause[][] | null {
  const normalized = query.trim().toLowerCase()
  const hasOperators = normalized.includes('&&') || normalized.includes('||')
  const isUnaryNegation = normalized.startsWith('!')
  if (!hasOperators && !isUnaryNegation) return null

  const orGroups = normalized
    .split('||')
    .map((group) => group.trim())
    .filter(Boolean)

  if (orGroups.length === 0) return null

  const parsed = orGroups
    .map((group) =>
      group
        .split('&&')
        .map((rawClause) => rawClause.trim())
        .filter(Boolean)
        .map((rawClause) => {
          const negate = rawClause.startsWith('!')
          const term = negate ? rawClause.slice(1).trim() : rawClause
          return { term, negate }
        })
        .filter((clause) => clause.term.length > 0)
    )
    .filter((group) => group.length > 0)

  return parsed.length > 0 ? parsed : null
}

function normalizeTagTerm(value: string): string {
  return value.toLowerCase().replaceAll('/', '_').replaceAll('-', '_').trim()
}

function matchesTagQuery(episode: DashboardEpisode, query: string): boolean {
  const trimmed = query.trim().toLowerCase()
  if (!trimmed) return true

  const tokens = episodeTagTokens(episode)
  const hasTerm = (term: string) => {
    const normalizedTerm = normalizeTagTerm(term)
    return tokens.some((token) => {
      if (token === term || token.includes(term)) return true
      const normalizedToken = normalizeTagTerm(token)
      return normalizedToken === normalizedTerm || normalizedToken.includes(normalizedTerm)
    })
  }
  const structured = parseStructuredTagQuery(trimmed)
  if (!structured) {
    const normalized = normalizeTagTerm(trimmed)
    return tokens.some((token) => token.includes(trimmed) || normalizeTagTerm(token).includes(normalized))
  }

  return structured.some((group) =>
    group.every((clause) => (clause.negate ? !hasTerm(clause.term) : hasTerm(clause.term)))
  )
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

function asEmbeddedRolePercentiles(value: unknown): DashboardRolePercentilesResponse | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as DashboardRolePercentilesResponse
}

function asEmbeddedDiagnoseRuns(value: unknown): DiagnoseRunSummary[] | null {
  if (!Array.isArray(value)) return null
  return value.filter(
    (entry): entry is DiagnoseRunSummary =>
      !!entry && typeof entry === 'object' && typeof (entry as { run_id?: unknown }).run_id === 'string'
  )
}

function buildDashboardFeedbackUrl(
  payload: {
    policyVersionId: string
    policyLabel: string
    activeTab: string
    dashboardUrl: string
    generatedAt: string
    activeMetric: string | null
    selectedEpisodeId: string | null
    tagQuery: string
  } | null
): string {
  if (!payload) return DASHBOARD_FEEDBACK_ISSUE_URL
  const contextLines = [
    `- Policy version ID: ${payload.policyVersionId}`,
    `- Policy: ${payload.policyLabel}`,
    `- Active tab: ${payload.activeTab}`,
    `- Generated at: ${payload.generatedAt}`,
    `- Dashboard URL: ${payload.dashboardUrl}`,
  ]
  if (payload.activeMetric) contextLines.push(`- Selected metric: ${payload.activeMetric}`)
  if (payload.selectedEpisodeId) contextLines.push(`- Selected episode ID: ${payload.selectedEpisodeId}`)
  if (payload.tagQuery.trim()) contextLines.push(`- Tag query: ${payload.tagQuery.trim()}`)

  const title = `[Policy Dashboard] ${payload.policyLabel} (${payload.policyVersionId})`
  const body = ['## Summary', '<describe the issue or request>', '', '## Dashboard Context', ...contextLines].join('\n')
  return `${DASHBOARD_FEEDBACK_ISSUE_URL}?${new URLSearchParams({ title, body }).toString()}`
}

function KPIStatCard({
  label,
  value,
  detail,
  detailSecondary,
  severity,
}: {
  label: string
  value: string
  detail?: string
  detailSecondary?: string
  severity: 'good' | 'warn' | 'bad'
}) {
  const longValue = value.length > 16
  return (
    <article className="card" style={{ padding: 12, borderWidth: 2, minWidth: 0, ...severityStyle(severity) }}>
      <p
        style={{
          margin: 0,
          fontSize: 12,
          letterSpacing: 0.3,
          textTransform: 'uppercase',
          color: 'var(--kpi-label-ink)',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
        title={label}
      >
        {label}
      </p>
      <p
        style={{
          margin: '6px 0 0',
          fontSize: longValue ? 18 : 24,
          fontWeight: 700,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
        title={value}
      >
        {value}
      </p>
      {detail && (
        <p
          style={{
            margin: '6px 0 0',
            fontSize: 12,
            color: 'var(--kpi-detail-ink)',
            whiteSpace: 'normal',
            overflowWrap: 'anywhere',
            lineHeight: 1.3,
          }}
          title={detail}
        >
          {detail}
        </p>
      )}
      {detailSecondary && (
        <p
          style={{
            margin: '2px 0 0',
            fontSize: 12,
            color: 'var(--kpi-detail-ink)',
            whiteSpace: 'normal',
            overflowWrap: 'anywhere',
            lineHeight: 1.3,
          }}
          title={detailSecondary}
        >
          {detailSecondary}
        </p>
      )}
    </article>
  )
}

export function DashboardClient() {
  const [policyVersionId, setPolicyVersionId] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadProgress, setLoadProgress] = useState(0)
  const [loadLabel, setLoadLabel] = useState('Loading dashboard data.')
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const [analysisApiKey, setAnalysisApiKey] = useState('')
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [analysis, setAnalysis] = useState<DashboardAnalysisResponse | null>(null)
  const [rolePercentiles, setRolePercentiles] = useState<DashboardRolePercentilesResponse | null>(null)
  const [roleLoading, setRoleLoading] = useState(false)
  const [roleError, setRoleError] = useState<string | null>(null)
  const loadProgressIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const loadProgressResetTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview')

  const [statusFilter, setStatusFilter] = useState<EpisodeStatusFilter>('all')
  const [replayOnly, setReplayOnly] = useState(false)
  const [tagQuery, setTagQuery] = useState('')
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(null)
  const [overviewReplayMode, setOverviewReplayMode] = useState<ReplaySpotlightMode>('selected')
  const [isReplayTheaterMode, setIsReplayTheaterMode] = useState(false)
  const [loadedReplaySpotlightUrl, setLoadedReplaySpotlightUrl] = useState<string | null>(null)
  const [overviewTrendMetric, setOverviewTrendMetric] = useState<OverviewTrendMetric>('reward')
  const [autoCommandCopied, setAutoCommandCopied] = useState(false)
  const [episodeSort, setEpisodeSort] = useState<EpisodeSortKey>('reward')
  const [episodeSortDir, setEpisodeSortDir] = useState<SortDir>('desc')
  const replaySpotlightContainerRef = useRef<HTMLDivElement | null>(null)
  const diagnoseRunsCacheRef = useRef<DiagnoseRunSummary[] | null>(null)
  const diagnoseRunsRequestRef = useRef<Promise<DiagnoseRunSummary[]> | null>(null)
  const pantheonStoriesCacheRef = useRef<PantheonStory[] | null>(null)
  const pantheonStoriesRequestRef = useRef<Promise<PantheonStory[]> | null>(null)

  const [selectedTrendMetric, setSelectedTrendMetric] = useState('score')
  const [showAnalysis, setShowAnalysis] = useState(true)
  const [diagnoseRuns, setDiagnoseRuns] = useState<DiagnoseRunSummary[]>([])
  const [selectedDiagnoseRunId, setSelectedDiagnoseRunId] = useState<string | null>(null)
  const [diagnoseManifest, setDiagnoseManifest] = useState<DiagnoseManifest | null>(null)
  const [diagnoseNote, setDiagnoseNote] = useState<DiagnoseDoctorNote | null>(null)
  const [pantheonStories, setPantheonStories] = useState<PantheonStory[]>([])
  const [pantheonLoading, setPantheonLoading] = useState(false)
  const [pantheonError, setPantheonError] = useState<string | null>(null)

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

  const clearLoadProgressTimers = useCallback(() => {
    if (loadProgressIntervalRef.current) {
      clearInterval(loadProgressIntervalRef.current)
      loadProgressIntervalRef.current = null
    }
    if (loadProgressResetTimeoutRef.current) {
      clearTimeout(loadProgressResetTimeoutRef.current)
      loadProgressResetTimeoutRef.current = null
    }
  }, [])

  const beginDashboardLoadProgress = useCallback(
    (label: string) => {
      clearLoadProgressTimers()
      setLoadLabel(label)
      setLoadProgress(8)
      setLoading(true)
      loadProgressIntervalRef.current = setInterval(() => {
        setLoadProgress((current) => {
          if (current >= 92) return current
          if (current < 35) return current + 7
          if (current < 70) return current + 4
          return current + 2
        })
      }, 220)
    },
    [clearLoadProgressTimers]
  )

  const finishDashboardLoadProgress = useCallback(() => {
    clearLoadProgressTimers()
    setLoadProgress(100)
    loadProgressResetTimeoutRef.current = setTimeout(() => {
      setLoading(false)
      setLoadProgress(0)
    }, 180)
  }, [clearLoadProgressTimers])

  useEffect(() => {
    return () => {
      clearLoadProgressTimers()
    }
  }, [clearLoadProgressTimers])

  const loadProgressMessage = useMemo(() => {
    if (!loading) return null
    if (loadProgress < 30) return `${loadLabel} Fetching policy + episode data...`
    if (loadProgress < 70) return `${loadLabel} Computing diagnostics and teammate pairings...`
    return `${loadLabel} Finalizing dashboard view...`
  }, [loadLabel, loadProgress, loading])

  const preloadRolePercentiles = useCallback(
    async (
      policyVersionIdRaw: string,
      generatedAtRaw: string | null | undefined,
      embeddedRolePercentiles: DashboardRolePercentilesResponse | null = null
    ) => {
      const policyVersionId = policyVersionIdRaw.trim()
      if (!policyVersionId) return

      const cacheKey = rolePercentilesCacheKey(policyVersionId, generatedAtRaw)
      if (!cacheKey) return
      if (embeddedRolePercentiles) {
        cacheRolePercentiles(cacheKey, embeddedRolePercentiles)
        setRolePercentiles(embeddedRolePercentiles)
        return
      }
      const cachedPercentiles = getCachedRolePercentiles(cacheKey)
      if (cachedPercentiles) {
        setRolePercentiles(cachedPercentiles)
        return
      }

      try {
        const response = await getOrFetchRolePercentiles(cacheKey, policyVersionId)
        setRolePercentiles(response)
      } catch {
        // Best-effort preload: tab-specific fetch will surface any errors when Coordination is opened.
      }
    },
    []
  )

  const prefetchDiagnoseRuns = useCallback((): Promise<DiagnoseRunSummary[]> => {
    if (diagnoseRunsCacheRef.current) {
      return Promise.resolve(diagnoseRunsCacheRef.current)
    }
    if (diagnoseRunsRequestRef.current) {
      return diagnoseRunsRequestRef.current
    }
    const request = fetchDiagnoseRuns()
      .then((response) => {
        diagnoseRunsCacheRef.current = [...response.runs]
        return diagnoseRunsCacheRef.current
      })
      .finally(() => {
        diagnoseRunsRequestRef.current = null
      })
    diagnoseRunsRequestRef.current = request
    return request
  }, [])

  const prefetchPantheonStories = useCallback((): Promise<PantheonStory[]> => {
    if (pantheonStoriesCacheRef.current) {
      return Promise.resolve(pantheonStoriesCacheRef.current)
    }
    if (pantheonStoriesRequestRef.current) {
      return pantheonStoriesRequestRef.current
    }
    const request = fetchPantheonStories()
      .then((response) => {
        pantheonStoriesCacheRef.current = [...response.stories]
        return pantheonStoriesCacheRef.current
      })
      .finally(() => {
        pantheonStoriesRequestRef.current = null
      })
    pantheonStoriesRequestRef.current = request
    return request
  }, [])

  const episodes = useMemo(() => (Array.isArray(data?.episodes) ? data.episodes : []), [data])
  const completedEpisodes = useMemo(() => episodes.filter((episode) => episode.status === 'completed'), [episodes])
  const failedEpisodes = useMemo(() => episodes.filter((episode) => episode.status === 'failed'), [episodes])

  const diagnostics = useMemo(() => asStringArray(data?.derived?.kpis?.diagnostics), [data])
  const failures = useMemo(() => asFailures(data?.derived?.failures), [data])
  const matchup = useMemo(() => asMatchup(data?.derived?.matchup), [data])
  const matchupCurrentAvgReward = toFiniteNumber(matchup?.current_avg_reward)
  const matchupBaselineAvgReward = toFiniteNumber(matchup?.baseline_avg_reward)
  const matchupGlobalDelta = toFiniteNumber(matchup?.global_reward_delta)
  const matchupOpponentSpread = toFiniteNumber(matchup?.opponent_spread)
  const matchupCompositionSpread = toFiniteNumber(matchup?.composition_spread)
  const matchupOpponentSlices = useMemo(() => asMatchupSlices(matchup?.opponent_slices), [matchup])
  const matchupCompositionSlices = useMemo(() => asMatchupSlices(matchup?.composition_slices), [matchup])
  const matchupCurrentAvgRewardSeverity = kpiSeverity(matchupCurrentAvgReward, 30, 10)
  const matchupBaselineAvgRewardSeverity = kpiSeverity(matchupBaselineAvgReward, 30, 10)
  const matchupGlobalDeltaSeverity = kpiSeverity(matchupGlobalDelta, 5, 0)
  const matchupOpponentSpreadSeverity = kpiSeverity(matchupOpponentSpread, 20, 40, false)
  const matchupCompositionSpreadSeverity = kpiSeverity(matchupCompositionSpread, 12, 24, false)
  const matchupEvidenceSeverity =
    matchup?.evidence_sufficient === true ? 'good' : matchup?.evidence_sufficient === false ? 'bad' : 'warn'
  const trend = useMemo<DashboardTrendSummary | null>(() => {
    if (!data?.derived?.trend || typeof data.derived.trend !== 'object' || Array.isArray(data.derived.trend))
      return null
    return data.derived.trend
  }, [data])
  const trendExplorer = useMemo(() => asTrendExplorer(data?.derived?.trend_explorer), [data])
  const confidence = useMemo(() => asConfidence(data?.derived?.confidence), [data])
  const patterns = useMemo(() => asPattern(data?.derived?.patterns), [data])
  const showConfidenceIntervals = Boolean(confidence)
  const showPatternExtraction = Boolean(patterns?.evidence_sufficient)
  const trendRightColumnCardCount = 1 + (showConfidenceIntervals ? 1 : 0) + (showPatternExtraction ? 1 : 0)
  const unsupported = useMemo(() => asUnsupported(data?.derived?.unsupported), [data])
  const instrumentation = useMemo(() => asInstrumentation(data?.derived?.instrumentation), [data])
  const statsInventory = useMemo(() => asStatsInventory(data?.derived?.stats_inventory), [data])
  const actionSummary = useMemo(() => asActions(data?.derived?.actions), [data])
  const orchestration = useMemo(() => asOrchestration(data?.derived?.orchestration), [data])
  const unsupportedIssues = useMemo(() => unsupported?.issues ?? [], [unsupported])
  const unsupportedIssueCount = unsupportedIssues.length
  const unsupportedErrorCount = useMemo(
    () => unsupportedIssues.filter((issue) => String(issue.severity ?? '').toLowerCase() === 'error').length,
    [unsupportedIssues]
  )
  const instrumentationChecks = useMemo(() => instrumentation?.checks ?? [], [instrumentation])
  const instrumentationKnown = instrumentation !== null
  const instrumentationFailCount = useMemo(
    () =>
      instrumentationChecks.filter((check) => {
        const status = String(check.status ?? '').toLowerCase()
        return status.length > 0 && status !== 'pass' && status !== 'ok' && status !== 'success'
      }).length,
    [instrumentationChecks]
  )
  const dataQualitySeverity: 'good' | 'warn' | 'bad' =
    unsupportedErrorCount > 0
      ? 'bad'
      : !instrumentationKnown ||
          unsupportedIssueCount > 0 ||
          instrumentationFailCount > 0 ||
          instrumentation?.compliant !== true
        ? 'warn'
        : 'good'
  const dataQualityLabel =
    dataQualitySeverity === 'good' ? 'clean' : dataQualitySeverity === 'bad' ? 'blocked' : 'partial'
  const dataQualityDetail = instrumentationKnown
    ? `${unsupportedIssueCount} issues · ${instrumentationFailCount}/${instrumentationChecks.length} checks`
    : `${unsupportedIssueCount} issues · instrumentation missing`
  const dataQualityDetailSecondary = !instrumentationKnown
    ? 'instrumentation summary missing from payload'
    : dataQualitySeverity === 'good'
      ? 'all required quality gates are passing'
      : dataQualitySeverity === 'bad'
        ? 'blocking quality issues detected'
        : 'quality gaps may skew KPI interpretation'
  const showExtendedOverviewKpis = instrumentation?.compliant === true

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
    return episodes.filter((episode) => {
      if (statusFilter !== 'all' && episode.status !== statusFilter) return false
      if (replayOnly && !episode.replay_url) return false
      return matchesTagQuery(episode, tagQuery)
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

  const replayEpisodes = useMemo(() => {
    return completedEpisodes
      .filter((episode) => Boolean(episode.replay_url))
      .sort(
        (left, right) =>
          (toFiniteNumber(left.reward ?? left.avg_reward) ?? Number.NEGATIVE_INFINITY) -
          (toFiniteNumber(right.reward ?? right.avg_reward) ?? Number.NEGATIVE_INFINITY)
      )
  }, [completedEpisodes])

  const selectedReplayEpisodeFromTable = useMemo(() => {
    if (!selectedEpisodeId) return null
    const found = episodes.find((episode) => episodeIdentifier(episode) === selectedEpisodeId)
    if (!found?.replay_url) return null
    return found
  }, [episodes, selectedEpisodeId])

  const replaySpotlightEpisode = useMemo(() => {
    if (overviewReplayMode === 'selected' && selectedReplayEpisodeFromTable) return selectedReplayEpisodeFromTable
    if (replayEpisodes.length === 0) return null
    if (overviewReplayMode === 'worst') return replayEpisodes[0]
    if (overviewReplayMode === 'best') return replayEpisodes[replayEpisodes.length - 1]
    return replayEpisodes[Math.floor(replayEpisodes.length / 2)]
  }, [overviewReplayMode, replayEpisodes, selectedReplayEpisodeFromTable])

  const replaySpotlightUrls = useMemo(() => {
    const replayUrl = typeof replaySpotlightEpisode?.replay_url === 'string' ? replaySpotlightEpisode.replay_url : null
    const mettascopeUrl = normalizeReplayUrl(replayUrl)
    return {
      mettascopeUrl,
      selected: mettascopeUrl,
    }
  }, [replaySpotlightEpisode?.replay_url])
  const isReplaySpotlightLoaded = replaySpotlightUrls.selected
    ? loadedReplaySpotlightUrl === replaySpotlightUrls.selected
    : true
  const replayKeyboardShortcutsEnabled = activeTab === 'overview' && Boolean(replaySpotlightUrls.selected)

  const toggleReplayTheaterMode = useCallback(() => {
    setIsReplayTheaterMode((current) => !current)
  }, [])

  const toggleReplayFullscreen = useCallback(() => {
    if (typeof document === 'undefined') return
    if (document.fullscreenElement) {
      void document.exitFullscreen()
      return
    }
    const container = replaySpotlightContainerRef.current
    if (!container || typeof container.requestFullscreen !== 'function') return
    void container.requestFullscreen()
  }, [])

  const onReplaySpotlightLoaded = useCallback(() => {
    if (replaySpotlightUrls.selected) {
      setLoadedReplaySpotlightUrl(replaySpotlightUrls.selected)
    }
  }, [replaySpotlightUrls.selected])

  useEffect(() => {
    if (replayKeyboardShortcutsEnabled) return
    setIsReplayTheaterMode(false)
  }, [replayKeyboardShortcutsEnabled])

  useEffect(() => {
    if (!replayKeyboardShortcutsEnabled || typeof window === 'undefined') return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.repeat) return
      if (isTypingContextTarget(event.target)) return
      const key = event.key.toLowerCase()
      if (key === 't') {
        event.preventDefault()
        toggleReplayTheaterMode()
        return
      }
      if (key === 'f') {
        event.preventDefault()
        toggleReplayFullscreen()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [replayKeyboardShortcutsEnabled, toggleReplayFullscreen, toggleReplayTheaterMode])

  const replaySpotlightFocusStep = useMemo(
    () => estimateReplayFocusStep(replaySpotlightEpisode),
    [replaySpotlightEpisode]
  )

  const overviewTrendPoints = useMemo(
    () => buildOverviewTrendPoints(completedEpisodes, overviewTrendMetric),
    [completedEpisodes, overviewTrendMetric]
  )
  const overviewTrendPath = useMemo(
    () => buildSparklinePath(overviewTrendPoints, OVERVIEW_TREND_CHART_WIDTH, OVERVIEW_TREND_CHART_HEIGHT, 22),
    [overviewTrendPoints]
  )
  const overviewTrendStats = useMemo(() => {
    if (overviewTrendPoints.length === 0) return null
    const values = overviewTrendPoints.map((point) => point.value)
    return {
      min: Math.min(...values),
      max: Math.max(...values),
      latest: values[values.length - 1],
      oldest: values[0],
      start: overviewTrendPoints[0].createdAt,
      end: overviewTrendPoints[overviewTrendPoints.length - 1].createdAt,
    }
  }, [overviewTrendPoints])

  const trendPoints = useMemo(() => asTrendPoints(trend?.points), [trend])
  const trendCoveredVersionCount = useMemo(
    () =>
      trendPoints.filter(
        (point) =>
          toFiniteNumber(point.score) !== null ||
          toFiniteNumber(point.rank) !== null ||
          (toFiniteNumber(point.matches) ?? 0) > 0
      ).length,
    [trendPoints]
  )
  const trendTotalMatches = useMemo(
    () => trendPoints.reduce((sum, point) => sum + (toFiniteNumber(point.matches) ?? 0), 0),
    [trendPoints]
  )

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
    const selectedMetric = selectedTrendSeries?.key ?? selectedTrendMetric
    return buildDashboardFeedbackUrl({
      policyVersionId: String(data.policy?.id ?? ''),
      policyLabel: `${String(data.policy?.name ?? 'unknown')} v${String(data.policy?.version ?? '?')}`,
      activeTab,
      dashboardUrl,
      generatedAt: String(data.generated_at ?? '-'),
      activeMetric: selectedMetric,
      selectedEpisodeId,
      tagQuery,
    })
  }, [activeTab, data, selectedEpisodeId, selectedTrendMetric, selectedTrendSeries?.key, tagQuery])

  useEffect(() => {
    if (trendSeries.length === 0) return
    if (trendSeries.some((series) => series.key === selectedTrendMetric)) return
    const defaultMetric = trendExplorer?.selected_metric ?? trendSeries[0].key
    setSelectedTrendMetric(defaultMetric)
  }, [selectedTrendMetric, trendExplorer?.selected_metric, trendSeries])

  const loadDashboardData = useCallback(
    async (rawPolicyVersionId: string) => {
      const trimmedPolicyVersionId = rawPolicyVersionId.trim()
      if (!trimmedPolicyVersionId) return

      setError(null)
      setAnalysisError(null)
      setAnalysis(null)
      setRolePercentiles(null)
      setRoleError(null)
      setRoleLoading(false)

      const cachedResponse = getCachedDashboardResponse(trimmedPolicyVersionId)
      if (cachedResponse) {
        clearLoadProgressTimers()
        setLoading(false)
        setLoadProgress(0)
        void preloadRolePercentiles(
          trimmedPolicyVersionId,
          cachedResponse.generated_at,
          asEmbeddedRolePercentiles(cachedResponse.role_percentiles)
        )
        setData(cachedResponse)
        setSelectedEpisodeId(null)
        if (typeof window !== 'undefined') {
          const url = new URL(window.location.href)
          if (url.searchParams.get('policyVersionId') !== trimmedPolicyVersionId) {
            url.searchParams.set('policyVersionId', trimmedPolicyVersionId)
            window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
          }
        }
        return
      }

      beginDashboardLoadProgress('Generating dashboard summary.')
      try {
        const response = await fetchDashboardData(trimmedPolicyVersionId)
        cacheDashboardResponse(response)
        setData(response)
        setSelectedEpisodeId(null)
        void preloadRolePercentiles(
          String(response.policy?.id ?? trimmedPolicyVersionId),
          response.generated_at,
          asEmbeddedRolePercentiles(response.role_percentiles)
        )
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
        finishDashboardLoadProgress()
      }
    },
    [beginDashboardLoadProgress, clearLoadProgressTimers, finishDashboardLoadProgress, preloadRolePercentiles]
  )

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

  const onExportBundle = () => {
    if (!data || typeof window === 'undefined') return

    const payload = {
      exported_at: new Date().toISOString(),
      dashboard_data: data,
      ui_context: {
        active_tab: activeTab,
        selected_metric: selectedTrendSeries?.key ?? selectedTrendMetric,
        selected_episode_id: selectedEpisodeId,
        filters: {
          status: statusFilter,
          replay_only: replayOnly,
          tag_query: tagQuery,
        },
        sort: { key: episodeSort, direction: episodeSortDir },
      },
      filtered_episode_ids: sortedEpisodes.map((episode) => episodeIdentifier(episode)),
      filtered_episode_count: sortedEpisodes.length,
    }

    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `dashboard-${String(data.policy?.name ?? 'policy')}-v${String(data.policy?.version ?? 'x')}-bundle.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  useEffect(() => {
    if (!selectedEpisodeId) return
    if (filteredEpisodes.some((episode) => episodeIdentifier(episode) === selectedEpisodeId)) return
    setSelectedEpisodeId(null)
  }, [filteredEpisodes, selectedEpisodeId])

  useEffect(() => {
    const loadedPolicyVersionId = data?.policy?.id
    if (!loadedPolicyVersionId) return
    const shouldShowRoleLoadState = activeTab === 'overview'
    if (!shouldShowRoleLoadState) return
    const policyVersionKey = String(loadedPolicyVersionId)
    const cacheKey = rolePercentilesCacheKey(policyVersionKey, data?.generated_at) ?? policyVersionKey
    const embeddedRolePercentiles = asEmbeddedRolePercentiles(data?.role_percentiles)
    if (embeddedRolePercentiles) {
      cacheRolePercentiles(cacheKey, embeddedRolePercentiles)
      setRolePercentiles(embeddedRolePercentiles)
      setRoleLoading(false)
      setRoleError(null)
      return
    }

    const cachedPercentiles = getCachedRolePercentiles(cacheKey)
    if (cachedPercentiles) {
      setRolePercentiles(cachedPercentiles)
      setRoleLoading(false)
      setRoleError(null)
      return
    }

    let cancelled = false
    setRoleLoading(true)
    setRoleError(null)

    void getOrFetchRolePercentiles(cacheKey, policyVersionKey)
      .then((response) => {
        if (cancelled) return
        setRolePercentiles(response)
        setRoleError(null)
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
  }, [activeTab, data?.generated_at, data?.policy?.id, data?.role_percentiles])

  useEffect(() => {
    if (!data) {
      setDiagnoseRuns([])
      setSelectedDiagnoseRunId(null)
      setDiagnoseManifest(null)
      setDiagnoseNote(null)
      return
    }

    const embeddedDiagnoseRuns = asEmbeddedDiagnoseRuns(data.diagnose_runs)
    if (embeddedDiagnoseRuns) {
      const sortedRuns = sortDiagnoseRuns(embeddedDiagnoseRuns)
      diagnoseRunsCacheRef.current = sortedRuns
      setDiagnoseRuns(sortedRuns)
      setSelectedDiagnoseRunId((current) => {
        if (current && sortedRuns.some((run) => run.run_id === current)) return current
        const preferred =
          sortedRuns.find((run) => runLikelyMatchesPolicy(run, data.policy)) ??
          sortedRuns.find((run) => Boolean(run.manifest)) ??
          sortedRuns[0]
        return preferred?.run_id ?? null
      })
      return
    }

    let cancelled = false

    void prefetchDiagnoseRuns()
      .then((runs) => {
        if (cancelled) return
        const sortedRuns = sortDiagnoseRuns(runs)

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
      .catch(() => {
        if (cancelled) return
        setDiagnoseRuns([])
        setSelectedDiagnoseRunId(null)
        setDiagnoseManifest(null)
        setDiagnoseNote(null)
      })

    return () => {
      cancelled = true
    }
  }, [data, prefetchDiagnoseRuns])

  useEffect(() => {
    if (!selectedDiagnoseRunId) {
      setDiagnoseManifest(null)
      setDiagnoseNote(null)
      return
    }

    let cancelled = false
    setDiagnoseManifest(diagnoseRuns.find((run) => run.run_id === selectedDiagnoseRunId)?.manifest ?? null)

    void Promise.allSettled([
      fetchDiagnoseDoctorNote(selectedDiagnoseRunId),
      fetchDiagnoseManifest(selectedDiagnoseRunId),
    ]).then((results) => {
      if (cancelled) return
      const [noteResult, manifestResult] = results

      if (noteResult.status === 'fulfilled') {
        setDiagnoseNote(noteResult.value)
      } else {
        setDiagnoseNote(null)
      }

      if (manifestResult.status === 'fulfilled') {
        setDiagnoseManifest(manifestResult.value)
      }
    })

    return () => {
      cancelled = true
    }
  }, [diagnoseRuns, selectedDiagnoseRunId])

  useEffect(() => {
    if (activeTab !== 'pantheon') return

    let cancelled = false
    setPantheonLoading(true)
    setPantheonError(null)

    void prefetchPantheonStories()
      .then((stories) => {
        if (cancelled) return
        setPantheonStories(stories)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setPantheonStories([])
        setPantheonError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (cancelled) return
        setPantheonLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [activeTab, prefetchPantheonStories])

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
        const cachedResponse = getCachedDashboardResponse(initialPolicyVersionId)
        if (cachedResponse) {
          void preloadRolePercentiles(
            initialPolicyVersionId,
            cachedResponse.generated_at,
            asEmbeddedRolePercentiles(cachedResponse.role_percentiles)
          )
          setData(cachedResponse)
          setError(null)
          return
        }
        await loadDashboardData(initialPolicyVersionId)
        return
      }

      const cachedDefault = getCachedDefaultDashboardResponse()
      if (cachedDefault) {
        clearLoadProgressTimers()
        setLoading(false)
        setLoadProgress(0)
        const defaultPolicyVersionId = String(cachedDefault.policy?.id ?? '').trim()
        void preloadRolePercentiles(
          defaultPolicyVersionId,
          cachedDefault.generated_at,
          asEmbeddedRolePercentiles(cachedDefault.role_percentiles)
        )
        setData(cachedDefault)
        setError(null)
        if (!defaultPolicyVersionId) return
        setPolicyVersionId(defaultPolicyVersionId)
        const url = new URL(window.location.href)
        if (url.searchParams.get('policyVersionId') !== defaultPolicyVersionId) {
          url.searchParams.set('policyVersionId', defaultPolicyVersionId)
          window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
        }
        return
      }

      try {
        beginDashboardLoadProgress('Loading default policy dashboard.')
        const response = await fetchDashboardDefaultData()
        if (cancelled) return

        const defaultPolicyVersionId = String(response.policy?.id ?? '').trim()
        cacheDashboardResponse(response, true)
        setData(response)
        setError(null)
        void preloadRolePercentiles(
          defaultPolicyVersionId,
          response.generated_at,
          asEmbeddedRolePercentiles(response.role_percentiles)
        )
        if (!defaultPolicyVersionId) return

        setPolicyVersionId(defaultPolicyVersionId)
        const url = new URL(window.location.href)
        if (url.searchParams.get('policyVersionId') !== defaultPolicyVersionId) {
          url.searchParams.set('policyVersionId', defaultPolicyVersionId)
          window.history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`)
        }
      } catch (err) {
        if (cancelled) return
        const message = err instanceof Error ? err.message : String(err)
        setError(message)
      } finally {
        if (!cancelled) {
          finishDashboardLoadProgress()
        }
      }
    }

    void initialize()
    return () => {
      cancelled = true
    }
  }, [
    beginDashboardLoadProgress,
    clearLoadProgressTimers,
    finishDashboardLoadProgress,
    loadDashboardData,
    preloadRolePercentiles,
  ])

  const kpis = data?.derived?.kpis
  const avgReward = toFiniteNumber(kpis?.avg_reward ?? kpis?.mean_reward)
  const actionSuccess = toFiniteNumber(kpis?.action_success_rate)
  const resourceRetention = toFiniteNumber(kpis?.resource_retention)
  const freezeVulnerability = toFiniteNumber(kpis?.freeze_vulnerability)
  const junctionControl = toFiniteNumber(kpis?.junction_control_rate)
  const noopRate = toFiniteNumber(kpis?.noop_rate)
  const rewardConsistency = toFiniteNumber(kpis?.reward_consistency)
  const avgRewardSeverity = kpiSeverity(avgReward, 2.0, 0.5)
  const avgRewardBandDetail = kpiSeverityBandDetail(avgReward, 2.0, 0.5, true, (threshold) =>
    formatNumber(threshold, 2)
  )
  const completedRewardSample = useMemo(
    () =>
      completedEpisodes
        .map((episode) => toFiniteNumber(episode.reward ?? episode.avg_reward))
        .filter((reward): reward is number => reward !== null),
    [completedEpisodes]
  )
  const parseRewardPercentile = useMemo(() => {
    const rows = rolePercentiles?.rows
    if (!rows || rows.length === 0) return null
    const percentiles: number[] = []
    for (const row of rows) {
      if (!row || typeof row !== 'object') continue
      const details = (row as Record<string, unknown>).details
      if (!details || typeof details !== 'object' || Array.isArray(details)) continue
      const metrics = (details as Record<string, unknown>).metrics
      if (!metrics || typeof metrics !== 'object' || Array.isArray(metrics)) continue
      const rewardMetric = (metrics as Record<string, unknown>).reward
      if (!rewardMetric || typeof rewardMetric !== 'object' || Array.isArray(rewardMetric)) continue
      const percentile = toFiniteNumber((rewardMetric as Record<string, unknown>).percentile)
      if (percentile !== null) percentiles.push(percentile)
    }
    if (percentiles.length === 0) return null
    return percentiles.reduce((sum, value) => sum + value, 0) / percentiles.length
  }, [rolePercentiles])
  const avgRewardPercentile = useMemo(
    () => percentileRank(avgReward, completedRewardSample),
    [avgReward, completedRewardSample]
  )
  const avgRewardPercentileDetail =
    parseRewardPercentile !== null && avgRewardPercentile !== null
      ? `pool reward percentile: P${formatNumber(parseRewardPercentile, 0)} (sample P${formatNumber(avgRewardPercentile, 0)})`
      : parseRewardPercentile !== null
        ? `pool reward percentile: P${formatNumber(parseRewardPercentile, 0)}`
        : avgRewardPercentile !== null
          ? `sample reward percentile: P${formatNumber(avgRewardPercentile, 0)}`
          : 'reward percentile unavailable'
  const actionSuccessSeverity = kpiSeverity(actionSuccess, 0.9, 0.7)
  const actionSuccessBandDetail = kpiSeverityBandDetail(actionSuccess, 0.9, 0.7, true, (threshold) =>
    formatPercent(threshold, 0)
  )
  const junctionControlSeverity = kpiSeverity(junctionControl, 0.6, 0.2)
  const junctionControlBandDetail = kpiSeverityBandDetail(junctionControl, 0.6, 0.2, true, (threshold) =>
    formatPercent(threshold, 0)
  )
  const noopRateSeverity = kpiSeverity(noopRate, 0.1, 0.25, false)
  const noopRateBandDetail = kpiSeverityBandDetail(noopRate, 0.1, 0.25, false, (threshold) =>
    formatPercent(threshold, 0)
  )
  const resourceRetentionSeverity = kpiSeverity(resourceRetention, 0.5, 0.2)
  const resourceRetentionBandDetail = kpiSeverityBandDetail(resourceRetention, 0.5, 0.2, true, (threshold) =>
    formatPercent(threshold, 0)
  )
  const freezeVulnerabilitySeverity = kpiSeverity(freezeVulnerability, 0.05, 0.15, false)
  const freezeVulnerabilityBandDetail = kpiSeverityBandDetail(freezeVulnerability, 0.05, 0.15, false, (threshold) =>
    formatPercent(threshold, 1)
  )
  const rewardConsistencySeverity = kpiSeverity(rewardConsistency, 0.6, 0.2)
  const rewardConsistencyBandDetail = kpiSeverityBandDetail(rewardConsistency, 0.6, 0.2, true, (threshold) =>
    formatPercent(threshold, 0)
  )
  const trainingFocus = deriveTrainingFocus(kpis)
  const completedWithReplayCount = completedEpisodes.filter((episode) => Boolean(episode.replay_url)).length
  const replayCoverage = completedEpisodes.length > 0 ? completedWithReplayCount / completedEpisodes.length : null
  const overviewRoleParsePills = useMemo(() => {
    const rows = rolePercentiles?.rows ?? []
    const rolePercentilesByRole = new Map<string, number>()
    const roleRowsByRole = new Map<string, (typeof rows)[number]>()
    for (const row of rows) {
      const role = String(row.role ?? '')
        .trim()
        .toLowerCase()
      const percentile = toFiniteNumber(row.percentile)
      if (!OVERVIEW_PARSE_ROLES.includes(role as (typeof OVERVIEW_PARSE_ROLES)[number])) continue
      if (percentile !== null) rolePercentilesByRole.set(role, percentile)
      roleRowsByRole.set(role, row)
    }

    return OVERVIEW_PARSE_ROLES.map((role) => ({
      role,
      label: OVERVIEW_PARSE_ROLE_LABELS[role],
      percentile: rolePercentilesByRole.get(role) ?? null,
      metricKeys: ((rolePercentiles?.roles?.[role] ?? []) as DashboardRoleMetricDef[])
        .map((definition, index) => ({
          definition,
          index,
          priority: OVERVIEW_PARSE_PRIORITY_METRICS[role].indexOf(definition.key),
        }))
        .sort((left, right) => {
          const leftPriority = left.priority >= 0 ? left.priority : Number.POSITIVE_INFINITY
          const rightPriority = right.priority >= 0 ? right.priority : Number.POSITIVE_INFINITY
          if (leftPriority !== rightPriority) return leftPriority - rightPriority
          return left.index - right.index
        })
        .map(({ definition }) => definition.key)
        .filter((key) => key.length > 0),
      sampleCount:
        Object.values(roleRowsByRole.get(role)?.details?.metrics ?? {})
          .map((metric) => toFiniteNumber(metric?.samples))
          .find((count) => count !== null) ?? null,
    }))
  }, [rolePercentiles])
  const capabilityAuditSummary = useMemo(() => {
    const statuses = Object.values(data?.derived?.capability_code_audit?.capabilities ?? {})
    let yes = 0
    let partial = 0
    let no = 0
    let planned = 0
    let unknown = 0
    let supportTrained = 0
    let supportBacked = 0
    let withEvidence = 0

    for (const statusEntry of statuses) {
      const status = String(statusEntry.status ?? '')
        .trim()
        .toLowerCase()
      if (status === 'yes') yes += 1
      else if (status === 'partial') partial += 1
      else if (status === 'no') no += 1
      else if (status === 'planned') planned += 1
      else unknown += 1

      const supportType = String(statusEntry.support_type ?? '')
        .trim()
        .toLowerCase()
      if (supportType === 'trained') supportTrained += 1
      else if (supportType === 'backed') supportBacked += 1

      if (Array.isArray(statusEntry.evidence) && statusEntry.evidence.length > 0) withEvidence += 1
    }

    const total = statuses.length
    return {
      total,
      yes,
      partial,
      no,
      planned,
      unknown,
      supportTrained,
      supportBacked,
      withEvidence,
      coverage: total > 0 ? yes / total : null,
      partialRate: total > 0 ? partial / total : null,
      missingRate: total > 0 ? no / total : null,
    }
  }, [data?.derived?.capability_code_audit?.capabilities])
  const capabilityStatusTotal = capabilityAuditSummary.total
  const capabilityStatusYes = capabilityAuditSummary.yes
  const capabilityStatusPartial = capabilityAuditSummary.partial
  const capabilityStatusNo = capabilityAuditSummary.no
  const capabilityStatusPlanned = capabilityAuditSummary.planned
  const capabilityStatusUnknown = capabilityAuditSummary.unknown
  const capabilityCoverage = capabilityAuditSummary.coverage
  const capabilityPartialRate = capabilityAuditSummary.partialRate
  const capabilityMissingRate = capabilityAuditSummary.missingRate
  const capabilitySupportTrained = capabilityAuditSummary.supportTrained
  const capabilitySupportBacked = capabilityAuditSummary.supportBacked
  const capabilityWithEvidenceCount = capabilityAuditSummary.withEvidence
  const pantheonStoriesByHall = useMemo(
    () =>
      PANTHEON_HALLS.reduce(
        (groups, hall) => {
          groups[hall] = pantheonStories.filter((story) => story.hall === hall)
          return groups
        },
        {
          fame: [] as PantheonStory[],
          same: [] as PantheonStory[],
          lame: [] as PantheonStory[],
        }
      ),
    [pantheonStories]
  )
  const pantheonPolicyCount = useMemo(() => {
    const policies = new Set(pantheonStories.map((story) => story.policy).filter((value) => value.trim().length > 0))
    return policies.size
  }, [pantheonStories])
  const pantheonReplayLinkedCount = useMemo(
    () => pantheonStories.filter((story) => Boolean(story.replay_url)).length,
    [pantheonStories]
  )
  const autoTrainingCommand = useMemo(() => {
    const policyName = String(data?.policy?.name ?? 'policy')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
    const policyVersion = String(data?.policy?.version ?? 'x')
    const runName = `auto-${policyName}-v${policyVersion}-${trainingFocus}`
    return `uv run ./tools/run.py train arena run=${runName} trainer.total_timesteps=20000000`
  }, [data?.policy?.name, data?.policy?.version, trainingFocus])
  const autoTrainingHint = autoTrainingRecipeHint(trainingFocus, data?.derived?.capability_code_audit)
  const copyAutoTrainingCommand = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return
    await navigator.clipboard.writeText(autoTrainingCommand)
    setAutoCommandCopied(true)
    setTimeout(() => setAutoCommandCopied(false), 1800)
  }, [autoTrainingCommand])

  return (
    <main className="grid dashboard-shell" style={{ gap: 16 }}>
      <section className="card dashboard-control-card grid" style={{ gap: 12 }}>
        <div className="dashboard-control-head">
          <div>
            <h1 className="dashboard-title-line">
              <span>Policy Dashboard</span>
              <span className="dashboard-title-subline">
                Episodes, diagnostics, and skill-tree evaluation in one view.
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
        {loading && (
          <div style={{ display: 'grid', gap: 6 }}>
            <div
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(loadProgress)}
              style={{
                width: '100%',
                height: 8,
                borderRadius: 999,
                background: 'rgba(15, 23, 42, 0.12)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${Math.max(4, Math.min(100, loadProgress))}%`,
                  height: '100%',
                  background: 'linear-gradient(90deg, #2563eb, #0ea5e9)',
                  transition: 'width 220ms ease',
                }}
              />
            </div>
            <p style={{ margin: 0, color: '#6f86a6', fontSize: 12 }}>{loadProgressMessage}</p>
          </div>
        )}
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
              onClick={() => activateTab('coordination')}
              className={activeTab === 'coordination' ? 'active-tab' : ''}
            >
              Coordination
            </button>
            <button
              type="button"
              onClick={() => activateTab('performance')}
              className={activeTab === 'performance' ? 'active-tab' : ''}
            >
              Episodes
            </button>
          </section>

          {(activeTab === 'overview' || activeTab === 'performance') && (
            <>
              {activeTab === 'overview' && (
                <section className="grid kpi-grid" style={{ gap: 10 }}>
                  <KPIStatCard
                    label="Avg Reward"
                    value={formatNumber(avgReward, 2)}
                    detail={avgRewardBandDetail}
                    detailSecondary={avgRewardPercentileDetail}
                    severity={avgRewardSeverity}
                  />
                  <KPIStatCard
                    label="Action Success"
                    value={formatPercent(actionSuccess, 0)}
                    detail={actionSuccessBandDetail}
                    severity={actionSuccessSeverity}
                  />
                  <KPIStatCard
                    label="Junction Control"
                    value={formatPercent(junctionControl, 0)}
                    detail={junctionControlBandDetail}
                    severity={junctionControlSeverity}
                  />
                  <KPIStatCard
                    label="Noop Rate"
                    value={formatPercent(noopRate, 1)}
                    detail={noopRateBandDetail}
                    severity={noopRateSeverity}
                  />
                  <KPIStatCard
                    label="Data Quality"
                    value={dataQualityLabel}
                    detail={dataQualityDetail}
                    detailSecondary={dataQualityDetailSecondary}
                    severity={dataQualitySeverity}
                  />
                  {showExtendedOverviewKpis && (
                    <KPIStatCard
                      label="Resource Retention"
                      value={formatPercent(resourceRetention, 0)}
                      detail={resourceRetentionBandDetail}
                      severity={resourceRetentionSeverity}
                    />
                  )}
                  {showExtendedOverviewKpis && (
                    <KPIStatCard
                      label="Freeze Vulnerability"
                      value={formatPercent(freezeVulnerability, 1)}
                      detail={freezeVulnerabilityBandDetail}
                      severity={freezeVulnerabilitySeverity}
                    />
                  )}
                  {showExtendedOverviewKpis && (
                    <KPIStatCard
                      label="Reward Consistency"
                      value={formatPercent(rewardConsistency, 0)}
                      detail={rewardConsistencyBandDetail}
                      severity={rewardConsistencySeverity}
                    />
                  )}
                </section>
              )}

              {activeTab === 'overview' &&
                (unsupported ||
                  instrumentation ||
                  actionSummary ||
                  orchestration ||
                  trend ||
                  confidence ||
                  patterns) && (
                  <section className="grid kpi-grid" style={{ gap: 10 }}>
                    {unsupported && (
                      <article
                        className="card"
                        style={{
                          padding: 10,
                          borderWidth: 2,
                          minWidth: 0,
                          ...severityStyle(unsupportedIssueCount > 0 ? 'warn' : 'good'),
                        }}
                      >
                        Unsupported-state warnings: <code>{unsupportedIssueCount}</code>
                      </article>
                    )}
                    {instrumentation && (
                      <article
                        className="card"
                        style={{
                          padding: 10,
                          borderWidth: 2,
                          minWidth: 0,
                          ...severityStyle(instrumentation.compliant ? 'good' : 'warn'),
                        }}
                      >
                        Instrumentation: <strong>{instrumentation.compliant ? 'compliant' : 'incomplete'}</strong> ·
                        score <code>{formatPercent(toFiniteNumber(instrumentation.score), 0)}</code>
                      </article>
                    )}
                    {actionSummary && (
                      <article
                        className="card"
                        style={{
                          padding: 10,
                          borderWidth: 2,
                          minWidth: 0,
                          ...severityStyle(
                            String(actionSummary.rollout_recommendation ?? '').toLowerCase() === 'hold'
                              ? 'warn'
                              : 'good'
                          ),
                        }}
                      >
                        Rollout gate: <code>{String(actionSummary.rollout_recommendation ?? '-')}</code> ·{' '}
                        <span style={{ overflowWrap: 'anywhere' }}>{String(actionSummary.headline ?? '-')}</span>
                      </article>
                    )}
                    {orchestration && (
                      <article
                        className="card"
                        style={{ padding: 10, borderWidth: 2, minWidth: 0, ...severityStyle('warn') }}
                      >
                        Experiment mode: <code>{String(orchestration.mode ?? '-')}</code> ·{' '}
                        <span style={{ overflowWrap: 'anywhere' }}>{String(orchestration.headline ?? '-')}</span>
                      </article>
                    )}
                    {trend && (
                      <article
                        className="card"
                        style={{
                          padding: 10,
                          borderWidth: 2,
                          minWidth: 0,
                          ...severityStyle(
                            String(trend.direction ?? '')
                              .toLowerCase()
                              .includes('improv') || String(trend.direction ?? '').toLowerCase() === 'up'
                              ? 'good'
                              : String(trend.direction ?? '')
                                    .toLowerCase()
                                    .includes('regress') || String(trend.direction ?? '').toLowerCase() === 'down'
                                ? 'bad'
                                : 'warn'
                          ),
                        }}
                      >
                        Trend: <code>{String(trend.direction ?? 'insufficient')}</code> · evidence{' '}
                        <strong>{trend.evidence_sufficient ? 'sufficient' : 'limited'}</strong> · covered{' '}
                        <code>
                          {trendCoveredVersionCount}/{trendPoints.length}
                        </code>
                      </article>
                    )}
                    {confidence && (
                      <article
                        className="card"
                        style={{
                          padding: 10,
                          borderWidth: 2,
                          minWidth: 0,
                          ...severityStyle(confidence.evidence_sufficient ? 'good' : 'warn'),
                        }}
                      >
                        Confidence: <strong>{confidence.evidence_sufficient ? 'sufficient' : 'limited'}</strong> ·
                        intervals <code>{(confidence.intervals ?? []).length}</code>
                      </article>
                    )}
                    {patterns && (
                      <article
                        className="card"
                        style={{
                          padding: 10,
                          borderWidth: 2,
                          minWidth: 0,
                          ...severityStyle(patterns.evidence_sufficient ? 'good' : 'warn'),
                        }}
                      >
                        Pattern extraction:{' '}
                        <span style={{ overflowWrap: 'anywhere' }}>{String(patterns.headline ?? '-')}</span> · signals{' '}
                        <code>{(patterns.signals ?? []).length}</code>
                      </article>
                    )}
                  </section>
                )}

              {activeTab === 'overview' && (
                <section className="grid parse-pill-grid" style={{ gap: 10 }}>
                  {overviewRoleParsePills.map((pill) => (
                    <article
                      key={pill.role}
                      className="card"
                      style={{ padding: 12, borderWidth: 2, minWidth: 0, ...parsePercentilePillStyle(pill.percentile) }}
                    >
                      <p
                        style={{
                          margin: 0,
                          fontSize: 12,
                          letterSpacing: 0.3,
                          textTransform: 'uppercase',
                          color: 'var(--kpi-label-ink)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                        title={pill.label}
                      >
                        {pill.label}
                      </p>
                      <p
                        style={{
                          margin: '6px 0 0',
                          fontSize: 24,
                          fontWeight: 700,
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                        }}
                        title={pill.percentile === null ? '-' : `P${pill.percentile.toFixed(1)}`}
                      >
                        {pill.percentile === null ? '-' : `P${pill.percentile.toFixed(1)}`}
                      </p>
                      <div className="role-progress" style={{ marginTop: 6 }}>
                        <div
                          className="role-progress-bar"
                          style={{ width: `${Math.max(0, Math.min(pill.percentile ?? 0, 100))}%` }}
                        />
                      </div>
                      <p
                        style={{
                          margin: '4px 0 0',
                          fontSize: 12,
                          color: 'var(--kpi-detail-ink)',
                          whiteSpace: 'normal',
                          overflowWrap: 'anywhere',
                          lineHeight: 1.3,
                        }}
                        title={
                          pill.metricKeys.length > 0
                            ? `mix metrics: ${pill.metricKeys.join(', ')}`
                            : 'mix metrics unavailable'
                        }
                      >
                        {pill.metricKeys.length > 0
                          ? `mix: ${pill.metricKeys.slice(0, 3).join(', ')}${pill.metricKeys.length > 3 ? ` +${pill.metricKeys.length - 3}` : ''}`
                          : 'mix unavailable'}
                        {pill.sampleCount !== null ? ` · n≈${pill.sampleCount.toFixed(0)}` : ''}
                      </p>
                      {pill.percentile === null && (
                        <p
                          style={{
                            margin: '2px 0 0',
                            fontSize: 12,
                            color: 'var(--kpi-detail-ink)',
                            whiteSpace: 'normal',
                            overflowWrap: 'anywhere',
                            lineHeight: 1.3,
                          }}
                        >
                          {roleLoading ? 'loading' : roleError ? 'unavailable' : 'no data'}
                        </p>
                      )}
                    </article>
                  ))}
                </section>
              )}

              {activeTab === 'performance' && (
                <section className="grid kpi-grid" style={{ gap: 10 }}>
                  <KPIStatCard
                    label="Failed Episodes"
                    value={String(toFiniteNumber(failures.failed_episodes) ?? 0)}
                    detail={formatPercent(toFiniteNumber(failures.failed_rate), 1)}
                    severity={kpiSeverity(toFiniteNumber(failures.failed_rate), 0.03, 0.1, false)}
                  />
                  <KPIStatCard
                    label="Replay Coverage"
                    value={formatPercent(replayCoverage, 0)}
                    detail={`${completedWithReplayCount}/${completedEpisodes.length} completed`}
                    severity={kpiSeverity(replayCoverage, 0.7, 0.4)}
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
                      (toFiniteNumber(failures.crash_failures) ?? 0) + (toFiniteNumber(failures.other_failures) ?? 0) >
                      0
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
              )}

              {activeTab === 'performance' && (
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
              )}

              <section className="grid" style={{ gap: 10 }}>
                {activeTab === 'overview' && (
                  <>
                    <article className="card grid" style={{ gap: 10, minWidth: 0 }}>
                      <div className="dashboard-title-line" style={{ marginBottom: 2 }}>
                        <h2 style={{ margin: 0 }}>Replay Spotlight</h2>
                        <span className="dashboard-title-subline">Embedded replay view for fastest debugging.</span>
                      </div>
                      {replayEpisodes.length === 0 ? (
                        <p style={{ margin: 0 }}>
                          No replay URLs found in sampled completed episodes. We can wire richer in-view controls once
                          replay capture coverage is complete.
                        </p>
                      ) : (
                        <>
                          <div
                            ref={replaySpotlightContainerRef}
                            data-testid="replay-spotlight-shell"
                            data-theater-mode={isReplayTheaterMode ? 'on' : 'off'}
                            style={{
                              position: 'relative',
                              width: isReplayTheaterMode ? 'calc(100vw - 24px)' : '100%',
                              maxWidth: isReplayTheaterMode ? 'calc(100vw - 24px)' : '100%',
                              marginLeft: isReplayTheaterMode ? '50%' : undefined,
                              transform: isReplayTheaterMode ? 'translateX(-50%)' : undefined,
                              border: '1px solid var(--line)',
                              borderRadius: 10,
                              overflow: 'hidden',
                              background: '#000',
                              minHeight: isReplayTheaterMode ? 0 : 360,
                              aspectRatio: isReplayTheaterMode ? '16 / 9' : undefined,
                            }}
                          >
                            {replaySpotlightUrls.selected ? (
                              <>
                                {!isReplaySpotlightLoaded && (
                                  <div
                                    data-testid="replay-spotlight-loading"
                                    style={{
                                      position: 'absolute',
                                      inset: 0,
                                      display: 'flex',
                                      alignItems: 'center',
                                      justifyContent: 'center',
                                      background: 'rgba(2, 6, 23, 0.88)',
                                      color: '#dbeafe',
                                      fontSize: 12,
                                      letterSpacing: 0.2,
                                      zIndex: 1,
                                    }}
                                  >
                                    Loading replay spotlight...
                                  </div>
                                )}
                                <iframe
                                  key={
                                    replaySpotlightEpisode
                                      ? episodeIdentifier(replaySpotlightEpisode)
                                      : 'replay-spotlight'
                                  }
                                  src={replaySpotlightUrls.selected}
                                  title="Replay spotlight"
                                  onLoad={onReplaySpotlightLoaded}
                                  style={{
                                    width: '100%',
                                    height: isReplayTheaterMode ? '100%' : 420,
                                    border: 0,
                                    opacity: isReplaySpotlightLoaded ? 1 : 0,
                                    transition: 'opacity 180ms ease',
                                  }}
                                  loading="lazy"
                                  allowFullScreen
                                />
                              </>
                            ) : (
                              <div style={{ padding: 12, color: '#fff' }}>
                                Replay viewer unavailable for this episode.
                              </div>
                            )}
                          </div>
                          <div className="grid" style={{ gap: 8 }}>
                            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ whiteSpace: 'nowrap' }}>Episode focus</span>
                              <select
                                value={overviewReplayMode}
                                onChange={(event) => setOverviewReplayMode(event.target.value as ReplaySpotlightMode)}
                                style={{ margin: 0, width: 'auto', minWidth: 0, flex: 1 }}
                              >
                                <option value="selected" disabled={!selectedReplayEpisodeFromTable}>
                                  selected from Episodes tab
                                </option>
                                <option value="worst">worst reward with replay</option>
                                <option value="median">median reward with replay</option>
                                <option value="best">best reward with replay</option>
                              </select>
                            </label>
                            <p style={{ margin: 0, fontSize: 12, color: '#4b617f' }}>
                              Shortcuts: <code>t</code> theater ({isReplayTheaterMode ? 'on' : 'off'}) · <code>f</code>{' '}
                              fullscreen
                            </p>
                          </div>
                          <p style={{ margin: 0, fontSize: 12, color: '#4b617f' }}>
                            Episode:{' '}
                            <code>{replaySpotlightEpisode ? episodeIdentifier(replaySpotlightEpisode) : '-'}</code> ·
                            reward{' '}
                            <code>
                              {formatNumber(
                                toFiniteNumber(replaySpotlightEpisode?.reward ?? replaySpotlightEpisode?.avg_reward),
                                3
                              )}
                            </code>{' '}
                            · steps <code>{String(toFiniteNumber(replaySpotlightEpisode?.steps) ?? '-')}</code>
                            {replaySpotlightFocusStep !== null && (
                              <>
                                {' '}
                                · seek hint <code>~step {replaySpotlightFocusStep}</code>
                              </>
                            )}
                          </p>
                        </>
                      )}
                    </article>

                    <section className="grid two coordination-pairing-layout" style={{ alignItems: 'start' }}>
                      <div className="grid" style={{ gap: 10, minWidth: 0 }}>
                        <section className="grid compact-grid" style={{ gap: 10 }}>
                          <article className="card">
                            <h2 style={{ marginTop: 0 }}>Best Teammate Pairing</h2>
                            {bestWorstOpponents?.best ? (
                              <p style={{ marginBottom: 0 }}>
                                <strong>{bestWorstOpponents.best.opponent}</strong> (avg reward{' '}
                                {formatNumber(bestWorstOpponents.best.avgReward, 3)})
                              </p>
                            ) : (
                              <p style={{ marginBottom: 0 }}>No teammate pairing reward data yet.</p>
                            )}
                          </article>
                          <article className="card">
                            <h2 style={{ marginTop: 0 }}>Lowest-Reward Teammate Pairing</h2>
                            {bestWorstOpponents?.worst ? (
                              <p style={{ marginBottom: 0 }}>
                                <strong>{bestWorstOpponents.worst.opponent}</strong> (avg reward{' '}
                                {formatNumber(bestWorstOpponents.worst.avgReward, 3)})
                              </p>
                            ) : (
                              <p style={{ marginBottom: 0 }}>No teammate pairing reward data yet.</p>
                            )}
                          </article>
                        </section>

                        {matchup && (
                          <section className="card" style={{ display: 'grid', gap: 10 }}>
                            <h2 style={{ margin: 0 }}>Teammate Pairing Diagnosis</h2>
                            <p style={{ margin: 0 }}>{String(matchup.reason ?? '-')}</p>
                            <div className="coordination-diagnosis-pills" style={{ display: 'grid', gap: 8 }}>
                              <div
                                className="card"
                                style={{
                                  padding: 10,
                                  borderWidth: 2,
                                  ...severityStyle(matchupCurrentAvgRewardSeverity),
                                }}
                              >
                                Current avg reward: <code>{formatNumber(matchupCurrentAvgReward, 3)}</code>
                              </div>
                              <div
                                className="card"
                                style={{
                                  padding: 10,
                                  borderWidth: 2,
                                  ...severityStyle(matchupBaselineAvgRewardSeverity),
                                }}
                              >
                                Baseline avg reward: <code>{formatNumber(matchupBaselineAvgReward, 3)}</code>
                              </div>
                              <div
                                className="card"
                                style={{ padding: 10, borderWidth: 2, ...severityStyle(matchupGlobalDeltaSeverity) }}
                              >
                                Global delta: <code>{formatSigned(matchupGlobalDelta, 3)}</code>
                              </div>
                              <div
                                className="card"
                                style={{ padding: 10, borderWidth: 2, ...severityStyle(matchupEvidenceSeverity) }}
                              >
                                Evidence: <strong>{matchup.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                              </div>
                              <div
                                className="card"
                                style={{ padding: 10, borderWidth: 2, ...severityStyle(matchupOpponentSpreadSeverity) }}
                              >
                                Teammate spread: <code>{formatNumber(matchupOpponentSpread, 3)}</code>
                              </div>
                              <div
                                className="card"
                                style={{ padding: 10, borderWidth: 2, ...severityStyle(matchupOpponentSpreadSeverity) }}
                              >
                                Best/Worst teammate:{' '}
                                <code>
                                  {String(matchup.best_opponent ?? '-')} / {String(matchup.worst_opponent ?? '-')}
                                </code>
                              </div>
                              <div
                                className="card"
                                style={{
                                  padding: 10,
                                  borderWidth: 2,
                                  ...severityStyle(matchupCompositionSpreadSeverity),
                                }}
                              >
                                Composition spread: <code>{formatNumber(matchupCompositionSpread, 3)}</code>
                              </div>
                              <div
                                className="card"
                                style={{
                                  padding: 10,
                                  borderWidth: 2,
                                  ...severityStyle(matchupCompositionSpreadSeverity),
                                }}
                              >
                                Best/Worst composition:{' '}
                                <code>
                                  {String(matchup.best_composition ?? '-')} / {String(matchup.worst_composition ?? '-')}
                                </code>
                              </div>
                            </div>
                          </section>
                        )}

                        <RolePercentilesPanel
                          roleData={rolePercentiles}
                          loading={roleLoading}
                          error={roleError}
                          mode="summary"
                        />

                        {data.derived?.outcome && (
                          <article className="card" style={{ minWidth: 0 }}>
                            <h2 style={{ marginTop: 0 }}>Outcome Summary</h2>
                            <p style={{ marginTop: 0 }}>
                              {String(data.derived.outcome.reason ?? 'No outcome summary provided.')}
                            </p>
                            <div className="grid outcome-meta-grid" style={{ gap: 8, fontSize: 13 }}>
                              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                Evidence:{' '}
                                <strong>{data.derived.outcome.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                              </span>
                              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                Score delta:{' '}
                                <code>{formatSigned(toFiniteNumber(data.derived.outcome.delta?.score_delta), 3)}</code>
                              </span>
                              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                Rank delta:{' '}
                                <code>{formatSigned(toFiniteNumber(data.derived.outcome.delta?.rank_delta), 0)}</code>
                              </span>
                              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                Baseline: v
                                {data.derived.outcome.baseline?.version === null ||
                                data.derived.outcome.baseline?.version === undefined
                                  ? '-'
                                  : data.derived.outcome.baseline.version}
                              </span>
                            </div>
                          </article>
                        )}

                        <article className="card grid" style={{ gap: 10, minWidth: 0 }}>
                          <div className="dashboard-title-line" style={{ marginBottom: 2 }}>
                            <h2 style={{ margin: 0 }}>Episode Metrics Over Time</h2>
                            <span className="dashboard-title-subline">X: episode time, Y: selected metric.</span>
                          </div>
                          <label style={{ display: 'flex', alignItems: 'center', gap: 8, maxWidth: 320 }}>
                            <span style={{ whiteSpace: 'nowrap' }}>Metric</span>
                            <select
                              value={overviewTrendMetric}
                              onChange={(event) => setOverviewTrendMetric(event.target.value as OverviewTrendMetric)}
                              style={{ margin: 0, width: 'auto', minWidth: 0, flex: 1 }}
                            >
                              <option value="reward">Reward</option>
                              <option value="noop_rate">Noop rate</option>
                              <option value="steps">Steps</option>
                              <option value="resource_gained">Resource gained</option>
                            </select>
                          </label>
                          {overviewTrendPoints.length < 2 || !overviewTrendStats ? (
                            <p style={{ margin: 0 }}>
                              Not enough per-episode signal for this metric yet. Per-step curves (resource/gear over
                              time) require richer episode telemetry; we can add those when backend collection lands.
                            </p>
                          ) : (
                            <>
                              <div style={{ overflowX: 'hidden' }}>
                                <svg
                                  width="100%"
                                  height={OVERVIEW_TREND_CHART_HEIGHT}
                                  viewBox={`0 0 ${OVERVIEW_TREND_CHART_WIDTH} ${OVERVIEW_TREND_CHART_HEIGHT}`}
                                  role="img"
                                  aria-label="Metric over time"
                                  style={{
                                    display: 'block',
                                    width: '94%',
                                    maxWidth: OVERVIEW_TREND_CHART_WIDTH,
                                    margin: '0 auto',
                                  }}
                                >
                                  <rect
                                    x="0"
                                    y="0"
                                    width={OVERVIEW_TREND_CHART_WIDTH}
                                    height={OVERVIEW_TREND_CHART_HEIGHT}
                                    fill="var(--panel-soft-bg-1)"
                                  />
                                  <path d={overviewTrendPath} fill="none" stroke="#2563eb" strokeWidth="2.3" />
                                </svg>
                              </div>
                              <div style={{ display: 'grid', gap: 8, fontSize: 13 }}>
                                <div className="grid metric-pairs" style={{ gap: 8 }}>
                                  <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                    Start:{' '}
                                    <code style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                                      {formatDateTime(overviewTrendStats.start)}
                                    </code>
                                  </span>
                                  <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                    End:{' '}
                                    <code style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                                      {formatDateTime(overviewTrendStats.end)}
                                    </code>
                                  </span>
                                </div>
                                <div className="grid metric-pairs" style={{ gap: 8 }}>
                                  <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                    Min/Max:{' '}
                                    <code style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                                      {formatNumber(overviewTrendStats.min, 3)}
                                    </code>{' '}
                                    /{' '}
                                    <code style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                                      {formatNumber(overviewTrendStats.max, 3)}
                                    </code>
                                  </span>
                                  <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                                    Delta:{' '}
                                    <code style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
                                      {formatSigned(overviewTrendStats.latest - overviewTrendStats.oldest, 3)}
                                    </code>
                                  </span>
                                </div>
                              </div>
                            </>
                          )}
                        </article>
                      </div>

                      <div className="grid" style={{ gap: 10, minWidth: 0 }}>
                        <section className="card">
                          <h2 style={{ marginTop: 0 }}>Teammate Breakdown</h2>
                          {opponentRows.length === 0 ? (
                            <p style={{ marginBottom: 0 }}>No teammate metrics available.</p>
                          ) : (
                            <div style={{ overflowX: 'auto' }}>
                              <table>
                                <thead>
                                  <tr>
                                    <th>Teammate</th>
                                    <th>Games</th>
                                    <th>Avg Reward</th>
                                    <th>Win Rate</th>
                                    <th>Agg</th>
                                    <th>Def</th>
                                    <th>Res</th>
                                    <th>Jnc</th>
                                    <th>Mob</th>
                                    <th>Top Profile</th>
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
                                      <td>{formatNumber(row.avgReward, 2)}</td>
                                      <td>{formatPercent(row.winRate, 0)}</td>
                                      <td>{formatNumber(toFiniteNumber(row.strategyProfile?.aggressive), 0)}</td>
                                      <td>{formatNumber(toFiniteNumber(row.strategyProfile?.defensive), 0)}</td>
                                      <td>{formatNumber(toFiniteNumber(row.strategyProfile?.resource_hoarder), 0)}</td>
                                      <td>{formatNumber(toFiniteNumber(row.strategyProfile?.junction_hunter), 0)}</td>
                                      <td>{formatNumber(toFiniteNumber(row.strategyProfile?.mobile_scout), 0)}</td>
                                      <td>{row.bestProfile ?? '-'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </section>

                        <RolePercentilesPanel
                          roleData={rolePercentiles}
                          loading={roleLoading}
                          error={roleError}
                          mode="metrics"
                          suppressStateMessage
                        />

                        <section className="card">
                          <div className="dashboard-title-line" style={{ marginBottom: 10 }}>
                            <h2 style={{ margin: 0 }}>Analysis</h2>
                            <span className="dashboard-title-subline">
                              Run AI analysis to generate a natural-language summary.
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
                              Key is sent only with this analysis request as <code>X-Anthropic-Api-Key</code>; it is not
                              persisted.
                            </p>
                            <div>
                              <button
                                type="button"
                                onClick={onRunAnalysis}
                                disabled={analysisLoading || loading || !policyVersionId.trim() || !data}
                              >
                                {analysis ? 'Re-run AI analysis' : 'Run AI analysis'}
                              </button>
                            </div>
                          </div>
                          {analysisError && (
                            <div
                              className="card"
                              style={{ padding: 12, borderColor: '#fecdca', background: '#fff7f6' }}
                            >
                              <p style={{ marginTop: 0, marginBottom: 6, color: '#b42318' }}>
                                <strong>Analysis unavailable:</strong> {analysisError}
                              </p>
                              {isAnalysisKeyMissingError(analysisError) && (
                                <p style={{ margin: 0, fontSize: 13, color: '#6b2c2c' }}>
                                  No shared key is configured for this backend. Bring your own key above, or run your
                                  own backend with <code>ANTHROPIC_API_KEY</code> exported.
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
                      </div>
                    </section>
                  </>
                )}
              </section>
            </>
          )}

          {activeTab === 'performance' && (
            <>
              <section className="card grid" style={{ gap: 10 }}>
                <h2 style={{ marginTop: 0, marginBottom: 2 }}>Filters & Export</h2>
                <div className="grid compact-grid" style={{ gap: 10 }}>
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
                      placeholder="e.g. did_align=false && stalled_noop_heavy=true"
                      value={tagQuery}
                      onChange={(event) => setTagQuery(event.target.value)}
                    />
                    <span style={{ fontSize: 12, color: '#4b617f' }}>
                      Supports AND/OR expressions with <code>&amp;&amp;</code>/<code>||</code>. Use <code>!</code> for
                      negation.
                    </span>
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
                      setSelectedEpisodeId(null)
                      setEpisodeSort('reward')
                      setEpisodeSortDir('desc')
                    }}
                  >
                    Reset filters
                  </button>
                  <button type="button" onClick={onExportEpisodes}>
                    Export filtered JSON
                  </button>
                  <button type="button" onClick={onExportBundle}>
                    Export full bundle JSON
                  </button>
                  <span style={{ fontSize: 12, color: '#4b617f' }}>
                    Feedback episode: <code>{selectedEpisodeId ?? '-'}</code> (click a row to set)
                  </span>
                  <span style={{ marginLeft: 'auto', fontSize: 12, color: '#4b617f' }}>
                    {sortedEpisodes.length}/{episodes.length} rows • order: {String(data.selection?.ordering ?? 'n/a')}{' '}
                    • limit: {String(data.selection?.limit ?? 'n/a')}
                  </span>
                </div>
              </section>

              <section className="grid two coordination-layout" style={{ alignItems: 'start' }}>
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
                                Teammate {episodeSort === 'opponent' ? (episodeSortDir === 'asc' ? '▲' : '▼') : ''}
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
                            <th>Status</th>
                            <th>Replay</th>
                            <th>Tags</th>
                          </tr>
                        </thead>
                        <tbody>
                          {sortedEpisodes.slice(0, 200).map((episode) => {
                            const id = episodeIdentifier(episode)
                            const reward = toFiniteNumber(episode.reward ?? episode.avg_reward)
                            const tags = asStringArray(episode.diagnostic_tags)
                            return (
                              <tr
                                key={id}
                                onClick={() => setSelectedEpisodeId(id)}
                                style={
                                  id === selectedEpisodeId
                                    ? { background: 'var(--panel-soft-bg-1)', cursor: 'pointer' }
                                    : { cursor: 'pointer' }
                                }
                              >
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

                <div className="grid" style={{ gap: 10 }}>
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
                        <p style={{ margin: 0 }}>No tags found in sampled episodes.</p>
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
                    <details>
                      <summary>Failed Episodes ({failedEpisodes.length})</summary>
                      <div style={{ marginTop: 10 }}>
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
                                  <th>Teammate</th>
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
                      </div>
                    </details>
                  </section>

                  {data.derived?.crash_dump && (
                    <section className="card">
                      <details>
                        <summary>Crash Dump Report</summary>
                        <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
                          <p style={{ margin: 0 }}>{String(data.derived.crash_dump.headline ?? '-')}</p>

                          {(data.derived.crash_dump.signatures ?? []).length > 0 && (
                            <div className="grid crash-signature-grid" style={{ gap: 8 }}>
                              {(data.derived.crash_dump.signatures ?? []).map((signature) => (
                                <article
                                  key={String(signature.signature ?? signature.error_type ?? 'signature')}
                                  className="card"
                                  style={{ padding: 10 }}
                                >
                                  <p style={{ marginTop: 0, marginBottom: 6 }}>
                                    <strong>{String(signature.error_type ?? 'unknown')}</strong> (
                                    {String(signature.count ?? 0)})
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
                        </div>
                      </details>
                    </section>
                  )}
                </div>
              </section>
            </>
          )}

          {activeTab === 'coordination' && (
            <section className="grid" style={{ gap: 10 }}>
              <section className="grid kpi-grid" style={{ gap: 10 }}>
                <KPIStatCard
                  label="Global Reward Delta"
                  value={formatSigned(matchupGlobalDelta, 3)}
                  severity={kpiSeverity(matchupGlobalDelta, 5, 0)}
                />
                <KPIStatCard
                  label="Teammate Spread"
                  value={formatNumber(matchupOpponentSpread, 3)}
                  severity={kpiSeverity(matchupOpponentSpread, 20, 40, false)}
                />
                <KPIStatCard
                  label="Composition Spread"
                  value={formatNumber(matchupCompositionSpread, 3)}
                  severity={kpiSeverity(matchupCompositionSpread, 12, 24, false)}
                />
                <KPIStatCard
                  label="Matchup Evidence"
                  value={matchup?.evidence_sufficient ? 'sufficient' : 'limited'}
                  severity={matchup?.evidence_sufficient ? 'good' : 'warn'}
                />
              </section>

              {(matchupOpponentSlices.length > 0 || matchupCompositionSlices.length > 0) && (
                <section className="grid table-pair-grid" style={{ gap: 10 }}>
                  {matchupOpponentSlices.length > 0 && (
                    <section className="card">
                      <h2 style={{ marginTop: 0 }}>Teammate Pairing Slices (Current Relative to Baseline)</h2>
                      <div style={{ overflowX: 'auto' }}>
                        <table>
                          <thead>
                            <tr>
                              <th>Paired Policy</th>
                              <th>Current Avg</th>
                              <th>Delta to Baseline</th>
                              <th>Delta to Policy Mean</th>
                            </tr>
                          </thead>
                          <tbody>
                            {matchupOpponentSlices.map((slice) => (
                              <tr key={String(slice.key ?? 'slice')}>
                                <td>{String(slice.key ?? '-')}</td>
                                <td>
                                  {formatNumber(toFiniteNumber(slice.avg_reward), 2)} (
                                  {toFiniteNumber(slice.count) ?? 0})
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

                  {matchupCompositionSlices.length > 0 && (
                    <section className="card">
                      <h2 style={{ marginTop: 0 }}>Composition Slices</h2>
                      <div style={{ overflowX: 'auto' }}>
                        <table>
                          <thead>
                            <tr>
                              <th>Composition</th>
                              <th>Current Avg</th>
                              <th>Delta to Baseline</th>
                              <th>Delta to Policy Mean</th>
                            </tr>
                          </thead>
                          <tbody>
                            {matchupCompositionSlices.map((slice) => (
                              <tr key={String(slice.key ?? 'comp')}>
                                <td>
                                  <code>{String(slice.key ?? '-')}</code>
                                </td>
                                <td>
                                  {formatNumber(toFiniteNumber(slice.avg_reward), 2)} (
                                  {toFiniteNumber(slice.count) ?? 0})
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
                </section>
              )}

              {!matchup && (
                <section className="card">
                  <p style={{ margin: 0 }}>No teammate matchup slices available.</p>
                </section>
              )}

              <section className="grid two overview-dense-grid" style={{ alignItems: 'start' }}>
                <div className="grid" style={{ gap: 10, minWidth: 0 }}>
                  {(unsupported || instrumentation) && (
                    <section className="card" style={{ display: 'grid', gap: 10 }}>
                      <h2 style={{ margin: 0 }}>Data Quality Gates</h2>
                      {unsupported?.has_unsupported_state ? (
                        <div className="grid" style={{ gap: 8 }}>
                          <p style={{ margin: 0, color: '#b42318' }}>
                            Unsupported-state warnings detected ({unsupportedIssueCount}).
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
                                {unsupportedIssues.map((issue) => (
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
                          {instrumentationChecks.length > 0 && (
                            <details>
                              <summary>Instrumentation Checks ({instrumentationChecks.length})</summary>
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
                                    {instrumentationChecks.map((check) => (
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

                  {actionSummary ? (
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
                      <div className="card" style={{ padding: 10, background: 'var(--panel-soft-bg-1)' }}>
                        <p style={{ marginTop: 0, marginBottom: 6 }}>
                          <strong>Auto next run</strong> · focus <code>{trainingFocus}</code>
                        </p>
                        <p style={{ marginTop: 0, marginBottom: 8, fontSize: 13 }}>
                          Suggested curriculum: <code>{autoTrainingHint}</code>
                        </p>
                        <code style={{ display: 'block', whiteSpace: 'pre-wrap' }}>{autoTrainingCommand}</code>
                        <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                          <button type="button" onClick={copyAutoTrainingCommand}>
                            {autoCommandCopied ? 'Copied' : 'Copy run command'}
                          </button>
                        </div>
                      </div>
                    </section>
                  ) : (
                    <section className="card" style={{ display: 'grid', gap: 8 }}>
                      <h2 style={{ margin: 0 }}>Auto Next Run</h2>
                      <p style={{ margin: 0 }}>
                        Focus area inferred from current weaknesses: <code>{trainingFocus}</code>
                      </p>
                      <p style={{ margin: 0, fontSize: 13 }}>
                        Suggested curriculum: <code>{autoTrainingHint}</code>
                      </p>
                      <code style={{ display: 'block', whiteSpace: 'pre-wrap' }}>{autoTrainingCommand}</code>
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <button type="button" onClick={copyAutoTrainingCommand}>
                          {autoCommandCopied ? 'Copied' : 'Copy run command'}
                        </button>
                      </div>
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
                </div>

                <div className="grid" style={{ gap: 10, minWidth: 0 }}>
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
                          Evidence: <strong>{trend.evidence_sufficient ? 'sufficient' : 'limited'}</strong>
                        </span>
                        <span>
                          Covered versions: <code>{trendCoveredVersionCount}</code>/<code>{trendPoints.length}</code>
                        </span>
                        <span>
                          Total matches: <code>{trendTotalMatches}</code>
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

                  <section className="card" style={{ display: 'grid', gap: 8 }}>
                    <h2 style={{ marginTop: 0 }}>Feedback</h2>
                    <p style={{ marginTop: 0, marginBottom: 8, color: '#546b8a' }}>
                      Report dashboard bugs/features with policy, tab, metric, filter, and selected-episode context
                      prefilled.
                    </p>
                    <a href={feedbackUrl} target="_blank" rel="noreferrer">
                      Open dashboard feedback issue
                    </a>
                  </section>
                </div>
              </section>
            </section>
          )}
          {activeTab === 'capabilities' && (
            <section className="grid" style={{ gap: 10 }}>
              <section className="grid kpi-grid" style={{ gap: 10 }}>
                <KPIStatCard
                  label="Capability Coverage"
                  value={formatPercent(capabilityCoverage, 0)}
                  detail={
                    capabilityStatusTotal > 0
                      ? `${capabilityStatusYes} yes · ${capabilityStatusPartial} partial / ${capabilityStatusTotal}`
                      : 'no audit rows'
                  }
                  severity={kpiSeverity(capabilityCoverage, 0.6, 0.35)}
                />
                <KPIStatCard
                  label="Confirmed"
                  value={String(capabilityStatusYes)}
                  detail={
                    capabilityStatusTotal > 0 ? `${formatPercent(capabilityCoverage, 0)} of audited` : 'no audit rows'
                  }
                  severity={kpiSeverity(capabilityCoverage, 0.6, 0.35)}
                />
                <KPIStatCard
                  label="Partial"
                  value={String(capabilityStatusPartial)}
                  detail={
                    capabilityStatusTotal > 0
                      ? `${formatPercent(capabilityPartialRate, 0)} still partial`
                      : 'no audit rows'
                  }
                  severity={kpiSeverity(capabilityPartialRate, 0.2, 0.4, false)}
                />
                <KPIStatCard
                  label="Missing"
                  value={String(capabilityStatusNo)}
                  detail={
                    capabilityStatusTotal > 0 ? `${formatPercent(capabilityMissingRate, 0)} marked no` : 'no audit rows'
                  }
                  severity={kpiSeverity(capabilityMissingRate, 0.1, 0.25, false)}
                />
                <KPIStatCard
                  label="Planned"
                  value={String(capabilityStatusPlanned)}
                  detail={`${capabilityStatusUnknown} unknown status`}
                  severity={capabilityStatusPlanned > 0 || capabilityStatusUnknown > 0 ? 'warn' : 'good'}
                />
                <KPIStatCard
                  label="Support/Evidence"
                  value={`${capabilitySupportTrained}/${capabilitySupportBacked}`}
                  detail={`${capabilityWithEvidenceCount}/${capabilityStatusTotal} with evidence`}
                  severity={
                    capabilityStatusTotal > 0 && capabilityWithEvidenceCount / capabilityStatusTotal >= 0.6
                      ? 'good'
                      : capabilityWithEvidenceCount > 0
                        ? 'warn'
                        : 'bad'
                  }
                />
              </section>

              <SkillTreePanel data={data} diagnoseNote={diagnoseNote} diagnoseManifest={diagnoseManifest} />
            </section>
          )}
          {activeTab === 'pantheon' && (
            <section className="grid" style={{ gap: 10 }}>
              <section className="grid kpi-grid" style={{ gap: 10 }}>
                <KPIStatCard
                  label="Motif Stories"
                  value={String(pantheonStories.length)}
                  detail="Curated Hall of Fame/Lame/Same snippets"
                  severity={pantheonStories.length >= 6 ? 'good' : pantheonStories.length > 0 ? 'warn' : 'bad'}
                />
                <KPIStatCard
                  label="Policies Covered"
                  value={String(pantheonPolicyCount)}
                  detail="Distinct policies represented in this dataset"
                  severity={pantheonPolicyCount >= 3 ? 'good' : pantheonPolicyCount > 0 ? 'warn' : 'bad'}
                />
                <KPIStatCard
                  label="Replay-linked"
                  value={String(pantheonReplayLinkedCount)}
                  detail={`${pantheonStories.length} total stories`}
                  severity={
                    pantheonStories.length > 0 && pantheonReplayLinkedCount === pantheonStories.length
                      ? 'good'
                      : pantheonReplayLinkedCount > 0
                        ? 'warn'
                        : 'bad'
                  }
                />
                <KPIStatCard
                  label="Supervised Seed"
                  value="v0"
                  detail="Bootstrapped motifs while replay-mining pipeline lands"
                  severity="warn"
                />
              </section>

              <section className="card grid" style={{ gap: 8 }}>
                <h2 style={{ margin: 0 }}>Pantheon</h2>
                <p style={{ margin: 0 }}>
                  Replay motif stories grouped as fame/lame/same. This is the supervised seed set for future behavior
                  learning.
                </p>
              </section>

              {pantheonLoading ? (
                <section className="card">
                  <p style={{ margin: 0 }}>Loading Pantheon motifs...</p>
                </section>
              ) : pantheonError ? (
                <section className="card">
                  <p style={{ margin: 0, color: '#b42318' }}>
                    <strong>Error:</strong> {pantheonError}
                  </p>
                </section>
              ) : pantheonStories.length === 0 ? (
                <section className="card">
                  <p style={{ margin: 0 }}>No Pantheon stories found yet.</p>
                </section>
              ) : (
                <section className="pantheon-hall-grid">
                  {PANTHEON_HALLS.map((hall) => (
                    <article key={hall} className={`card pantheon-hall-card pantheon-hall-${hall}`}>
                      <div className="pantheon-hall-head">
                        <h3 style={{ margin: 0 }}>{PANTHEON_HALL_LABELS[hall]}</h3>
                        <span>{pantheonStoriesByHall[hall].length}</span>
                      </div>
                      <div className="grid" style={{ gap: 8 }}>
                        {pantheonStoriesByHall[hall].map((story) => (
                          <article key={story.story_id} className="pantheon-story-card">
                            <div className="pantheon-story-head">
                              <strong>{story.title}</strong>
                              <span>{story.source ?? 'unknown'}</span>
                            </div>
                            <p style={{ margin: 0 }}>{story.motif}</p>
                            <p style={{ margin: 0, color: '#5b7294', fontSize: 13 }}>{story.summary}</p>
                            <p className="pantheon-story-meta">
                              policy <code>{story.policy}</code>
                              {story.run_id ? (
                                <>
                                  {' '}
                                  · run <code>{story.run_id}</code>
                                </>
                              ) : null}
                              {story.episode_id ? (
                                <>
                                  {' '}
                                  · episode <code>{story.episode_id}</code>
                                </>
                              ) : null}
                            </p>
                            {Array.isArray(story.tags) && story.tags.length > 0 ? (
                              <p className="pantheon-story-tags">
                                tags: <code>{story.tags.join(', ')}</code>
                              </p>
                            ) : null}
                            {story.replay_url ? (
                              <a href={story.replay_url} target="_blank" rel="noreferrer">
                                Open replay
                              </a>
                            ) : null}
                          </article>
                        ))}
                      </div>
                    </article>
                  ))}
                </section>
              )}
            </section>
          )}

          <section className="vibeservatory-service-row" aria-label="Vibeservatory services">
            <Link className="vibeservatory-service-link" href="/diagnose">
              Diagnose Service
            </Link>
            <Link className="vibeservatory-service-link vibeservatory-service-link-pantheon" href="/pantheon/v0">
              Pantheon Service
            </Link>
          </section>
        </>
      )}
    </main>
  )
}
