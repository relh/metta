import { FC } from 'react'

import { Card } from '@/components/Card'
import { getRepo } from '@/lib/repo/server'

import { VersionEpisodesTable } from './VersionEpisodesTable'

export const VersionEpisodesCard: FC<{ policyVersionId: string }> = async ({ policyVersionId }) => {
  const repo = await getRepo()
  const { episodes } = await repo.queryEpisodes({
    primary_policy_version_ids: [policyVersionId],
    limit: 200,
    offset: 0,
  })

  return (
    <Card title="Episodes">
      {episodes.length === 0 ? (
        <div className="text-gray-500 text-sm">No episodes found for this policy version.</div>
      ) : (
        <VersionEpisodesTable policyVersionId={policyVersionId} episodes={episodes} />
      )}
    </Card>
  )
}
