'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  DASHBOARD_API_BASE_URL,
  type DashboardAnalysisResponse,
  type DashboardRolePercentilesResponse,
  type DashboardResponse,
  fetchDashboardAnalysis,
  fetchDashboardData,
  fetchDashboardRolePercentiles,
} from '../lib/api'
import { RolePercentilesPanel } from './RolePercentilesPanel'
import { SkillTreePanel } from './SkillTreePanel'

type DashboardTab = 'overview' | 'episodes' | 'opponents' | 'roles' | 'eval_tree' | 'cogames_diagnose' | 'train_tree'

const DASHBOARD_TABS: DashboardTab[] = [
  'overview',
  'episodes',
  'opponents',
  'roles',
  'eval_tree',
  'cogames_diagnose',
  'train_tree',
]

function parseDashboardTab(value: string | null): DashboardTab | null {
  if (!value) return null
  return DASHBOARD_TABS.find((tab) => tab === value) ?? null
}

type OpponentSummaryRow = {
  opponent: string
  count: number
  completed: number
  avgReward: number | null
  totalReward: number | null
  bestProfile: string | null
  source: 'derived' | 'episodes'
}

function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return value
}

export function DashboardClient() {
  const [policyVersionId, setPolicyVersionId] = useState('')
  const [loading, setLoading] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<DashboardResponse | null>(null)
  const [analysis, setAnalysis] = useState<DashboardAnalysisResponse | null>(null)
  const [rolePercentiles, setRolePercentiles] = useState<DashboardRolePercentilesResponse | null>(null)
  const [roleLoading, setRoleLoading] = useState(false)
  const [roleError, setRoleError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<DashboardTab>('overview')

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
  const diagnostics = useMemo(() => {
    const maybe = data?.derived?.kpis?.diagnostics
    return Array.isArray(maybe) ? maybe : []
  }, [data])
  const opponentRows = useMemo<OpponentSummaryRow[]>(() => {
    const rawOpponentMetrics = data?.derived?.opponent_metrics
    if (rawOpponentMetrics && typeof rawOpponentMetrics === 'object' && !Array.isArray(rawOpponentMetrics)) {
      const rows: OpponentSummaryRow[] = []
      for (const [opponent, raw] of Object.entries(rawOpponentMetrics)) {
        if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
        const record = raw as Record<string, unknown>
        const count = Number(record.count ?? 0)
        if (!Number.isFinite(count) || count <= 0) continue

        const avgReward = toFiniteNumber(record.avg_reward)
        const totalReward = toFiniteNumber(record.total_reward)
        const strategyProfileRaw = record.strategy_profile
        let bestProfile: string | null = null
        if (strategyProfileRaw && typeof strategyProfileRaw === 'object' && !Array.isArray(strategyProfileRaw)) {
          let bestLabel: string | null = null
          let bestScore = Number.NEGATIVE_INFINITY
          for (const [label, score] of Object.entries(strategyProfileRaw)) {
            const numericScore = toFiniteNumber(score)
            if (numericScore === null) continue
            if (numericScore > bestScore) {
              bestScore = numericScore
              bestLabel = label
            }
          }
          bestProfile = bestLabel
        }

        rows.push({
          opponent,
          count,
          completed: count,
          avgReward,
          totalReward,
          bestProfile,
          source: 'derived',
        })
      }
      if (rows.length > 0) {
        return rows.sort((a, b) => b.count - a.count || a.opponent.localeCompare(b.opponent))
      }
    }

    const fallback = new Map<string, { count: number; completed: number; rewardTotal: number; rewardCount: number }>()
    for (const episode of episodes) {
      const opponent = String(episode.opponent_name ?? 'unknown')
      const row = fallback.get(opponent) ?? { count: 0, completed: 0, rewardTotal: 0, rewardCount: 0 }
      row.count += 1
      const status = String(episode.status ?? '')
      const reward = toFiniteNumber(episode.reward ?? episode.avg_reward)
      if (status === 'completed') {
        row.completed += 1
        if (reward !== null) {
          row.rewardTotal += reward
          row.rewardCount += 1
        }
      }
      fallback.set(opponent, row)
    }
    const rows: OpponentSummaryRow[] = [...fallback.entries()].map(([opponent, row]) => ({
      opponent,
      count: row.count,
      completed: row.completed,
      avgReward: row.rewardCount > 0 ? row.rewardTotal / row.rewardCount : null,
      totalReward: row.rewardCount > 0 ? row.rewardTotal : null,
      bestProfile: null,
      source: 'episodes',
    }))
    return rows.sort((a, b) => b.count - a.count || a.opponent.localeCompare(b.opponent))
  }, [data, episodes])
  const bestWorstOpponents = useMemo(() => {
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

  const loadDashboardData = useCallback(async (rawPolicyVersionId: string) => {
    const trimmedPolicyVersionId = rawPolicyVersionId.trim()
    if (!trimmedPolicyVersionId) return

    setError(null)
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
    setError(null)
    setAnalysisLoading(true)
    try {
      const response = await fetchDashboardAnalysis(policyVersionId.trim())
      setAnalysis(response)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
    } finally {
      setAnalysisLoading(false)
    }
  }

  useEffect(() => {
    if (activeTab !== 'roles') return
    const loadedPolicyVersionId = data?.policy?.id
    if (!loadedPolicyVersionId) return

    let cancelled = false
    setRoleLoading(true)
    setRoleError(null)

    void fetchDashboardRolePercentiles(String(loadedPolicyVersionId))
      .then((response) => {
        if (cancelled) return
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
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const initialPolicyVersionId = params.get('policyVersionId')?.trim()
    const initialTab = parseDashboardTab(params.get('tab'))
    if (initialTab) {
      setActiveTab(initialTab)
    }
    if (!initialPolicyVersionId) return
    setPolicyVersionId(initialPolicyVersionId)
    void loadDashboardData(initialPolicyVersionId)
  }, [loadDashboardData])

  return (
    <main className="grid" style={{ gap: 16 }}>
      <header className="card">
        <h1 style={{ marginTop: 0 }}>Standalone Dashboard</h1>
        <p style={{ marginBottom: 0 }}>
          Backend: <code>{DASHBOARD_API_BASE_URL}</code>
        </p>
      </header>

      <section className="card grid" style={{ gap: 12 }}>
        <label htmlFor="policy-version-id">Policy version id</label>
        <input
          id="policy-version-id"
          placeholder="UUID"
          value={policyVersionId}
          onChange={(event) => setPolicyVersionId(event.target.value)}
        />
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button type="button" onClick={onLoad} disabled={loading || !policyVersionId.trim()}>
            {loading ? 'Loading...' : 'Load dashboard data'}
          </button>
          <button type="button" onClick={onRunAnalysis} disabled={analysisLoading || !policyVersionId.trim() || !data}>
            {analysisLoading ? 'Running analysis...' : 'Run diagnostics analysis'}
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
          <section className="card tab-row">
            <button
              type="button"
              onClick={() => activateTab('overview')}
              className={activeTab === 'overview' ? 'active-tab' : ''}
            >
              Overview
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
              onClick={() => activateTab('opponents')}
              className={activeTab === 'opponents' ? 'active-tab' : ''}
            >
              Opponents
            </button>
            <button
              type="button"
              onClick={() => activateTab('roles')}
              className={activeTab === 'roles' ? 'active-tab' : ''}
            >
              Roles
            </button>
            <button
              type="button"
              onClick={() => activateTab('eval_tree')}
              className={activeTab === 'eval_tree' ? 'active-tab' : ''}
            >
              Eval Tree
            </button>
            <button
              type="button"
              onClick={() => activateTab('cogames_diagnose')}
              className={activeTab === 'cogames_diagnose' ? 'active-tab' : ''}
            >
              Cogames Diagnose
            </button>
            <button
              type="button"
              onClick={() => activateTab('train_tree')}
              className={activeTab === 'train_tree' ? 'active-tab' : ''}
            >
              Train Tree
            </button>
          </section>

          {activeTab === 'overview' && (
            <>
              <section className="grid two">
                <article className="card">
                  <h2 style={{ marginTop: 0 }}>Policy</h2>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{JSON.stringify(data.policy ?? {}, null, 2)}</pre>
                </article>
                <article className="card">
                  <h2 style={{ marginTop: 0 }}>KPI Snapshot</h2>
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(data.derived?.kpis ?? {}, null, 2)}
                  </pre>
                </article>
              </section>

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Diagnostics ({diagnostics.length})</h2>
                {diagnostics.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No diagnostics emitted.</p>
                ) : (
                  <ul style={{ marginBottom: 0 }}>
                    {diagnostics.map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))}
                  </ul>
                )}
              </section>

              {analysis && (
                <section className="card">
                  <h2 style={{ marginTop: 0 }}>AI Analysis</h2>
                  <p style={{ marginTop: 0, whiteSpace: 'pre-wrap' }}>{analysis.analysis}</p>
                  <h3>Data sources</h3>
                  <ul style={{ marginBottom: 0 }}>
                    {analysis.data_sources.map((source) => (
                      <li key={source}>{source}</li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          )}

          {activeTab === 'episodes' && (
            <>
              <section className="card">
                <h2 style={{ marginTop: 0 }}>Episodes ({episodes.length})</h2>
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Status</th>
                        <th>Reward</th>
                        <th>Steps</th>
                        <th>Opponent</th>
                        <th>Team</th>
                        <th>Diagnostics</th>
                      </tr>
                    </thead>
                    <tbody>
                      {episodes.slice(0, 200).map((episode) => {
                        const id = String(episode.episode_id ?? episode.id ?? '')
                        const status = String(episode.status ?? '')
                        const rewardNumber = toFiniteNumber(episode.reward ?? episode.avg_reward)
                        const reward = rewardNumber === null ? '' : rewardNumber.toFixed(3)
                        const steps = String(episode.steps ?? '')
                        const opponent = String(episode.opponent_name ?? '')
                        const teamComposition = String(episode.team_composition ?? '')
                        const tags = Array.isArray(episode.diagnostic_tags)
                          ? episode.diagnostic_tags.map((value) => String(value)).join(', ')
                          : ''

                        return (
                          <tr key={id}>
                            <td>
                              <code>{id}</code>
                            </td>
                            <td>{status}</td>
                            <td>{reward}</td>
                            <td>{steps}</td>
                            <td>{opponent}</td>
                            <td>{teamComposition}</td>
                            <td>{tags}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}

          {activeTab === 'opponents' && (
            <>
              <section className="grid two">
                <article className="card">
                  <h2 style={{ marginTop: 0 }}>Best matchup</h2>
                  {bestWorstOpponents?.best ? (
                    <p style={{ marginBottom: 0 }}>
                      <strong>{bestWorstOpponents.best.opponent}</strong>{' '}
                      <span>(avg reward {bestWorstOpponents.best.avgReward?.toFixed(3)})</span>
                    </p>
                  ) : (
                    <p style={{ marginBottom: 0 }}>No matchup reward data yet.</p>
                  )}
                </article>
                <article className="card">
                  <h2 style={{ marginTop: 0 }}>Worst matchup</h2>
                  {bestWorstOpponents?.worst ? (
                    <p style={{ marginBottom: 0 }}>
                      <strong>{bestWorstOpponents.worst.opponent}</strong>{' '}
                      <span>(avg reward {bestWorstOpponents.worst.avgReward?.toFixed(3)})</span>
                    </p>
                  ) : (
                    <p style={{ marginBottom: 0 }}>No matchup reward data yet.</p>
                  )}
                </article>
              </section>

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Opponent metrics ({opponentRows.length})</h2>
                {opponentRows.length === 0 ? (
                  <p style={{ marginBottom: 0 }}>No opponent metrics available.</p>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Opponent</th>
                          <th>Episodes</th>
                          <th>Completed</th>
                          <th>Avg Reward</th>
                          <th>Total Reward</th>
                          <th>Top Profile</th>
                          <th>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {opponentRows.map((row) => (
                          <tr key={row.opponent}>
                            <td>{row.opponent}</td>
                            <td>{row.count}</td>
                            <td>{row.completed}</td>
                            <td>{row.avgReward === null ? '' : row.avgReward.toFixed(3)}</td>
                            <td>{row.totalReward === null ? '' : row.totalReward.toFixed(3)}</td>
                            <td>{row.bestProfile ?? ''}</td>
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

          {activeTab === 'roles' && (
            <RolePercentilesPanel roleData={rolePercentiles} loading={roleLoading} error={roleError} />
          )}
          {activeTab === 'eval_tree' && <SkillTreePanel mode="eval" data={data} />}
          {activeTab === 'cogames_diagnose' && (
            <SkillTreePanel mode="eval" data={data} initialSourceFilter="cogames-diagnose" lockSourceFilter />
          )}
          {activeTab === 'train_tree' && <SkillTreePanel mode="train" data={data} />}
        </>
      )}
    </main>
  )
}
