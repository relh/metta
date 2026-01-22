import { PropsWithChildren } from 'react'

import { AutoRefresh } from '@/components/AutoRefresh'
import { Card } from '@/components/Card'
import { RefreshButton } from '@/components/RefreshButton'
import { ResetErrorProvider } from '@/components/ResetErrorContext'
import { SearchParamInput } from '@/components/SearchParamInput'

import { StatusDropdown } from './StatusDropdown'

export default function EpisodeJobsLayout({ children }: PropsWithChildren) {
  return (
    <div className="p-5 max-w-[1600px] mx-auto">
      <AutoRefresh />
      <Card title="Episode Jobs">
        <ResetErrorProvider>
          <div className="mb-4 flex gap-4 items-center">
            <div className="w-80">
              <SearchParamInput paramName="jobId" placeholder="Filter by Job ID..." />
            </div>
            <StatusDropdown />
            <RefreshButton />
          </div>
          {children}
        </ResetErrorProvider>
      </Card>
    </div>
  )
}
