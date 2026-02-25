import { Metadata } from "next";
import { redirect } from "next/navigation";

import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import { seasonRoute } from "@observatory/lib/routes";
import {
  seasonTabModeForName,
  TOURNAMENT_DEFAULT_SEASON_NAME,
} from "@observatory/lib/tournament/tabMode";

export default async function TournamentPage({
  searchParams,
}: PageProps<"/observatory/tournament">) {
  const repo = await getRepo();
  const seasons = await repo.getSeasons();
  if (seasons.length === 0) {
    return (
      <div className="mx-auto flex max-w-5xl justify-center p-6 py-16">
        <ServerDebugDrain />
        <div className="text-foreground-muted">No seasons found</div>
      </div>
    );
  }

  const params = await searchParams;
  const requestedMode =
    params.mode === "tournament" ? "tournament" : "freeplay";
  const modeSeasons = seasons.filter(
    (season) => seasonTabModeForName(season.name) === requestedMode,
  );
  const preferredSeasons = modeSeasons.length > 0 ? modeSeasons : seasons;
  const defaultSeason =
    (requestedMode === "tournament"
      ? preferredSeasons.find(
          (season) => season.name === TOURNAMENT_DEFAULT_SEASON_NAME,
        )
      : null) ??
    preferredSeasons.find((season) => season.is_default) ??
    preferredSeasons[0];
  const effectiveMode =
    modeSeasons.length > 0
      ? requestedMode
      : seasonTabModeForName(defaultSeason.name);
  redirect(seasonRoute(defaultSeason.name, { mode: effectiveMode }));
}

export const metadata: Metadata = {
  title: "Tournaments | Observatory",
};
