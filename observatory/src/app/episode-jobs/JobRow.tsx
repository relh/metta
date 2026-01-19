'use client'
import clsx from 'clsx'
import { FC, Fragment, useState } from 'react'

import { StyledLink } from '@/components/StyledLink'
import { TD, TR } from '@/components/Table'
import { JobRequest } from '@/lib/repo'

import { PolicyLink } from './PolicyLink'
import { StatusBadge } from './StatusBadge'
import { Timeline } from './Timeline'

export const JobRow: FC<{ job: JobRequest }> = ({ job }) => {
  const [expanded, setExpanded] = useState(false)
  const policyUris = job.job?.policy_uris as string[] | undefined
  const episodeTags = job.job?.episode_tags as Record<string, string> | undefined
  const episodeId = job.result?.episode_id as string | undefined
  const resultError = job.result?.error as string | undefined
  const lifecycleError = job.error

  const hasError = resultError || lifecycleError
  const hasExpandableContent = !episodeId && (hasError || job.result)

  return (
    <Fragment>
      <TR
        className={clsx(hasExpandableContent && 'hover:bg-gray-50 cursor-pointer')}
        onClick={() => hasExpandableContent && setExpanded(!expanded)}
      >
        <TD className="font-mono text-xs">{job.id.slice(0, 8)}</TD>
        <TD>
          <div className="flex flex-col gap-1">
            <StatusBadge status={job.status} />
          </div>
        </TD>
        <TD>
          {policyUris?.map((uri, i) => (
            <div key={i}>
              <PolicyLink uri={uri} />
            </div>
          ))}
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
          ) : resultError ? (
            <span className="text-red-600 text-xs">{expanded ? '[-] Error' : '[+] Error'}</span>
          ) : job.result ? (
            <span className="text-gray-600 text-xs">{expanded ? '[-] Result' : '[+] Result'}</span>
          ) : (
            '-'
          )}
        </TD>
      </TR>
      {expanded && hasExpandableContent && (
        <tr className="bg-gray-50">
          <td colSpan={6} className="px-3 py-2 space-y-2">
            {lifecycleError && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">Job lifecycle error:</div>
                <pre className="text-xs text-red-600">{lifecycleError}</pre>
              </div>
            )}
            {resultError && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">Episode-runner error:</div>
                <pre className="text-xs whitespace-pre-wrap text-red-600">{resultError}</pre>
              </div>
            )}
            {job.result && !resultError && (
              <div>
                <div className="text-xs font-medium text-gray-500 mb-1">Result:</div>
                <pre className="text-xs whitespace-pre-wrap text-gray-600">{JSON.stringify(job.result, null, 2)}</pre>
              </div>
            )}
          </td>
        </tr>
      )}
    </Fragment>
  )
}
