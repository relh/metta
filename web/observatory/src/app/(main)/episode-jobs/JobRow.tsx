'use client'
import { FC, useCallback, useRef, useState } from 'react'

import { StyledLink } from '@/components/StyledLink'
import { TD, TR } from '@/components/Table'
import { JobRequest } from '@/lib/repo'

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

export const JobRow: FC<{ job: JobRequest }> = ({ job }) => {
  const policyUris = job.job?.policy_uris as string[] | undefined
  const policyVersionEntries = job.policy_versions
  const policyByPosition = new Map(policyVersionEntries.map((entry) => [entry.position, entry.policy]))
  const episodeTags = job.job?.episode_tags as Record<string, string> | undefined
  const episodeId = job.result?.episode_id as string | undefined
  const runnerImageShort = parseRunnerImageShort(job.result?.runner_image as string | undefined)
  const runnerImageFull = job.result?.runner_image as string | undefined
  const lifecycleError = job.error
  const [showSpec, setShowSpec] = useState(false)

  return (
    <>
      <TR>
        <TD>
          <LabelValueTable>
            <LabelRow label="Status">
              <StatusBadge status={job.status} />
            </LabelRow>
            {runnerImageShort && (
              <LabelRow label="Runner Image">
                <CopyButton text={runnerImageFull ?? ''} className="font-mono hover:text-gray-900">
                  <span>{runnerImageShort}</span>
                </CopyButton>
              </LabelRow>
            )}
            <LabelRow label="Job ID">
              <CopyButton text={job.id} className="font-mono hover:text-gray-900">
                <span>{job.id.slice(0, 8)}</span>
              </CopyButton>
            </LabelRow>
            {job.job && (
              <LabelRow label="Spec">
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
            {(job.status === 'completed' || job.status === 'failed') && (
              <LabelRow label="Logs">
                <a
                  href={`/api/jobs/${job.id}/logs`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline text-xs"
                >
                  View
                </a>
              </LabelRow>
            )}
            <LabelRow label="Repro">
              <CopyButton
                text={`./tools/run.py recipes.experiment.episode_runner.repro id=${job.id}`}
                className="text-blue-600 hover:underline"
                title="Copy local repro command"
              >
                <span>Copy</span>
              </CopyButton>
            </LabelRow>
          </LabelValueTable>
        </TD>
        <TD>
          {policyUris && policyUris.length > 0 ? (
            policyUris.map((uri, i) => (
              <div key={`${uri}-${i}`}>
                <PolicyLink uri={uri} policy={policyByPosition.get(i)} />
              </div>
            ))
          ) : policyVersionEntries.length > 0 ? (
            policyVersionEntries.map((entry) => (
              <div key={`${entry.policy.id}-${entry.position}`}>
                <PolicyLink uri={`metta://policy/${entry.policy.id}`} policy={entry.policy} />
              </div>
            ))
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </TD>
        <TD>
          {episodeTags && Object.keys(episodeTags).length > 0 ? (
            <Tags tags={episodeTags} />
          ) : (
            <span className="text-gray-400">-</span>
          )}
        </TD>
        <TD>
          <Timeline job={job} />
        </TD>
        <TD>
          {episodeId ? (
            <StyledLink href={`/episodes/${episodeId}`}>View</StyledLink>
          ) : lifecycleError ? (
            <span className="text-red-600 text-xs truncate max-w-[150px] block" title={lifecycleError}>
              {lifecycleError}
            </span>
          ) : (
            '-'
          )}
        </TD>
      </TR>
      {showSpec && job.job && (
        <TR>
          <TD colSpan={5}>
            <pre className="bg-gray-50 border border-gray-200 rounded p-2 text-[11px] overflow-auto max-h-[300px] m-0">
              {JSON.stringify(truncateValue(job.job), null, 2)}
            </pre>
          </TD>
        </TR>
      )}
    </>
  )
}
