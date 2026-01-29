import { FC } from 'react'

import { Table, TableBody, TableHeader, TH } from '@/components/Table'
import { JobRequest } from '@/lib/repo'

import { JobRow } from './JobRow'

export const JobsTable: FC<{ jobs: JobRequest[] }> = ({ jobs }) => {
  return (
    <Table>
      <TableHeader>
        <TH style={{ width: 100 }}>Job</TH>
        <TH>Policies</TH>
        <TH>Tags</TH>
        <TH style={{ width: 280 }}>Timeline</TH>
        <TH>Result</TH>
        <TH style={{ width: 50 }}>Logs</TH>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} />
        ))}
      </TableBody>
    </Table>
  )
}
