'use client'

import { useMemo } from 'react'

import type { DashboardRoleMetricDef, DashboardRolePercentilesResponse, DashboardRolePercentileRow } from '../lib/api'

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

function roleSortIndex(role: string): number {
  return ROLE_ORDER.indexOf(role as (typeof ROLE_ORDER)[number])
}

function compareRoleNames(leftRole: string, rightRole: string): number {
  const leftIndex = roleSortIndex(leftRole)
  const rightIndex = roleSortIndex(rightRole)
  if (leftIndex === -1 && rightIndex === -1) return leftRole.localeCompare(rightRole)
  if (leftIndex === -1) return 1
  if (rightIndex === -1) return -1
  return leftIndex - rightIndex
}

function parseRows(
  rows: DashboardRolePercentileRow[],
  definitions: Record<string, DashboardRoleMetricDef[]>
): ParsedRole[] {
  const parsedRows = rows.map((row) => {
    const details = isObject(row.details) ? row.details : {}
    const metricMap = isObject(details.metrics) ? details.metrics : {}
    const defsForRole = definitions[row.role] ?? []
    const metrics: MetricDetail[] = defsForRole
      .map((definition) => {
        const metricDetails = metricMap[definition.key]
        if (!isObject(metricDetails)) return null
        const higherIsBetter =
          typeof metricDetails.higher_is_better === 'boolean'
            ? metricDetails.higher_is_better
            : definition.higher_is_better

        return {
          key: definition.key,
          avg: asFiniteNumber(metricDetails.avg),
          percentile: asFiniteNumber(metricDetails.percentile),
          higherIsBetter,
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

  return parsedRows.sort((left, right) => compareRoleNames(left.role, right.role))
}

function RolePercentilesMessageCard({ message, color }: { message: string; color?: string }) {
  return (
    <section className="card">
      <h2 style={{ marginTop: 0 }}>Parses</h2>
      <p style={{ marginBottom: 0, color }}>{message}</p>
    </section>
  )
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

  const parseMetricRows = useMemo(() => {
    if (!roleData?.roles) return []
    const entries = Object.entries(roleData.roles)
    entries.sort((left, right) => compareRoleNames(left[0], right[0]))

    return entries
      .map(([role, definitions]) => {
        const keys = definitions.map((definition) => definition.key)
        if (keys.length === 0) return null
        return {
          role,
          keys,
        }
      })
      .filter((entry): entry is { role: string; keys: string[] } => entry !== null)
  }, [roleData])

  if (loading) {
    return <RolePercentilesMessageCard message="Loading parse percentile metrics..." />
  }

  if (error) {
    return <RolePercentilesMessageCard message={error} color="#b42318" />
  }

  if (parsedRows.length === 0) {
    return (
      <RolePercentilesMessageCard message="No parse percentile data yet for this policy in the selected pool. This is expected on read-only/new environments until percentile backfill runs." />
    )
  }

  return (
    <section className="grid" style={{ gap: 12 }}>
      <article className="card">
        <h2 style={{ marginTop: 0 }}>Parse Percentile Summary</h2>
        <p style={{ marginTop: 0, color: '#405a7d' }}>
          {roleData?.pool_name ? `Pool: ${roleData.pool_name}` : 'Pool: unknown'} | Parses scored: {parsedRows.length}
        </p>
        <p style={{ marginTop: 0, marginBottom: 8, fontSize: 12, color: '#4b617f' }}>
          Parses are backend percentile ranks computed from role-defining shaped metrics, plus deaths for every role.
        </p>
        {parseMetricRows.length > 0 && (
          <div style={{ display: 'grid', gap: 4, marginBottom: 10 }}>
            {parseMetricRows.map((row) => (
              <p key={row.role} style={{ margin: 0, fontSize: 12, color: '#4b617f', overflowWrap: 'anywhere' }}>
                <strong>{ROLE_LABELS[row.role] ?? row.role}:</strong> {row.keys.join(', ')}
              </p>
            ))}
          </div>
        )}
        <div className="role-grid">
          {parsedRows.map((row) => (
            <div key={row.role} className="role-card">
              <p className="role-card-title">{ROLE_LABELS[row.role] ?? row.role}</p>
              <p className={`role-card-value ${percentileClass(row.percentile)}`}>P{row.percentile.toFixed(1)}</p>
              <div className="role-progress">
                <div
                  className="role-progress-bar"
                  style={{ width: `${Math.max(0, Math.min(row.percentile, 100))}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </article>

      {parsedRows.map((row) => (
        <article key={row.role} className="card">
          <h3 style={{ marginTop: 0 }}>{ROLE_LABELS[row.role] ?? row.role} Parse Metrics</h3>
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
