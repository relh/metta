import {
  createLoader,
  parseAsInteger,
  parseAsString,
  parseAsStringLiteral,
} from "nuqs/server";

import { AutoRefresh } from "@observatory/components/AutoRefresh";
import { Card } from "@observatory/components/Card";
import { PaginatedControls } from "@observatory/components/PaginatedControls";
import { RefreshButton } from "@observatory/components/RefreshButton";
import { SearchParamInput } from "@observatory/components/SearchParamInput";
import { AccessDenied } from "@observatory/components/SoftmaxGuard";
import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { ALL_JOB_STATUSES } from "@observatory/lib/repo";
import { getRepo } from "@observatory/lib/repo/server";

import { JobFilters } from "./JobFilters";
import { JobsTable } from "./JobsTable";

const nuqsParams = {
  jobId: parseAsString.withDefault(""),
  policyVersionId: parseAsString.withDefault(""),
  status: parseAsStringLiteral(ALL_JOB_STATUSES),
  seasonId: parseAsString.withDefault(""),
  poolId: parseAsString.withDefault(""),
  page: parseAsInteger.withDefault(0),
};

const parseSearchParams = createLoader(nuqsParams);

export default async function EpisodeJobsPage({
  searchParams: rawSearchParams,
}: PageProps<"/observatory/episode-jobs">) {
  const repo = await getRepo();
  const userInfo = await repo.whoami();
  if (!userInfo.is_softmax_team_member) {
    return <AccessDenied />;
  }

  const searchParams = await parseSearchParams(rawSearchParams);
  const {
    jobId: jobIdFilter,
    policyVersionId: policyVersionIdFilter,
    status: statusFilter,
    seasonId: seasonIdFilter,
    poolId: poolIdFilter,
    page,
  } = searchParams;
  const pageSize = 50;

  const [jobs, seasons] = await Promise.all([
    repo.getJobs({
      job_type: "episode",
      statuses: statusFilter ? [statusFilter] : undefined,
      job_id: jobIdFilter || undefined,
      policy_version_id: policyVersionIdFilter || undefined,
      season_id: seasonIdFilter || undefined,
      pool_id: poolIdFilter || undefined,
      limit: pageSize,
      offset: page * pageSize,
    }),
    repo.getSeasons(),
  ]);
  const selectedSeason = seasons.find((s) => s.id === seasonIdFilter);
  const selectedSeasonDetail = selectedSeason
    ? await repo.getSeason(selectedSeason.name)
    : null;

  return (
    <div className="mx-auto max-w-[1600px] p-5">
      <ServerDebugDrain />
      <AutoRefresh />
      <Card title="Episode Jobs">
        <div className="mb-4 flex flex-wrap items-end gap-3">
          <JobFilters seasons={seasons} selectedSeason={selectedSeasonDetail} />
          <div>
            <div className="text-foreground-muted mb-1 text-xs">Job ID</div>
            <div className="w-64">
              <SearchParamInput
                paramName="jobId"
                placeholder="Filter by Job ID..."
              />
            </div>
          </div>
          <div className="self-end pb-0.5">
            <RefreshButton />
          </div>
        </div>
        <div className="overflow-x-auto">
          <JobsTable jobs={jobs} />
          {jobs.length === 0 && (
            <div className="text-foreground-muted p-5 text-center">
              No jobs found
            </div>
          )}
          <PaginatedControls isLastPage={jobs.length < pageSize} />
        </div>
      </Card>
    </div>
  );
}
