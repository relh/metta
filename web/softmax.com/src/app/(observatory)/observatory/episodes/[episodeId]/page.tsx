import { notFound } from "next/navigation";

import { Card } from "@observatory/components/Card";
import { StandardPageLayout } from "@observatory/components/layouts/StandardPageLayout";
import { ReplayViewer } from "@observatory/components/ReplayViewer";
import { SmallHeader } from "@observatory/components/SmallHeader";
import { TagList } from "@observatory/components/TagList";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import { episodeJobsRoute } from "@observatory/lib/routes";
import { formatDate, formatRelativeTime } from "@observatory/utils/datetime";

import { JobsTable } from "../../episode-jobs/JobsTable";
import { GameStats, PoliciesAndAgents } from "./PoliciesAndAgents";

export default async function EpisodeDetailPage(
  props: PageProps<"/observatory/episodes/[episodeId]">,
) {
  const repo = await getRepo();
  const { episodeId } = await props.params;
  const response = await repo.queryEpisodes({
    episode_ids: [episodeId],
    limit: 1,
    offset: 0,
  });
  const episode = response.episodes[0];
  if (!episode) {
    notFound();
  }

  const jobs = episode.job_id
    ? await repo.getJobs({ job_id: episode.job_id, limit: 1 })
    : [];

  return (
    <StandardPageLayout>
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-foreground-muted text-xs font-semibold tracking-wide uppercase">
            Episode
          </p>
          <h1 className="text-foreground text-2xl font-semibold break-all">
            {episodeId}
          </h1>
          <div className="text-foreground-muted flex flex-wrap gap-3 text-sm">
            <span title={formatDate(episode.created_at)}>
              Created: {formatRelativeTime(episode.created_at)}
            </span>
            {episode.job_id && (
              <a
                href={episodeJobsRoute({ jobId: episode.job_id })}
                className="text-blue-600 hover:underline"
              >
                Job: {episode.job_id.slice(0, 8)}
              </a>
            )}
            <span className="text-foreground-muted flex items-center gap-1">
              Episode ID:
              <span className="text-foreground-subtle font-mono text-xs">
                {episodeId}
              </span>
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

      <div className="bg-surface border-border rounded-lg border shadow-sm">
        <div className="space-y-6 p-5">
          <div>
            <SmallHeader>Tags</SmallHeader>
            {Object.keys(episode.tags).length === 0 ? (
              <div className="text-foreground-muted text-sm">
                No tags found.
              </div>
            ) : (
              <TagList tags={episode.tags} />
            )}
          </div>

          <div>
            <SmallHeader>Attributes</SmallHeader>
            {Object.keys(episode.attributes || {}).length === 0 ? (
              <div className="text-foreground-muted text-sm">
                No attributes recorded.
              </div>
            ) : (
              <pre className="bg-surface-alt border-border text-foreground overflow-auto rounded border p-3 text-xs">
                {JSON.stringify(episode.attributes, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    </StandardPageLayout>
  );
}
