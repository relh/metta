'use client'

import { FC } from 'react'

import { Card } from '@/components/Card'
import type { DashboardResponse } from '@/lib/repo'

export const PatternCard: FC<{ data: DashboardResponse }> = ({ data }) => {
  const patterns = data.derived.patterns
  if (!patterns || !patterns.evidence_sufficient) return null

  return (
    <Card title="Pattern Extraction">
      {/* Always visible: headline */}
      <p className="text-sm text-foreground">{patterns.headline}</p>

      {/* Collapsible: signals */}
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-medium text-foreground-subtle hover:text-foreground">
          Detected Signals ({patterns.signals.length})
        </summary>
        <div className="mt-2 space-y-2">
          {patterns.signals.map((signal) => (
            <div
              key={signal.code}
              className={`rounded border p-3 ${
                signal.severity === 'high'
                  ? 'bg-red-50 border-red-200'
                  : signal.severity === 'warn'
                    ? 'bg-yellow-50 border-yellow-200'
                    : 'bg-blue-50 border-blue-200'
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">{signal.title}</span>
                <span className="text-[10px] uppercase tracking-wide text-foreground-muted">
                  {signal.confidence} confidence
                </span>
              </div>
              <p className="text-xs text-foreground-subtle mt-1">{signal.evidence}</p>
              <p className="text-xs text-foreground mt-1">{signal.next_action}</p>
            </div>
          ))}
        </div>
      </details>
    </Card>
  )
}
