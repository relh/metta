'use client'

import { FC } from 'react'

import { Card } from '@/components/Card'
import type { DashboardResponse } from '@/lib/repo'

import { KpiCard } from './shared'

export const HealthTab: FC<{ data: DashboardResponse }> = ({ data }) => {
  const failures = data.derived.failures
  const crashDump = data.derived.crash_dump
  const failedEpisodes = data.episodes.filter((e) => e.status === 'failed')

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard
          label="Failed Episodes"
          value={`${failures.failed_episodes}`}
          detail={`${(failures.failed_rate * 100).toFixed(1)}% of sampled episodes`}
          severity={failures.failed_rate >= 0.1 ? 'bad' : failures.failed_rate >= 0.03 ? 'warn' : 'good'}
        />
        <KpiCard
          label="Timeout Failures"
          value={`${failures.timeout_failures}`}
          severity={failures.timeout_failures > 0 ? 'bad' : 'good'}
        />
        <KpiCard
          label="OOM Failures"
          value={`${failures.oom_failures}`}
          severity={failures.oom_failures > 0 ? 'bad' : 'good'}
        />
        <KpiCard
          label="Crash Failures"
          value={`${failures.crash_failures + failures.other_failures}`}
          detail={`${failures.crash_failures} classified + ${failures.other_failures} other`}
          severity={failures.crash_failures + failures.other_failures > 0 ? 'bad' : 'good'}
        />
        <KpiCard
          label="Freeze-Heavy (Completed)"
          value={`${failures.freeze_heavy_completed}`}
          severity={failures.freeze_heavy_completed > 0 ? 'warn' : 'good'}
        />
        <KpiCard
          label="Noop-Heavy (Completed)"
          value={`${failures.noop_heavy_completed}`}
          severity={failures.noop_heavy_completed > 0 ? 'warn' : 'good'}
        />
      </div>

      <Card title={`Failed Episodes (${failedEpisodes.length})`}>
        {failedEpisodes.length === 0 ? (
          <p className="text-sm text-foreground-muted">No failed episodes in the sampled data</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Job ID</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">
                    Error Type
                  </th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Opponent</th>
                  <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Team</th>
                </tr>
              </thead>
              <tbody>
                {failedEpisodes.map((ep) => (
                  <tr key={ep.episode_id} className="border-b border-border-subtle hover:bg-surface-alt">
                    <td className="px-3 py-2 font-mono text-xs">{ep.job_id || '-'}</td>
                    <td className="px-3 py-2 font-mono">{ep.error_type || 'unknown'}</td>
                    <td className="px-3 py-2">
                      {ep.opponent_name} v{ep.opponent_version}
                    </td>
                    <td className="px-3 py-2 font-mono">{ep.team_composition}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {crashDump && (
        <Card title="Crash Dump Report">
          <p className="text-sm text-foreground">{crashDump.headline}</p>
          {crashDump.signatures.length > 0 && (
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
              {crashDump.signatures.map((signature) => (
                <div key={signature.signature} className="rounded border border-rose-200 bg-rose-50 p-2">
                  <p className="text-xs font-semibold text-rose-900">
                    {signature.error_type} ({signature.count})
                  </p>
                  {signature.example_message && (
                    <p className="text-xs text-rose-800 mt-1">{signature.example_message}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          {crashDump.entries.length > 0 && (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Job</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Type</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Message</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-foreground-muted uppercase">Analyze</th>
                  </tr>
                </thead>
                <tbody>
                  {crashDump.entries.map((entry) => (
                    <tr key={entry.episode_id} className="border-b border-border-subtle hover:bg-surface-alt">
                      <td className="px-3 py-2 font-mono text-xs">{entry.job_id || '-'}</td>
                      <td className="px-3 py-2 font-mono text-xs">{entry.error_type || 'unknown'}</td>
                      <td className="px-3 py-2 text-xs text-foreground-subtle">{entry.error_message || '-'}</td>
                      <td className="px-3 py-2">
                        <code className="text-[11px] text-foreground-subtle">{entry.analysis_command}</code>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </>
  )
}
