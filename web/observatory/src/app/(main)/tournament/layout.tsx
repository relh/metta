import { FC, PropsWithChildren, Suspense } from 'react'

import { getRepo } from '@/lib/repo/server'

import { SeasonSelect } from './SeasonSelect'

const InnerSeasonSelect: FC = async () => {
  const repo = await getRepo()
  const seasons = await repo.getSeasons()

  return <SeasonSelect seasons={seasons} />
}

export default function TournamentLayout({ children }: PropsWithChildren) {
  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div className="space-y-6">
        <Suspense fallback={<SeasonSelect seasons={[]} />}>
          <InnerSeasonSelect />
          {children}
        </Suspense>
      </div>
    </div>
  )
}
