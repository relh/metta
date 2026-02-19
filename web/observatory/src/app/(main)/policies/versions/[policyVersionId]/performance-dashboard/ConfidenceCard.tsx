'use client'

import { FC } from 'react'

import { Card } from '@/components/Card'
import type { DashboardResponse } from '@/lib/repo'

import { formatSigned } from './shared'

export const ConfidenceCard: FC<{ data: DashboardResponse }> = ({ data }) => {
  const confidence = data.derived.confidence
  if (!confidence) return null

  return (
    <Card title="Confidence Intervals">
      {/* Always visible: one-line summary */}
      <p className="text-sm text-foreground">
        Evidence:{' '}
        <span
          className={confidence.evidence_sufficient ? 'text-green-700 font-semibold' : 'text-yellow-700 font-semibold'}
        >
          {confidence.evidence_sufficient ? 'sufficient' : 'limited'}
        </span>
      </p>

      {/* Collapsible: full table */}
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-foreground-subtle hover:text-foreground">
          Interval Details
        </summary>
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Metric</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Point &Delta;
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">CI Low</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">CI High</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Samples</th>
                <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                  Interpretation
                </th>
              </tr>
            </thead>
            <tbody>
              {confidence.intervals.map((interval) => (
                <tr key={interval.key} className="border-b border-border-subtle">
                  <td className="px-3 py-2">{interval.label}</td>
                  <td className="px-3 py-2 font-mono">
                    {interval.point_estimate === null ? '-' : formatSigned(interval.point_estimate, 3)}
                  </td>
                  <td className="px-3 py-2 font-mono">{interval.lower === null ? '-' : interval.lower.toFixed(3)}</td>
                  <td className="px-3 py-2 font-mono">{interval.upper === null ? '-' : interval.upper.toFixed(3)}</td>
                  <td className="px-3 py-2 font-mono">
                    {interval.current_samples}/{interval.baseline_samples}
                  </td>
                  <td
                    className={`px-3 py-2 text-xs ${
                      interval.crosses_zero === false
                        ? 'text-green-700'
                        : interval.crosses_zero === true
                          ? 'text-yellow-700'
                          : 'text-foreground-muted'
                    }`}
                  >
                    {interval.interpretation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {confidence.recommended_actions.length > 0 && (
          <ul className="mt-3 space-y-1">
            {confidence.recommended_actions.map((action, idx) => (
              <li key={idx} className="text-xs text-foreground-subtle">
                {idx + 1}. {action}
              </li>
            ))}
          </ul>
        )}
      </details>
    </Card>
  )
}
