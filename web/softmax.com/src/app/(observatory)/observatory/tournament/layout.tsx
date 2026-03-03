import { FC, PropsWithChildren, Suspense } from "react";

import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";

import { SeasonSelect } from "./SeasonSelect";

const InnerSeasonSelect: FC = async () => {
  const repo = await getRepo();
  const seasons = await repo.getSeasons();

  return (
    <>
      <SeasonSelect seasons={seasons} />
      <ServerDebugDrain />
    </>
  );
};

export default function TournamentLayout({ children }: PropsWithChildren) {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <Suspense fallback={<SeasonSelect seasons={[]} />}>
        <InnerSeasonSelect />
      </Suspense>
      {children}
    </div>
  );
}
