import { notFound } from "next/navigation";
import { FC, Suspense } from "react";

import { AutoRefresh } from "@observatory/components/AutoRefresh";
import { type LinkTab, LinkTabs } from "@observatory/components/LinkTabs";
import { Spinner } from "@observatory/components/Spinner";
import { TournamentDescriptionMeta } from "@observatory/components/tournament/TournamentDescriptionMeta";
import type { SeasonDetail } from "@observatory/lib/api";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import {
  matchesRoute,
  seasonPlayersRoute,
  seasonTeamsRoute,
} from "@observatory/lib/routes";
import { getSeasonStageContext } from "@observatory/lib/tournament/api";
import { parseDatetime } from "@observatory/utils/datetime";

import { StageProgress } from "./StageProgress";
import { defaultSelectedStage } from "./stageSelection";

const SEASON_STATUS_LABELS: Record<SeasonDetail["status"], string> = {
  not_started: "Not started",
  in_progress: "In progress",
  complete: "Complete",
};

const SEASON_STATUS_BADGE_CLASSES: Record<SeasonDetail["status"], string> = {
  not_started: "border-border text-foreground-muted bg-transparent",
  in_progress:
    "border-green-500/40 text-green-700 dark:text-green-300 bg-transparent",
  complete:
    "border-blue-500/40 text-blue-700 dark:text-blue-300 bg-transparent",
};

const formatCreatedAt = (iso: string) => {
  const createdAt = parseDatetime(iso);
  if (!createdAt) {
    return "—";
  }
  return createdAt.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
};

const SeasonDetails: FC<{ seasonName: string }> = async ({ seasonName }) => {
  const repo = await getRepo();
  const season = await repo.getSeason(seasonName);
  if (!season) {
    return notFound();
  }

  return (
    <div className="space-y-2">
      <ServerDebugDrain />
      <div>
        <div className="flex flex-wrap items-baseline gap-2">
          <h1 className="text-foreground m-0 text-3xl font-bold">
            {season.display_name}
          </h1>
          <span
            className={`inline-flex items-center rounded-full border px-1.5 py-0 text-[11px] font-medium ${SEASON_STATUS_BADGE_CLASSES[season.status]}`}
          >
            {SEASON_STATUS_LABELS[season.status]}
          </span>
          {!season.public && (
            <span className="inline-flex items-center rounded-full border border-yellow-500/40 px-1.5 py-0 text-[11px] font-medium text-yellow-700 dark:text-yellow-300">
              private
            </span>
          )}
        </div>
        {season.summary && (
          <div className="text-foreground-muted mt-0.5 text-sm">
            {season.summary}
          </div>
        )}
      </div>
      <div className="text-foreground-muted flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span>
          Entrants: {season.entrant_count}
          {season.active_entrant_count !== season.entrant_count
            ? ` (${season.active_entrant_count} active)`
            : ""}
        </span>
        <span>Stages: {season.stage_count}</span>
        {season.created_at && (
          <span>Created at: {formatCreatedAt(season.created_at)}</span>
        )}
        <TournamentDescriptionMeta season={season} />
      </div>
    </div>
  );
};

export default async function SeasonPage({
  params,
  children,
}: LayoutProps<"/observatory/tournament/[seasonName]">) {
  const { seasonName } = await params;

  const repo = await getRepo();
  const stageContext = await getSeasonStageContext(repo, seasonName);
  const stageKindsByPool = stageContext.progress
    ? Object.fromEntries(
        stageContext.progress.stage_flow.map((stage) => [
          stage.input_pool,
          stage.kind,
        ]),
      )
    : undefined;

  const tabs: LinkTab[] = [
    { id: "players", label: "Players", href: seasonPlayersRoute(seasonName) },
    {
      id: "matches",
      label: "Matches",
      href: matchesRoute(seasonName, {}),
      ...(stageContext.progress
        ? { allowedStageKinds: ["team_eval", "policy_eval"] }
        : {}),
    },
    ...(stageContext.hasTeams
      ? [
          {
            id: "teams",
            label: "Teams",
            href: seasonTeamsRoute(seasonName),
            ...(stageContext.progress
              ? { allowedStageKinds: ["team_eval"] }
              : {}),
          },
        ]
      : []),
  ];

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
            stageContext.progress.started,
          )}
          started={stageContext.progress.started}
        />
      )}
      <LinkTabs
        tabs={tabs}
        stageKindsByPool={stageKindsByPool}
        defaultStage={stageContext.selectedStage}
      />
      {children}
    </div>
  );
}

export async function generateMetadata({
  params,
}: LayoutProps<"/observatory/tournament/[seasonName]">) {
  const { seasonName } = await params;
  return {
    title: `Season ${seasonName} | Observatory`,
  };
}
