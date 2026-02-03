import { FC } from 'react'

import { Table, TableBody, TableHeader, TH } from '@/components/Table'
import { JobRequest } from '@/lib/repo'

import { JobRow } from './JobRow'

export const JobsTable: FC<{ jobs: JobRequest[] }> = ({ jobs }) => {
  return (
    <Table>
      <TableHeader>
        <TH style={{ width: 30 }} />
        <TH style={{ width: 140 }}>Job</TH>
        <TH style={{ width: 200 }}>Policies</TH>
        <TH style={{ width: 70 }}>Agents</TH>
        <TH style={{ width: 90 }}>Reward</TH>
        <TH style={{ width: 180 }}>Info</TH>
        <TH style={{ width: 130 }}>Time</TH>
        <TH style={{ width: 140 }}>View</TH>
      </TableHeader>
      <TableBody>
        {jobs.map((job) => (
          <JobRow key={job.id} job={job} />
        ))}
      </TableBody>
    </Table>
  )
}
