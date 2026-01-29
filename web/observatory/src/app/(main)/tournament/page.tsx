import { Metadata } from 'next'
import { redirect } from 'next/navigation'

import { getRepo } from '@/lib/repo/server'

export default async function TournamentPage() {
  const repo = await getRepo()
  const seasons = await repo.getSeasons()
  if (seasons.length === 0) {
    return (
      <div className="p-6 max-w-5xl mx-auto flex justify-center py-16">
        <div className="text-gray-600">No seasons found</div>
      </div>
    )
  }

  const defaultSeason = seasons.find((s) => s.is_default) ?? seasons[0]
  redirect(`/tournament/${defaultSeason.name}`)
}

export const metadata: Metadata = {
  title: 'Tournaments | Observatory',
}
