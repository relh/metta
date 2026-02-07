import { notFound } from 'next/navigation'
import { FC, Suspense } from 'react'

import { AutoRefresh } from '@/components/AutoRefresh'
import { LinkTabs } from '@/components/LinkTabs'
import { Spinner } from '@/components/Spinner'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'

const SeasonDetails: FC<{ seasonName: string }> = async ({ seasonName }) => {
  const repo = await getRepo()
  const season = await repo.getSeason(seasonName)
  if (!season) {
    return notFound()
  }

  return (
    <div className="text-gray-500 text-sm">
      <ServerDebugDrain />
      {season.summary && <div>{season.summary}</div>}
      {season.pools.length > 0 && (
        <div className="mt-1 ml-4 space-y-0.5">
          {season.pools.map((pool) => (
            <div key={pool.name}>
              <span className="font-medium text-gray-600">{pool.name}:</span> {pool.description}
              {pool.config_id && (
                <>
                  {' '}
                  <a
                    href={`${repo.baseUrl}/tournament/configs/${pool.config_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-500 hover:text-blue-700"
                  >
                    [config]
                  </a>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default async function SeasonPage({ params, children }: LayoutProps<'/tournament/[seasonName]'>) {
  const { seasonName } = await params

  return (
    <div className="space-y-6">
      <AutoRefresh interval={10000} />
      <Suspense fallback={<Spinner />}>
        <SeasonDetails seasonName={seasonName} />
      </Suspense>
      <LinkTabs
        tabs={[
          {
            id: 'leaderboard',
            label: 'Leaderboard',
            href: `/tournament/${seasonName}`,
          },
          {
            id: 'players',
            label: 'Players',
            href: `/tournament/${seasonName}/players`,
          },
          {
            id: 'matches',
            label: 'Matches',
            href: `/tournament/${seasonName}/matches`,
          },
        ]}
      />
      {children}
    </div>
  )
}

export async function generateMetadata({ params }: PageProps<'/tournament/[seasonName]'>) {
  const { seasonName } = await params
  return {
    title: `Season ${seasonName} | Observatory`,
  }
}
