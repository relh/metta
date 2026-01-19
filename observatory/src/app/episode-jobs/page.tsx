import { createLoader, parseAsInteger, parseAsString, parseAsStringLiteral } from 'nuqs/server'

import { PaginatedControls } from '@/components/PaginatedControls'
import { Table, TableBody, TableHeader, TH } from '@/components/Table'
import { ALL_JOB_STATUSES } from '@/lib/repo'
import { getRepo } from '@/lib/repo/server'

import { JobRow } from './JobRow'

const nuqsParams = {
  jobId: parseAsString.withDefault(''),
  status: parseAsStringLiteral(ALL_JOB_STATUSES),
  page: parseAsInteger.withDefault(0),
}

const parseSearchParams = createLoader(nuqsParams)

export default async function EpisodeJobsPage({ searchParams: rawSearchParams }: PageProps<'/episode-jobs'>) {
  const searchParams = await parseSearchParams(rawSearchParams)
  const { jobId: jobIdFilter, status: statusFilter, page } = searchParams

  const repo = await getRepo()

  const pageSize = 50
  const jobs = await repo.getJobs({
    job_type: 'episode',
    statuses: statusFilter ? [statusFilter] : undefined,
    job_id: jobIdFilter || undefined,
    limit: pageSize,
    offset: page * pageSize,
  })

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TH style={{ width: 100 }}>Job ID</TH>
          <TH style={{ width: 100 }}>Status</TH>
          <TH>Policy URIs</TH>
          <TH style={{ width: 200 }}>Tags</TH>
          <TH style={{ width: 280 }}>Timeline</TH>
          <TH style={{ width: 100 }}>Result</TH>
        </TableHeader>
        <TableBody>
          {jobs.map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
        </TableBody>
      </Table>
      {jobs.length === 0 && <div className="p-5 text-center text-gray-500">No jobs found</div>}
      <PaginatedControls isLastPage={jobs.length < pageSize} />
    </div>
  )
}
