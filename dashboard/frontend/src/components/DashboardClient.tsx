'use client'

import { useEffect, useMemo, useState } from 'react'

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

type DashboardTab = 'overview' | 'roles' | 'eval_tree' | 'train_tree'

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

  const episodes = useMemo(() => (Array.isArray(data?.episodes) ? data.episodes : []), [data])
  const diagnostics = useMemo(() => {
    const maybe = data?.derived?.kpis?.diagnostics
    return Array.isArray(maybe) ? maybe : []
  }, [data])

  const onLoad = async () => {
    setError(null)
    setAnalysis(null)
    setRolePercentiles(null)
    setRoleError(null)
    setRoleLoading(false)
    setLoading(true)
    try {
      const response = await fetchDashboardData(policyVersionId.trim())
      setData(response)
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      setError(message)
    } finally {
      setLoading(false)
    }
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
            <button type="button" onClick={() => setActiveTab('overview')} className={activeTab === 'overview' ? 'active-tab' : ''}>
              Overview
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('roles')}
              className={activeTab === 'roles' ? 'active-tab' : ''}
            >
              Roles
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('eval_tree')}
              className={activeTab === 'eval_tree' ? 'active-tab' : ''}
            >
              Eval Tree
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('train_tree')}
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

              <section className="card">
                <h2 style={{ marginTop: 0 }}>Episodes ({episodes.length})</h2>
                <div style={{ overflowX: 'auto' }}>
                  <table>
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Status</th>
                        <th>Reward</th>
                        <th>Opponent</th>
                        <th>Diagnostics</th>
                      </tr>
                    </thead>
                    <tbody>
                      {episodes.slice(0, 40).map((episode) => {
                        const id = String(episode.episode_id ?? episode.id ?? '')
                        const status = String(episode.status ?? '')
                        const reward = String(episode.avg_reward ?? episode.reward ?? '')
                        const opponent = String(episode.opponent_name ?? '')
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
                            <td>{opponent}</td>
                            <td>{tags}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
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

          {activeTab === 'roles' && <RolePercentilesPanel roleData={rolePercentiles} loading={roleLoading} error={roleError} />}
          {activeTab === 'eval_tree' && <SkillTreePanel mode="eval" data={data} />}
          {activeTab === 'train_tree' && <SkillTreePanel mode="train" data={data} />}
        </>
      )}
    </main>
  )
}
