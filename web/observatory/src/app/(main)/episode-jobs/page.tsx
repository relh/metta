import { createLoader, parseAsInteger, parseAsString, parseAsStringLiteral } from 'nuqs/server'

import { AutoRefresh } from '@/components/AutoRefresh'
import { Card } from '@/components/Card'
import { PaginatedControls } from '@/components/PaginatedControls'
import { RefreshButton } from '@/components/RefreshButton'
import { SearchParamInput } from '@/components/SearchParamInput'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { ALL_JOB_STATUSES } from '@/lib/repo'
import { getRepo } from '@/lib/repo/server'

import { JobFilters } from './JobFilters'
import { JobsTable } from './JobsTable'

const nuqsParams = {
  jobId: parseAsString.withDefault(''),
  policyVersionId: parseAsString.withDefault(''),
  status: parseAsStringLiteral(ALL_JOB_STATUSES),
  seasonId: parseAsString.withDefault(''),
  poolId: parseAsString.withDefault(''),
  page: parseAsInteger.withDefault(0),
}

const parseSearchParams = createLoader(nuqsParams)

export default async function EpisodeJobsPage({ searchParams: rawSearchParams }: PageProps<'/episode-jobs'>) {
  const searchParams = await parseSearchParams(rawSearchParams)
  const {
    jobId: jobIdFilter,
    policyVersionId: policyVersionIdFilter,
    status: statusFilter,
    seasonId: seasonIdFilter,
    poolId: poolIdFilter,
    page,
  } = searchParams

  const repo = await getRepo()
  const pageSize = 50

  const [jobs, seasons] = await Promise.all([
    repo.getJobs({
      job_type: 'episode',
      statuses: statusFilter ? [statusFilter] : undefined,
      job_id: jobIdFilter || undefined,
      policy_version_id: policyVersionIdFilter || undefined,
      season_id: seasonIdFilter || undefined,
      pool_id: poolIdFilter || undefined,
      limit: pageSize,
      offset: page * pageSize,
    }),
    repo.getSeasons(),
  ])

  return (
    <div className="p-5 max-w-[1600px] mx-auto">
      <ServerDebugDrain />
      <AutoRefresh />
      <Card title="Episode Jobs">
        <div className="mb-4 flex flex-wrap gap-3 items-end">
          <JobFilters seasons={seasons} />
          <div>
            <div className="text-xs text-foreground-muted mb-1">Job ID</div>
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
          {jobs.length === 0 && <div className="p-5 text-center text-foreground-muted">No jobs found</div>}
          <PaginatedControls isLastPage={jobs.length < pageSize} />
        </div>
      </Card>
    </div>
  )
}
