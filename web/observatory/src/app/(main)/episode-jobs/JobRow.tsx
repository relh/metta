'use client'
import { FC } from 'react'

import { StyledLink } from '@/components/StyledLink'
import { TD, TR } from '@/components/Table'
import { JobRequest } from '@/lib/repo'

import { PolicyLink } from './PolicyLink'
import { StatusBadge } from './StatusBadge'
import { Timeline } from './Timeline'

export const JobRow: FC<{ job: JobRequest }> = ({ job }) => {
  const policyUris = job.job?.policy_uris as string[] | undefined
  const policyVersionEntries = job.policy_versions
  const policyByPosition = new Map(policyVersionEntries.map((entry) => [entry.position, entry.policy]))
  const episodeTags = job.job?.episode_tags as Record<string, string> | undefined
  const episodeId = job.result?.episode_id as string | undefined
  const lifecycleError = job.error

  return (
    <TR>
      <TD className="font-mono text-xs">{job.id.slice(0, 8)}</TD>
      <TD>
        <StatusBadge status={job.status} />
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
          <div className="flex flex-wrap gap-1">
            {Object.entries(episodeTags).map(([k, v]) => (
              <span key={k} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded" title={`${k}: ${v}`}>
                {k}={v}
              </span>
            ))}
          </div>
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
