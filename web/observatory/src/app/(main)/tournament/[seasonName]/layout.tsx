import { notFound } from 'next/navigation'
import { FC, Suspense } from 'react'

import { AutoRefresh } from '@/components/AutoRefresh'
import { LinkTabs, type LinkTab } from '@/components/LinkTabs'
import { Spinner } from '@/components/Spinner'
import { TournamentDescriptionMeta } from '@/components/tournament/TournamentDescriptionMeta'
import type { SeasonDetail } from '@/lib/api'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getSeasonStageContext } from '@/lib/tournament/api'
import { getRepo } from '@/lib/repo/server'

import { StageProgress } from './StageProgress'
import { defaultSelectedStage } from './stageSelection'

const SEASON_STATUS_LABELS: Record<SeasonDetail['status'], string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  complete: 'Complete',
}

const SEASON_STATUS_BADGE_CLASSES: Record<SeasonDetail['status'], string> = {
  not_started: 'border-border text-foreground-muted bg-transparent',
  in_progress: 'border-green-500/40 text-green-700 dark:text-green-300 bg-transparent',
  complete: 'border-blue-500/40 text-blue-700 dark:text-blue-300 bg-transparent',
}

const formatStartedAt = (iso: string) =>
  new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

const SeasonDetails: FC<{ seasonName: string }> = async ({ seasonName }) => {
  const repo = await getRepo()
  const season = await repo.getSeason(seasonName)
  if (!season) {
    return notFound()
  }

  return (
    <div className="space-y-2">
      <ServerDebugDrain />
      <div>
        <div className="flex flex-wrap items-baseline gap-2">
          <h1 className="m-0 text-3xl font-bold text-foreground">{season.display_name}</h1>
          <span
            className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${SEASON_STATUS_BADGE_CLASSES[season.status]}`}
          >
            {SEASON_STATUS_LABELS[season.status]}
          </span>
        </div>
        {season.summary && <div className="mt-0.5 text-sm text-foreground-muted">{season.summary}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-foreground-muted">
        <span>
          Entrants: {season.entrant_count}
          {season.active_entrant_count !== season.entrant_count ? ` (${season.active_entrant_count} active)` : ''}
        </span>
        <span>Stages: {season.stage_count}</span>
        {season.started_at && <span>Started at: {formatStartedAt(season.started_at)}</span>}
        <TournamentDescriptionMeta season={season} />
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
    { id: 'players', label: 'Players', href: `/tournament/${seasonName}/players` },
    {
      id: 'leaderboard',
      label: 'Leaderboard',
      href:
        stageContext.teamSeason && stageContext.progress && !stageContext.progress.started
          ? `/tournament/${seasonName}?view=leaderboard`
          : `/tournament/${seasonName}`,
    },
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

export async function generateMetadata({ params }: LayoutProps<'/tournament/[seasonName]'>) {
  const { seasonName } = await params
  return {
    title: `Season ${seasonName} | Observatory`,
  }
}
