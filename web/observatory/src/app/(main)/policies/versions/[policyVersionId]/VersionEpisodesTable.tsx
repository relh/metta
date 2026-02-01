'use client'
import { FC, useState } from 'react'

import { A } from '@/components/A'
import { Button } from '@/components/Button'
import { normalizeReplayUrl, normalizeVibescopeUrl, ReplayViewer } from '@/components/ReplayViewer'
import { StyledLink } from '@/components/StyledLink'
import { Table, TableHeader, TD, TH, TR } from '@/components/Table'
import { EpisodeWithTags } from '@/lib/repo'
import { formatDate, formatRelativeTime } from '@/utils/datetime'

function formatScore(value: number | null | undefined): string {
  if (typeof value !== 'number') {
    return '—'
  }
  return value.toFixed(2)
}

function getPolicyAvgReward(policyVersionId: string, episode: EpisodeWithTags): number | undefined {
  if (policyVersionId && episode.avg_rewards[policyVersionId] !== undefined) {
    return episode.avg_rewards[policyVersionId]
  }
  if (episode.primary_pv_id && episode.avg_rewards[episode.primary_pv_id] !== undefined) {
    return episode.avg_rewards[episode.primary_pv_id]
  }
  return undefined
}

export const VersionEpisodesTable: FC<{ policyVersionId: string; episodes: EpisodeWithTags[] }> = ({
  policyVersionId,
  episodes,
}) => {
  const [episodeReplayPreview, setEpisodeReplayPreview] = useState<{
    replayUrl: string
    label: string
  } | null>(null)

  const toggleEpisodeReplayPreview = (episode: EpisodeWithTags) => {
    if (!episode.replay_url) return
    setEpisodeReplayPreview((prev) => {
      if (prev?.replayUrl === episode.replay_url) {
        return null
      }
      return { replayUrl: episode.replay_url!, label: `Episode ${episode.id.slice(0, 8)}` }
    })
  }

  return (
    <>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TH>ID</TH>
            <TH>Replay</TH>
            <TH>Created</TH>
            <TH>Avg Reward (policy)</TH>
          </TableHeader>
          <Table.Body>
            {episodes.map((episode) => (
              <TR key={episode.id}>
                <TD>
                  <StyledLink href={`/episodes/${episode.id}`} className="font-mono text-xs">
                    {episode.id}
                  </StyledLink>
                </TD>
                <TD>
                  {(() => {
                    const msUrl = normalizeReplayUrl(episode.replay_url)
                    const vsUrl = normalizeVibescopeUrl(episode.replay_url)
                    if (!msUrl) {
                      return '—'
                    }
                    return (
                      <div className="flex items-center gap-2">
                        <A href={msUrl} target="_blank" rel="noopener noreferrer">
                          MS
                        </A>
                        {vsUrl ? (
                          <A href={vsUrl} target="_blank" rel="noopener noreferrer">
                            VS
                          </A>
                        ) : null}
                        <Button size="sm" onClick={() => toggleEpisodeReplayPreview(episode)}>
                          Show
                        </Button>
                      </div>
                    )
                  })()}
                </TD>
                <TD title={formatDate(episode.created_at)}>{formatRelativeTime(episode.created_at)}</TD>
                <TD className="px-3 py-2">
                  <span className="font-mono">{formatScore(getPolicyAvgReward(policyVersionId, episode))}</span>
                </TD>
              </TR>
            ))}
          </Table.Body>
        </Table>
      </div>
      {episodeReplayPreview ? (
        <div className="mt-4">
          <ReplayViewer
            replayUrl={episodeReplayPreview.replayUrl}
            label={`Replay preview (${episodeReplayPreview.label})`}
          />
        </div>
      ) : null}
    </>
  )
}
