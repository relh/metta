'use client'
import { FC, useCallback, useRef, useState } from 'react'

import { normalizeReplayUrl, normalizeVibescopeUrl } from '@/components/ReplayViewer'
import { StyledLink } from '@/components/StyledLink'
import { TD, TR } from '@/components/Table'
import { METTA_GITHUB_ORGANIZATION, METTA_GITHUB_REPO } from '@/constants'
import { JobRequest } from '@/lib/repo'
import { formatDurationBetween, formatDurationSince } from '@/utils/datetime'

import { LabelRow, LabelValueTable } from './LabelValueTable'
import { PolicyLink } from './PolicyLink'
import { StatusBadge } from './StatusBadge'
import { Timeline } from './Timeline'

const MAX_VISIBLE_TAGS = 2

const TagPill: FC<{ k: string; v: string; truncate?: boolean }> = ({ k, v, truncate }) => (
  <span
    className={`px-1 py-0.5 bg-gray-100 text-gray-600 text-[10px] rounded-full whitespace-nowrap ${truncate ? 'inline-block max-w-[180px] truncate' : ''}`}
    title={`${k}: ${v}`}
  >
    {k}={v}
  </span>
)

const Tags: FC<{ tags: Record<string, string> }> = ({ tags }) => {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const entries = Object.entries(tags)
  const visible = entries.slice(0, MAX_VISIBLE_TAGS)
  const overflow = entries.slice(MAX_VISIBLE_TAGS)

  return (
    <div className="relative" ref={ref}>
      <div className="flex flex-wrap gap-0.5 items-center">
        {visible.map(([k, v]) => (
          <TagPill key={k} k={k} v={v} />
        ))}
        {overflow.length > 0 && (
          <button
            onClick={() => setOpen(!open)}
            className="px-1 py-0.5 bg-gray-200 text-gray-500 text-[10px] rounded-full whitespace-nowrap bg-transparent border-none cursor-pointer p-0 hover:text-gray-800"
          >
            +{overflow.length}
          </button>
        )}
      </div>
      {open && (
        <div className="absolute z-10 top-full left-0 mt-1 p-1.5 bg-white border border-gray-200 rounded shadow-lg flex flex-col gap-0.5">
          {entries.map(([k, v]) => (
            <TagPill key={k} k={k} v={v} truncate />
          ))}
        </div>
      )}
    </div>
  )
}

function parseRunnerImageShort(runnerImage: string | undefined): string | null {
  if (!runnerImage) return null
  const digestMatch = runnerImage.match(/sha256:([a-f0-9]+)/)
  if (digestMatch) return digestMatch[1].slice(0, 12)
  const lastColon = runnerImage.lastIndexOf(':')
  if (lastColon === -1) return runnerImage.split('/').pop() ?? runnerImage
  return runnerImage.slice(lastColon + 1)
}

const CopyButton: FC<{ text: string; children: React.ReactNode; className?: string; title?: string }> = ({
  text,
  children,
  className,
  title,
}) => {
  const [copied, setCopied] = useState(false)
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [text])

  return (
    <button
      onClick={handleCopy}
      className={`bg-transparent border-none cursor-pointer p-0 ${className ?? ''}`}
      title={title ?? text}
    >
      {copied ? <span className="text-green-600">Copied!</span> : children}
    </button>
  )
}

function truncateValue(value: unknown, depth: number = 0): unknown {
  if (depth > 4) return '...'
  if (typeof value === 'string' && value.length > 80) return value.slice(0, 80) + '...'
  if (Array.isArray(value)) {
    const truncated = value.slice(0, 10).map((v) => truncateValue(v, depth + 1))
    if (value.length > 10) truncated.push(`... +${value.length - 10} more`)
    return truncated
  }
  if (value && typeof value === 'object') {
    const result: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value)) {
      result[k] = truncateValue(v, depth + 1)
    }
    return result
  }
  return value
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toFixed(4)
}

