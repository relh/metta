import { notFound } from 'next/navigation'

import { Card } from '@/components/Card'
import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'
import { ReplayViewer } from '@/components/ReplayViewer'
import { SmallHeader } from '@/components/SmallHeader'
import { TagList } from '@/components/TagList'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatDate, formatRelativeTime } from '@/utils/datetime'

import { JobsTable } from '../../episode-jobs/JobsTable'
import { GameStats, PoliciesAndAgents } from './PoliciesAndAgents'

export default async function EpisodeDetailPage(props: PageProps<'/episodes/[episodeId]'>) {
  const repo = await getRepo()
  const { episodeId } = await props.params
  const response = await repo.queryEpisodes({ episode_ids: [episodeId], limit: 1, offset: 0 })
  const episode = response.episodes[0]
  if (!episode) {
    notFound()
  }

  const jobs = episode.job_id ? await repo.getJobs({ job_id: episode.job_id, limit: 1 }) : []

  return (
    <StandardPageLayout>
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-foreground-muted tracking-wide">Episode</p>
          <h1 className="text-2xl font-semibold text-foreground break-all">{episodeId}</h1>
          <div className="flex flex-wrap gap-3 text-sm text-foreground-muted">
            <span title={formatDate(episode.created_at)}>Created: {formatRelativeTime(episode.created_at)}</span>
            {episode.eval_task_id && <span>Eval Task: {episode.eval_task_id}</span>}
            {episode.job_id && (
              <a href={`/episode-jobs?jobId=${episode.job_id}`} className="text-blue-600 hover:underline">
                Job: {episode.job_id.slice(0, 8)}
              </a>
            )}
            <span className="flex items-center gap-1 text-foreground-muted">
              Episode ID:
              <span className="font-mono text-xs text-foreground-subtle">{episodeId}</span>
            </span>
          </div>
        </div>
      </div>

      <GameStats attributes={episode.attributes} />
      <PoliciesAndAgents jobId={episode.tags?.job_id} />

      {jobs.length > 0 && (
        <Card title="Job">
          <JobsTable jobs={jobs} />
        </Card>
      )}

      <Card title="Replay">
        <ReplayViewer replayUrl={episode.replay_url} label="Episode replay" />
      </Card>

      <div className="bg-surface border border-border rounded-lg shadow-sm">
        <div className="p-5 space-y-6">
          <div>
            <SmallHeader>Tags</SmallHeader>
            {Object.keys(episode.tags).length === 0 ? (
              <div className="text-foreground-muted text-sm">No tags found.</div>
            ) : (
              <TagList tags={episode.tags} />
            )}
          </div>

          <div>
            <SmallHeader>Attributes</SmallHeader>
            {Object.keys(episode.attributes || {}).length === 0 ? (
              <div className="text-foreground-muted text-sm">No attributes recorded.</div>
            ) : (
              <pre className="bg-surface-alt border border-border rounded p-3 text-xs overflow-auto text-foreground">
                {JSON.stringify(episode.attributes, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    </StandardPageLayout>
  )
}
