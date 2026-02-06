import { createLoader, parseAsInteger, parseAsString, parseAsStringLiteral } from 'nuqs/server'
import { FC } from 'react'

import { Card } from '@/components/Card'
import { PaginatedControls } from '@/components/PaginatedControls'
import { RefreshButton } from '@/components/RefreshButton'
import { SearchParamInput } from '@/components/SearchParamInput'
import { ALL_JOB_STATUSES } from '@/lib/repo'
import { getRepo } from '@/lib/repo/server'

import { JobFilters } from '../../../episode-jobs/JobFilters'
import { JobsTable } from '../../../episode-jobs/JobsTable'

const nuqsParams = {
  policyVersionId: parseAsString.withDefault(''),
  status: parseAsStringLiteral(ALL_JOB_STATUSES),
  seasonId: parseAsString.withDefault(''),
  poolId: parseAsString.withDefault(''),
  jobId: parseAsString.withDefault(''),
  page: parseAsInteger.withDefault(0),
}

const parseSearchParams = createLoader(nuqsParams)

export const PolicyVersionJobsCard: FC<{
  policyVersionId: string
  searchParams: Promise<Record<string, string | string[] | undefined>>
}> = async ({ policyVersionId, searchParams }) => {
  const params = await parseSearchParams(searchParams)
  const pageSize = 50

  const repo = await getRepo()
  const [jobs, seasons] = await Promise.all([
    repo.getJobs({
      job_type: 'episode',
      policy_version_id: params.policyVersionId || policyVersionId,
      statuses: params.status ? [params.status] : undefined,
      season_id: params.seasonId || undefined,
      pool_id: params.poolId || undefined,
      job_id: params.jobId || undefined,
      limit: pageSize,
      offset: (params.page ?? 0) * pageSize,
    }),
    repo.getSeasons(),
  ])

  return (
    <Card title="Jobs">
      <div className="mb-4 flex flex-wrap gap-3 items-end">
        <JobFilters seasons={seasons} defaultPolicyVersionId={policyVersionId} />
        <div>
          <div className="text-xs text-gray-500 mb-1">Job ID</div>
          <div className="w-64">
            <SearchParamInput paramName="jobId" placeholder="Filter by Job ID..." />
          </div>
        </div>
        <div className="self-end pb-0.5">
          <RefreshButton />
        </div>
      </div>
      <div className="overflow-x-auto">
        <JobsTable jobs={jobs} />
        {jobs.length === 0 && <div className="p-5 text-center text-gray-500">No jobs found</div>}
        <PaginatedControls isLastPage={jobs.length < pageSize} />
      </div>
    </Card>
  )
}
