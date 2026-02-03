import { FC } from 'react'

import { Card } from '@/components/Card'
import { getRepo } from '@/lib/repo/server'

import { JobsTable } from '../../../episode-jobs/JobsTable'

export const PolicyVersionJobsCard: FC<{ policyVersionId: string }> = async ({ policyVersionId }) => {
  const repo = await getRepo()
  const jobs = await repo.getJobs({
    job_type: 'episode',
    policy_version_id: policyVersionId,
    limit: 50,
    offset: 0,
  })

  return (
    <Card title="Jobs">
      {jobs.length === 0 ? (
        <div className="text-gray-500 text-sm">No episode jobs found for this policy version.</div>
      ) : (
        <div className="overflow-x-auto">
          <JobsTable jobs={jobs} />
        </div>
      )}
    </Card>
  )
}
