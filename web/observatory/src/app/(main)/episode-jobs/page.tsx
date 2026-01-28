import { createLoader, parseAsInteger, parseAsString, parseAsStringLiteral } from 'nuqs/server'

import { PaginatedControls } from '@/components/PaginatedControls'
import { ALL_JOB_STATUSES } from '@/lib/repo'
import { getRepo } from '@/lib/repo/server'

import { JobsTable } from './JobsTable'

const nuqsParams = {
  jobId: parseAsString.withDefault(''),
  policyVersionId: parseAsString.withDefault(''),
  status: parseAsStringLiteral(ALL_JOB_STATUSES),
  page: parseAsInteger.withDefault(0),
}

const parseSearchParams = createLoader(nuqsParams)

export default async function EpisodeJobsPage({ searchParams: rawSearchParams }: PageProps<'/episode-jobs'>) {
  const searchParams = await parseSearchParams(rawSearchParams)
  const { jobId: jobIdFilter, policyVersionId: policyVersionIdFilter, status: statusFilter, page } = searchParams

  const repo = await getRepo()

  const pageSize = 50
  const jobs = await repo.getJobs({
    job_type: 'episode',
    statuses: statusFilter ? [statusFilter] : undefined,
    job_id: jobIdFilter || undefined,
    policy_version_id: policyVersionIdFilter || undefined,
    limit: pageSize,
    offset: page * pageSize,
  })

  return (
    <div className="overflow-x-auto">
      <JobsTable jobs={jobs} />
      {jobs.length === 0 && <div className="p-5 text-center text-gray-500">No jobs found</div>}
      <PaginatedControls isLastPage={jobs.length < pageSize} />
    </div>
  )
}
