import { Metadata } from 'next'
import { createLoader, parseAsInteger, parseAsString } from 'nuqs/server'
import { Suspense } from 'react'

import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'
import { SearchParamInput } from '@/components/SearchParamInput'
import { Spinner } from '@/components/Spinner'

import { PoliciesTable } from './PoliciesTable'

const nuqsParams = {
  q: parseAsString.withDefault(''),
  page: parseAsInteger.withDefault(0),
}

const parseSearchParams = createLoader(nuqsParams)

export default async function PoliciesPage({ searchParams: rawSearchParams }: PageProps<'/policies'>) {
  const { q: nameFilter, page } = await parseSearchParams(rawSearchParams)

  return (
    <StandardPageLayout>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold text-foreground">Policies</h1>
          <p className="text-sm text-foreground-muted">All policies ordered by creation date</p>
        </div>
      </div>

      <div className="bg-surface border border-border rounded-lg shadow-sm">
        <div className="p-5">
          <div className="w-full max-w-xs mb-6">
            <SearchParamInput paramName="q" placeholder="Search by name..." />
          </div>
          <Suspense
            fallback={
              <div className="grid place-items-center min-h-80">
                <Spinner size="lg" />
              </div>
            }
          >
            <PoliciesTable nameFilter={nameFilter} page={page} />
          </Suspense>
        </div>
      </div>
    </StandardPageLayout>
  )
}

export const metadata: Metadata = {
  title: 'Policies | Observatory',
}
