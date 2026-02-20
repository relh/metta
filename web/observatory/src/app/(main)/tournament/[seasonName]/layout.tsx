import { notFound } from 'next/navigation'
import { FC, Suspense } from 'react'

import { AutoRefresh } from '@/components/AutoRefresh'
import { LinkTabs, type LinkTab } from '@/components/LinkTabs'
import { Spinner } from '@/components/Spinner'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getSeasonStageContext } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'

import { StageProgress } from './StageProgress'
import { defaultSelectedStage } from './stageSelection'

const SeasonDetails: FC<{ seasonName: string }> = async ({ seasonName }) => {
  const repo = await getRepo()
  const season = await repo.getSeason(seasonName)
  if (!season) {
    return notFound()
  }

  return (
    <div className="text-foreground-muted text-sm">
      <ServerDebugDrain />
      {season.summary && <div>{season.summary}</div>}
      <div>
        Compat version:{' '}
        {season.compat_version ? (
          <span className="font-mono text-foreground">compat-v{season.compat_version}</span>
        ) : (
          'not pinned to a specific runner compat version'
        )}
      </div>
    </div>
  )
}

export default async function SeasonPage({ params, children }: LayoutProps<'/tournament/[seasonName]'>) {
  const { seasonName } = await params

  const repo = await getRepo()
  const stageContext = await getSeasonStageContext(repo, seasonName)
  const stageKindsByPool = stageContext.progress
    ? Object.fromEntries(stageContext.progress.stage_flow.map((stage) => [stage.input_pool, stage.kind]))
    : undefined

  const tabs: LinkTab[] = [
    {
      id: 'leaderboard',
      label: 'Leaderboard',
      href:
        stageContext.teamSeason && stageContext.progress && !stageContext.progress.started
          ? `/tournament/${seasonName}?view=leaderboard`
          : `/tournament/${seasonName}`,
    },
    { id: 'players', label: 'Players', href: `/tournament/${seasonName}/players` },
    {
      id: 'matches',
      label: 'Matches',
      href: `/tournament/${seasonName}/matches`,
      ...(stageContext.progress ? { allowedStageKinds: ['team_eval', 'policy_eval'] } : {}),
    },
    ...(stageContext.hasTeams
      ? [
          {
            id: 'teams',
            label: 'Teams',
            href: `/tournament/${seasonName}/teams`,
            ...(stageContext.progress ? { allowedStageKinds: ['team_eval'] } : {}),
          },
        ]
      : []),
  ]

  return (
    <div className="space-y-6">
      <AutoRefresh interval={10000} />
      <Suspense fallback={<Spinner />}>
        <SeasonDetails seasonName={seasonName} />
      </Suspense>
      {stageContext.progress && (
        <StageProgress
          stageFlow={stageContext.progress.stage_flow}
          stages={stageContext.progress.stages}
          defaultStage={defaultSelectedStage(
            stageContext.progress.stages,
            stageContext.progress.stage_flow,
            stageContext.progress.started
          )}
          started={stageContext.progress.started}
        />
      )}
      <LinkTabs tabs={tabs} stageKindsByPool={stageKindsByPool} defaultStage={stageContext.selectedStage} />
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
