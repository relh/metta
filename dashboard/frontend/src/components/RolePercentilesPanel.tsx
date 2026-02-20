'use client'

import { useMemo } from 'react'

import type {
  DashboardRoleMetricDef,
  DashboardRolePercentilesResponse,
  DashboardRolePercentileRow,
} from '../lib/api'

type MetricDetail = {
  key: string
  avg: number | null
  percentile: number | null
  higherIsBetter: boolean
  samples: number | null
}

type ParsedRole = {
  role: string
  percentile: number
  metrics: MetricDetail[]
}

const ROLE_ORDER = ['aligner', 'miner', 'scrambler', 'scout'] as const

const ROLE_LABELS: Record<string, string> = {
  aligner: 'Aligner',
  miner: 'Miner',
  scrambler: 'Scrambler',
  scout: 'Scout',
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function percentileClass(percentile: number): string {
  if (percentile >= 90) return 'percentile-top'
  if (percentile >= 70) return 'percentile-high'
  if (percentile >= 40) return 'percentile-mid'
  return 'percentile-low'
}

function parseRows(
  rows: DashboardRolePercentileRow[],
  definitions: Record<string, DashboardRoleMetricDef[]>
): ParsedRole[] {
  const parsedRows = rows.map((row) => {
    const details = isObject(row.details) ? row.details : {}
    const metricMap = isObject(details.metrics) ? details.metrics : {}
    const defsForRole = definitions[row.role] ?? []
    const orderedMetricKeys =
      defsForRole.length > 0 ? defsForRole.map((def) => def.key) : Object.keys(metricMap).sort((a, b) => a.localeCompare(b))

    const metrics: MetricDetail[] = orderedMetricKeys
      .map((metricKey) => {
        const metricDetails = metricMap[metricKey]
        if (!isObject(metricDetails)) return null
        const fallbackDef = defsForRole.find((def) => def.key === metricKey)

        return {
          key: metricKey,
          avg: asFiniteNumber(metricDetails.avg),
          percentile: asFiniteNumber(metricDetails.percentile),
          higherIsBetter:
            typeof metricDetails.higher_is_better === 'boolean'
              ? metricDetails.higher_is_better
              : (fallbackDef?.higher_is_better ?? true),
          samples: asFiniteNumber(metricDetails.samples),
        }
      })
      .filter((metric): metric is MetricDetail => metric !== null)

    return {
      role: row.role,
      percentile: row.percentile,
      metrics,
    }
  })

  return parsedRows.sort((left, right) => {
    const leftIndex = ROLE_ORDER.indexOf(left.role as (typeof ROLE_ORDER)[number])
    const rightIndex = ROLE_ORDER.indexOf(right.role as (typeof ROLE_ORDER)[number])
    if (leftIndex === -1 && rightIndex === -1) return left.role.localeCompare(right.role)
    if (leftIndex === -1) return 1
    if (rightIndex === -1) return -1
    return leftIndex - rightIndex
  })
}

export function RolePercentilesPanel({
  roleData,
  loading,
  error,
}: {
  roleData: DashboardRolePercentilesResponse | null
  loading: boolean
  error: string | null
}) {
  const parsedRows = useMemo(() => {
    if (!roleData?.rows?.length) return []
    return parseRows(roleData.rows, roleData.roles)
  }, [roleData])

  if (loading) {
    return (
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Role Percentiles</h2>
        <p style={{ marginBottom: 0 }}>Loading role percentile metrics...</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Role Percentiles</h2>
        <p style={{ marginBottom: 0, color: '#b42318' }}>{error}</p>
      </section>
    )
  }

  if (parsedRows.length === 0) {
    return (
      <section className="card">
        <h2 style={{ marginTop: 0 }}>Role Percentiles</h2>
        <p style={{ marginBottom: 0 }}>No role percentile data is available for this policy in the selected pool.</p>
      </section>
    )
  }

  return (
    <section className="grid" style={{ gap: 12 }}>
      <article className="card">
        <h2 style={{ marginTop: 0 }}>Role Percentile Summary</h2>
        <p style={{ marginTop: 0, color: '#405a7d' }}>
          {roleData?.pool_name ? `Pool: ${roleData.pool_name}` : 'Pool: unknown'} | Roles scored: {parsedRows.length}
        </p>
        <div className="role-grid">
          {parsedRows.map((row) => (
            <div key={row.role} className="role-card">
              <p className="role-card-title">{ROLE_LABELS[row.role] ?? row.role}</p>
              <p className={`role-card-value ${percentileClass(row.percentile)}`}>P{row.percentile.toFixed(1)}</p>
              <div className="role-progress">
                <div className="role-progress-bar" style={{ width: `${Math.max(0, Math.min(row.percentile, 100))}%` }} />
              </div>
            </div>
          ))}
        </div>
      </article>

      {parsedRows.map((row) => (
        <article key={row.role} className="card">
          <h3 style={{ marginTop: 0 }}>{ROLE_LABELS[row.role] ?? row.role} Metrics</h3>
          {row.metrics.length === 0 ? (
            <p style={{ marginBottom: 0 }}>No metric breakdown was returned for this role.</p>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Average</th>
                    <th>Percentile</th>
                    <th>Direction</th>
                    <th>Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {row.metrics.map((metric) => (
                    <tr key={`${row.role}-${metric.key}`}>
                      <td>
                        <code>{metric.key}</code>
                      </td>
                      <td>{metric.avg === null ? '-' : metric.avg.toFixed(3)}</td>
                      <td className={metric.percentile === null ? '' : percentileClass(metric.percentile)}>
                        {metric.percentile === null ? '-' : `P${metric.percentile.toFixed(1)}`}
                      </td>
                      <td>{metric.higherIsBetter ? 'Higher is better' : 'Lower is better'}</td>
                      <td>{metric.samples === null ? '-' : metric.samples.toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      ))}
    </section>
  )
}
