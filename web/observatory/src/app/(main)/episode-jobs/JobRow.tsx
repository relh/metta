'use client'
import { FC, useRef, useState } from 'react'

import { StyledLink } from '@/components/StyledLink'
import { TD, TR } from '@/components/Table'
import { JobRequest } from '@/lib/repo'

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

export const JobRow: FC<{ job: JobRequest }> = ({ job }) => {
  const policyUris = job.job?.policy_uris as string[] | undefined
  const policyVersionEntries = job.policy_versions
  const policyByPosition = new Map(policyVersionEntries.map((entry) => [entry.position, entry.policy]))
  const episodeTags = job.job?.episode_tags as Record<string, string> | undefined
  const episodeId = job.result?.episode_id as string | undefined
  const lifecycleError = job.error

  return (
    <TR>
      <TD>
        <StatusBadge status={job.status} />
        {job.job ? (
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
            className="font-mono text-xs text-blue-600 hover:underline bg-transparent border-none cursor-pointer p-0"
            title="Download job spec"
          >
            {job.id.slice(0, 8)}
          </button>
        ) : (
          <div className="font-mono text-xs">{job.id.slice(0, 8)}</div>
        )}
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
      <TD>
        {(job.status === 'completed' || job.status === 'failed') && (
          <a
            href={`/api/jobs/${job.id}/logs`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline text-xs"
          >
            Logs
          </a>
        )}
      </TD>
    </TR>
  )
}