const ExpandDownloadRow: FC<{ label: string; data: unknown; show: boolean; onToggle: () => void }> = ({
  label,
  data,
  show,
  onToggle,
}) => (
  <LabelRow label={label}>
    <span className="flex gap-1.5 justify-end">
      <button
        onClick={onToggle}
        className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
      >
        {show ? 'Collapse' : 'Expand'}
      </button>
      <button
        onClick={() => {
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
          const url = URL.createObjectURL(blob)
          const a = document.createElement('a')
          a.href = url
          a.download = `${label.toLowerCase().replace(/\s+/g, '-')}.json`
          a.click()
          URL.revokeObjectURL(url)
        }}
        className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
      >
        Download
      </button>
    </span>
  </LabelRow>
)

const ExpansionPanel: FC<{ label: string; content: string; copyContent?: string; onClose: () => void }> = ({
  label,
  content,
  copyContent,
  onClose,
}) => {
  const [copied, setCopied] = useState(false)
  return (
    <div className="max-w-0 min-w-full overflow-hidden">
      <div className="flex items-center justify-between bg-gray-100 border border-gray-200 border-b-0 rounded-t px-3 py-1.5">
        <span className="text-xs font-semibold text-gray-600">{label}</span>
        <span className="flex gap-2">
          <button
            onClick={() => {
              navigator.clipboard.writeText(copyContent ?? content)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
            className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0 text-xs"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-800 bg-transparent border-none cursor-pointer p-0 text-xs"
          >
            Close
          </button>
        </span>
      </div>
      <pre className="bg-gray-50 border border-gray-200 rounded-b p-3 text-[11px] overflow-auto max-h-[500px] m-0 whitespace-pre-wrap break-all">
        {content}
      </pre>
    </div>
  )
}

function getTimeDisplay(job: JobRequest): { primary: string; secondary?: string } {
  if (job.status === 'completed' || job.status === 'failed') {
    const runDur = formatDurationBetween(job.running_at, job.completed_at)
    const overallDur = formatDurationBetween(job.created_at, job.completed_at)
    if (runDur && overallDur && runDur !== overallDur) {
      return { primary: `${runDur} running`, secondary: `${overallDur} total` }
    }
    if (runDur) return { primary: `${runDur} running` }
    if (overallDur) return { primary: overallDur }
    return { primary: '—' }
  }
  if (job.status === 'running') {
    const dur = formatDurationSince(job.running_at)
    return dur ? { primary: `${dur} running` } : { primary: '—' }
  }
  if (job.status === 'dispatched') {
    const dur = formatDurationSince(job.dispatched_at)
    return dur ? { primary: `${dur} waiting` } : { primary: '—' }
  }
  return { primary: '—' }
}

function computeAgentCounts(assignments: number[] | undefined): Map<number, number> {
  const counts = new Map<number, number>()
  if (!assignments) return counts
  for (const policyIdx of assignments) {
    counts.set(policyIdx, (counts.get(policyIdx) ?? 0) + 1)
  }
  return counts
}

export const JobRow: FC<{ job: JobRequest }> = ({ job }) => {
  const policyUris = job.job?.policy_uris as string[] | undefined
  const assignments = job.job?.assignments as number[] | undefined
  const agentCountsByPosition = computeAgentCounts(assignments)
  const policyVersionEntries = job.policy_versions
  const episodeTags = job.job?.episode_tags as Record<string, string> | undefined
  const episodeId = job.result?.episode_id as string | undefined
  const runnerImageShort = parseRunnerImageShort(job.result?.runner_image as string | undefined)
  const runnerImageFull = job.result?.runner_image as string | undefined
  const gitCommit = job.result?.git_commit as string | undefined
  const instanceType = job.result?.instance_type as string | undefined
  const lifecycleError = job.error
  const [expanded, setExpanded] = useState(false)
  const [showSpec, setShowSpec] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const [logs, setLogs] = useState<string | null>(null)
  const [showGameStats, setShowGameStats] = useState(false)
  const [showAgentStats, setShowAgentStats] = useState(false)
  const [traceLoading, setTraceLoading] = useState(false)

  const policyStatsMap = new Map((job.episode?.policy_stats ?? []).map((s) => [s.policy_version_id, s]))
  const attrs = job.episode?.attributes
  const gameStats = attrs?.stats?.game
  const agentStats = attrs?.stats?.agent

  const timeDisplay = getTimeDisplay(job)
  const openTraceViewer = useCallback(async () => {
    setTraceLoading(true)
    const handle = window.open('https://ui.perfetto.dev')
    if (!handle) {
      setTraceLoading(false)
      return
    }

    const response = await fetch(`/api/jobs/${job.id}/trace`)
    if (!response.ok) {
      handle.close()
      setTraceLoading(false)
      return
    }
    const buffer = await response.arrayBuffer()

    await new Promise<void>((resolve) => {
      const interval = setInterval(() => handle.postMessage('PING', '*'), 100)
      const cleanup = () => {
        clearInterval(interval)
        clearTimeout(timeout)
        window.removeEventListener('message', onMessage)
        resolve()
      }
      const onMessage = (e: MessageEvent) => {
        if (e.data === 'PONG') cleanup()
      }
      const timeout = setTimeout(cleanup, 10000)
      window.addEventListener('message', onMessage)
    })

    handle.postMessage(
      {
        perfetto: {
          buffer,
          title: `Job ${job.id}`,
          fileName: `job-${job.id}-trace.pftrace`,
        },
      },
      '*'
    )
    setTraceLoading(false)
  }, [job.id])

  const downloadTrace = useCallback(() => {
    fetch(`/api/jobs/${job.id}/trace`)
      .then((response) => {
        if (!response.ok) return null
        return response.text()
      })
      .then((trace) => {
        if (!trace) return
        const blob = new Blob([trace], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `job-${job.id}-trace.json`
        a.click()
        URL.revokeObjectURL(url)
      })
  }, [job.id])

  return (
    <>
      {/* Compact row */}
      <TR>
        <TD className="!px-1 !py-2 text-center cursor-pointer select-none" onClick={() => setExpanded(!expanded)}>
          <span className="text-gray-400 text-xs">{expanded ? '\u25BC' : '\u25B6'}</span>
        </TD>
        <TD>
          <StatusBadge status={job.status} />
          {lifecycleError && job.status === 'failed' && lifecycleError !== 'Error' && (
            <div className="text-red-600 text-[10px] truncate max-w-[130px] mt-0.5" title={lifecycleError}>
              {lifecycleError}
            </div>
          )}
        </TD>
        <TD>
          {policyVersionEntries.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyVersionEntries.map((entry, i) => {
                const uri = policyUris?.[i] ?? `metta://policy/${entry.policy.id}`
                return (
                  <div key={`${entry.policy.id}-${entry.position}`}>
                    <PolicyLink uri={uri} policy={entry.policy} />
                  </div>
                )
              })}
            </div>
          ) : policyUris && policyUris.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyUris.map((uri, i) => (
                <div key={`${uri}-${i}`} className="font-mono text-xs text-wrap break-all">
                  {uri}
                </div>
              ))}
            </div>
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </TD>
        <TD>
          {policyVersionEntries.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyVersionEntries.map((entry) => {
                const stat = policyStatsMap.get(entry.policy.id)
                const specAgents = agentCountsByPosition.get(entry.position)
                const numAgents = stat?.num_agents ?? specAgents
                return (
                  <div key={`${entry.policy.id}-${entry.position}`} className="font-mono text-xs">
                    {numAgents != null ? numAgents : '-'}
                  </div>
                )
              })}
            </div>
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </TD>
        <TD>
          {policyVersionEntries.length > 0 ? (
            <div className="flex flex-col gap-1">
              {policyVersionEntries.map((entry) => {
                const stat = policyStatsMap.get(entry.policy.id)
                return (
                  <div key={`${entry.policy.id}-${entry.position}`} className="font-mono text-xs">
                    {stat ? fmt(stat.avg_reward) : '-'}
                  </div>
                )
              })}
            </div>
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </TD>
        <TD>
          <div className="flex flex-col gap-0.5">
            {job.match?.season_name && (
              <StyledLink href={`/tournament/${job.match.season_name}`} className="text-xs">
                {job.match.season_name}
              </StyledLink>
            )}
            {job.match?.pool_name && <span className="text-gray-500 text-[10px]">{job.match.pool_name}</span>}
            {episodeTags && Object.keys(episodeTags).length > 0 && <Tags tags={episodeTags} />}
          </div>
        </TD>
        <TD>
          <div className="text-xs">{timeDisplay.primary}</div>
          {timeDisplay.secondary && <div className="text-gray-400 text-[10px]">{timeDisplay.secondary}</div>}
        </TD>
        <TD>
          <div className="flex items-center gap-0 text-xs flex-wrap">
            {episodeId && <StyledLink href={`/episodes/${episodeId}`}>Episode</StyledLink>}
            {job.episode?.replay_url && normalizeVibescopeUrl(job.episode.replay_url) && (
              <>
                {episodeId && <span className="text-gray-300 mx-1">&middot;</span>}
                <a
                  href={normalizeVibescopeUrl(job.episode.replay_url)!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  VS
                </a>
              </>
            )}
            {job.episode?.replay_url && normalizeReplayUrl(job.episode.replay_url) && (
              <>
                <span className="text-gray-300 mx-1">&middot;</span>
                <a
                  href={normalizeReplayUrl(job.episode.replay_url)!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  MS
                </a>
              </>
            )}
          </div>
        </TD>
      </TR>

      {/* Expanded detail panel */}
      {expanded && (
        <TR>
          <TD colSpan={8} className="!p-0">
            <div className="bg-gray-50 border-t border-gray-200 px-4 py-3 grid grid-cols-[1fr_auto_1fr_auto_1fr] gap-0">
              {/* Job */}
              <div className="px-3">
                <div className="text-xs text-gray-500 font-semibold uppercase tracking-wide mb-1.5">Job</div>
                <LabelValueTable>
                  <LabelRow label="Job ID">
                    <CopyButton text={job.id} className="font-mono text-xs hover:text-gray-900">
                      <span>{job.id}</span>
                    </CopyButton>
                  </LabelRow>
                  {gitCommit && (
                    <LabelRow label="Runner Commit">
                      <a
                        href={`https://github.com/${METTA_GITHUB_ORGANIZATION}/${METTA_GITHUB_REPO}/commit/${gitCommit}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-xs text-blue-600 hover:underline"
                      >
                        {gitCommit.slice(0, 7)}
                      </a>
                    </LabelRow>
                  )}
                  {instanceType && (
                    <LabelRow label="Instance">
                      <span className="font-mono text-xs">{instanceType}</span>
                    </LabelRow>
                  )}
                  {!gitCommit && runnerImageShort && (
                    <LabelRow label="Runner Image">
                      <CopyButton text={runnerImageFull ?? ''} className="font-mono text-xs hover:text-gray-900">
                        <span>{runnerImageShort}</span>
                      </CopyButton>
                    </LabelRow>
                  )}
                  {job.job && (
                    <LabelRow label="Episode Spec">
                      <span className="flex gap-1.5 justify-end">
                        <button
                          onClick={() => setShowSpec(!showSpec)}
                          className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
                        >
                          {showSpec ? 'Collapse' : 'Expand'}
                        </button>
                        <button
                          onClick={() => {
                            const blob = new Blob([JSON.stringify(job.job, null, 2)], { type: 'application/json' })
                            const url = URL.createObjectURL(blob)
                            const a = document.createElement('a')
                            a.href = url
                            a.download = `job-${job.id}.json`
                            a.click()
                            URL.revokeObjectURL(url)
                          }}
                          className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  <LabelRow label="Local reproduce command">
                    <CopyButton
                      text={`./tools/run.py recipes.experiment.episode_runner.repro source=${job.id}`}
                      className="text-blue-600 hover:underline"
                      title="Copy local repro command"
                    >
                      <span>Copy</span>
                    </CopyButton>
                  </LabelRow>
                </LabelValueTable>
              </div>
              <div className="w-px bg-gray-200" />
              {/* Timing */}
              <div className="px-3">
                <div className="text-xs text-gray-500 font-semibold uppercase tracking-wide mb-1.5">Timing</div>
                <Timeline job={job} />
              </div>
              <div className="w-px bg-gray-200" />
              {/* Results */}
              <div className="px-3">
                <div className="text-xs text-gray-500 font-semibold uppercase tracking-wide mb-1.5">Results</div>
                <LabelValueTable>
                  {gameStats && (
                    <ExpandDownloadRow
                      label="Game Stats"
                      data={gameStats}
                      show={showGameStats}
                      onToggle={() => setShowGameStats(!showGameStats)}
                    />
                  )}
                  {agentStats && (
                    <ExpandDownloadRow
                      label="Agent Stats"
                      data={agentStats}
                      show={showAgentStats}
                      onToggle={() => setShowAgentStats(!showAgentStats)}
                    />
                  )}
                  {(job.status === 'completed' || job.status === 'failed') && (
                    <LabelRow label="Trace">
                      <span className="flex gap-1.5 justify-end">
                        <button
                          onClick={openTraceViewer}
                          disabled={traceLoading}
                          className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0 disabled:opacity-50 disabled:cursor-default"
                        >
                          {traceLoading ? (
                            <span className="inline-flex items-center gap-1">
                              <span className="inline-block w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                              Loading
                            </span>
                          ) : (
                            'View'
                          )}
                        </button>
                        <button
                          onClick={downloadTrace}
                          className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  {(job.status === 'completed' || job.status === 'failed') && (
                    <LabelRow label="Logs">
                      <span className="flex gap-1.5 justify-end">
                        <button
                          onClick={() => {
                            if (!showLogs && logs === null) {
                              fetch(`/api/jobs/${job.id}/logs`)
                                .then((r) => r.text())
                                .then((text) => {
                                  setLogs(text)
                                  setShowLogs(true)
                                })
                            } else {
                              setShowLogs(!showLogs)
                            }
                          }}
                          className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
                        >
                          {showLogs ? 'Collapse' : 'Expand'}
                        </button>
                        <button
                          onClick={() => {
                            const doDownload = (text: string) => {
                              const blob = new Blob([text], { type: 'text/plain' })
                              const url = URL.createObjectURL(blob)
                              const a = document.createElement('a')
                              a.href = url
                              a.download = `job-${job.id}-logs.txt`
                              a.click()
                              URL.revokeObjectURL(url)
                            }
                            if (logs !== null) {
                              doDownload(logs)
                            } else {
                              fetch(`/api/jobs/${job.id}/logs`)
                                .then((r) => r.text())
                                .then((text) => {
                                  setLogs(text)
                                  doDownload(text)
                                })
                            }
                          }}
                          className="text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
                        >
                          Download
                        </button>
                      </span>
                    </LabelRow>
                  )}
                  {lifecycleError && (
                    <LabelRow label="Error">
                      <span className="text-red-600 text-xs" title={lifecycleError}>
                        {lifecycleError}
                      </span>
                    </LabelRow>
                  )}
                </LabelValueTable>
              </div>
            </div>
          </TD>
        </TR>
      )}

      {/* Expansion rows */}
      {expanded && showLogs && logs !== null && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel label="Logs" content={logs} onClose={() => setShowLogs(false)} />
          </TD>
        </TR>
      )}
      {expanded && showSpec && job.job && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Episode Spec"
              content={JSON.stringify(truncateValue(job.job), null, 2)}
              copyContent={JSON.stringify(job.job, null, 2)}
              onClose={() => setShowSpec(false)}
            />
          </TD>
        </TR>
      )}
      {expanded && showGameStats && gameStats && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Game Stats"
              content={JSON.stringify(gameStats, null, 2)}
              onClose={() => setShowGameStats(false)}
            />
          </TD>
        </TR>
      )}
      {expanded && showAgentStats && agentStats && (
        <TR>
          <TD colSpan={8} className="!p-2">
            <ExpansionPanel
              label="Agent Stats"
              content={JSON.stringify(agentStats, null, 2)}
              onClose={() => setShowAgentStats(false)}
            />
          </TD>
        </TR>
      )}
    </>
  )
}
