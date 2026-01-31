import { notFound } from 'next/navigation'

import { Card } from '@/components/Card'
import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'
import { ReplayViewer } from '@/components/ReplayViewer'
import { SmallHeader } from '@/components/SmallHeader'
import { TagList } from '@/components/TagList'
import { getRepo } from '@/lib/repo/server'
import { formatDate, formatRelativeTime } from '@/utils/datetime'

import { AgentStats, GameStats } from './AgentStats'
import { PoliciesAndScores } from './PoliciesAndScores'

export default async function EpisodeDetailPage(props: PageProps<'/episodes/[episodeId]'>) {
  const repo = await getRepo()
  const { episodeId } = await props.params
  const response = await repo.queryEpisodes({ episode_ids: [episodeId], limit: 1, offset: 0 })
  const episode = response.episodes[0]
  if (!episode) {
    notFound()
  }

  return (
    <StandardPageLayout>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-gray-500 tracking-wide">Episode</p>
          <h1 className="text-2xl font-semibold text-gray-900 break-all">{episodeId}</h1>
          <div className="flex flex-wrap gap-3 text-sm text-gray-600">
            <span title={formatDate(episode.created_at)}>Created: {formatRelativeTime(episode.created_at)}</span>
            {episode.eval_task_id && <span>Eval Task: {episode.eval_task_id}</span>}
            <span className="flex items-center gap-1 text-gray-500">
              Episode ID:
              <span className="font-mono text-xs text-gray-700">{episodeId}</span>
            </span>
          </div>
        </div>
      </div>

      <PoliciesAndScores episode={episode} />

      <GameStats attributes={episode.attributes} />
      <AgentStats attributes={episode.attributes} jobId={episode.tags?.job_id} />

      <Card title="Replay">
        <ReplayViewer replayUrl={episode.replay_url} label="Episode replay" />
      </Card>

      <div className="bg-white border border-gray-200 rounded-lg shadow-sm">
        <div className="p-5 space-y-6">
          <div>
            <SmallHeader>Tags</SmallHeader>
            {Object.keys(episode.tags).length === 0 ? (
              <div className="text-gray-500 text-sm">No tags found.</div>
            ) : (
              <TagList tags={episode.tags} />
            )}
          </div>

          <div>
            <SmallHeader>Attributes</SmallHeader>
            {Object.keys(episode.attributes || {}).length === 0 ? (
              <div className="text-gray-500 text-sm">No attributes recorded.</div>
            ) : (
              <pre className="bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-auto">
                {JSON.stringify(episode.attributes, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    </StandardPageLayout>
  )
}
