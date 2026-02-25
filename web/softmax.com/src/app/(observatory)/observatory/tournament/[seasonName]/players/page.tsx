import { createLoader, parseAsString } from "nuqs/server";

import { ServerDebugDrain } from "@observatory/lib/debug/ServerDebugDrain";
import { getRepo } from "@observatory/lib/repo/server";
import {
  getPlayerStages,
  getSeasonStageContext,
} from "@observatory/lib/tournament/api";
import { formatRelativeTime } from "@observatory/utils/datetime";

import { stageFlowLabel, stageLabel } from "../stageSelection";
import { formatPolicyDisplay } from "../utils";
import {
  PlayersSortableTable,
  type PlayersTableRow,
  type PlayersTableStageCell,
} from "./PlayersSortableTable";
import {
  PlayersStageScoreChart,
  type PolicyStageSeries,
} from "./PlayersStageScoreChart";
import { compareMissingLast } from "./scoreSort";
import { SubmitForm } from "./SubmitForm";

const parseSearchParams = createLoader({ stage: parseAsString });

type PolicyStageStats = {
  mean: number;
  stddev: number | null;
};

function calculateSampleStddev(values: number[], mean: number): number | null {
  if (values.length === 0) {
    return null;
  }
  if (values.length === 1) {
    return 0;
  }

  const squaredDistanceSum = values.reduce(
    (sum, value) => sum + (value - mean) ** 2,
    0,
  );
  return Math.sqrt(squaredDistanceSum / (values.length - 1));
}

export default async function PlayersPage({
  params,
  searchParams,
}: PageProps<"/observatory/tournament/[seasonName]/players">) {
  const { seasonName } = await params;
  const parsed = await parseSearchParams(searchParams);
  const repo = await getRepo();
  const [season, policies, stageContext] = await Promise.all([
    repo.getSeason(seasonName),
    repo.getSeasonPolicies(seasonName),
    getSeasonStageContext(repo, seasonName, parsed.stage),
  ]);
  const existingPolicyVersionIds = new Set(policies.map((p) => p.policy.id));
  const selectedStage = stageContext.selectedStage;
  const selectedFlowStage = selectedStage
    ? stageContext.progress?.stage_flow.find(
        (stage) => stage.input_pool === selectedStage,
      )
    : null;
  const selectedStageStatus = selectedFlowStage?.status ?? null;
  const tournamentNotStarted = stageContext.progress?.started !== true;
  const playerStages = getPlayerStages(
    stageContext.stages,
    stageContext.progress,
  );
  const poolNames =
    stageContext.progress && playerStages.length > 0
      ? playerStages.map((stage) => stage.name)
      : selectedStage
        ? [selectedStage]
        : season.pools.map((pool) => pool.name);
  const stageFlowByPool = new Map(
    (stageContext.progress?.stage_flow ?? []).map((stage) => [
      stage.input_pool,
      stage,
    ]),
  );
  const stageKindByPool = new Map(
    (stageContext.progress?.stage_flow ?? []).map((stage) => [
      stage.input_pool,
      stage.kind,
    ]),
  );
  const stageLabelByPool = new Map(
    poolNames.map((poolName) => {
      const stageFlow = stageFlowByPool.get(poolName);
      return [
        poolName,
        stageFlow ? stageFlowLabel(stageFlow) : stageLabel(poolName),
      ] as const;
    }),
  );
  const selectedDisplayStage =
    selectedStage && poolNames.includes(selectedStage) ? selectedStage : null;
  const showPendingState =
    selectedStage !== null && selectedStageStatus === "pending";
  const showEmptyState = policies.length === 0;
  const shouldRenderPlayerTable = !showPendingState && !showEmptyState;
  const policyLabelById = new Map(
    policies.map((policy) => [policy.policy.id, formatPolicyDisplay(policy)]),
  );
  const teamPageSize = 200;
  const stageScoreStatsByPool = shouldRenderPlayerTable
    ? new Map(
        await Promise.all(
          poolNames.map(
            async (
              poolName,
            ): Promise<readonly [string, Map<string, PolicyStageStats>]> => {
              const stageKind = stageKindByPool.get(poolName);
              if (stageKind === "team_eval") {
                const teams: Awaited<ReturnType<typeof repo.getSeasonTeams>> =
                  [];
                let offset = 0;
                while (true) {
                  // Team stage leaderboard endpoint defaults to top-N results; use full team pages for ranking.
                  const page = await repo.getSeasonTeams(seasonName, {
                    pool_name: poolName,
                    limit: teamPageSize,
                    offset,
                  });
                  teams.push(...page);
                  if (page.length < teamPageSize) break;
                  offset += teamPageSize;
                }
                const scoresByPolicy = new Map<string, number[]>();
                for (const team of teams) {
                  if (team.score === null) continue;
                  for (const cog of team.cogs) {
                    const scores = scoresByPolicy.get(cog.policy.id);
                    if (scores) {
                      scores.push(team.score);
                    } else {
                      scoresByPolicy.set(cog.policy.id, [team.score]);
                    }
                  }
                }
                const statsByPolicy = new Map<string, PolicyStageStats>();
                for (const [policyId, scores] of scoresByPolicy) {
                  if (scores.length === 0) {
                    continue;
                  }
                  const mean =
                    scores.reduce((sum, score) => sum + score, 0) /
                    scores.length;
                  statsByPolicy.set(policyId, {
                    mean,
                    stddev: calculateSampleStddev(scores, mean),
                  });
                }
                return [poolName, statsByPolicy] as const;
              }

              const leaderboard = await repo.getSeasonStageLeaderboard(
                seasonName,
                "policy",
                poolName,
              );
              return [
                poolName,
                new Map(
                  leaderboard.map((entry) => [
                    entry.policy.id,
                    {
                      mean: entry.score,
                      stddev: entry.score_stddev ?? null,
                    },
                  ]),
                ),
              ] as const;
            },
          ),
        ),
      )
    : new Map<string, Map<string, PolicyStageStats>>();
  const defaultPolicySort = (
    a: (typeof policies)[number],
    b: (typeof policies)[number],
  ) => {
    for (const poolName of [...poolNames].reverse()) {
      const aScore = stageScoreStatsByPool
        .get(poolName)
        ?.get(a.policy.id)?.mean;
      const bScore = stageScoreStatsByPool
        .get(poolName)
        ?.get(b.policy.id)?.mean;
      const byScore = compareMissingLast(aScore, bScore);
      if (byScore !== 0) return byScore;
    }
    if (a.entered_at !== b.entered_at)
      return b.entered_at.localeCompare(a.entered_at);
    return a.policy.id.localeCompare(b.policy.id);
  };
  const defaultSortedPolicies = shouldRenderPlayerTable
    ? [...policies].sort(defaultPolicySort)
    : policies;
  const chartStages = shouldRenderPlayerTable
    ? poolNames.map((poolName) => ({
        key: poolName,
        label: stageLabelByPool.get(poolName) ?? poolName,
      }))
    : [];
  const stageColumns = shouldRenderPlayerTable
    ? poolNames.map((poolName) => ({
        key: poolName,
        label: stageLabelByPool.get(poolName) ?? poolName,
        selected: selectedDisplayStage === poolName,
      }))
    : [];
  const tableRows: PlayersTableRow[] = shouldRenderPlayerTable
    ? defaultSortedPolicies.map((policy, index) => {
        const poolStatusMap = Object.fromEntries(
          policy.pools.map((pool) => [pool.pool_name, pool]),
        );
        const stages: Record<string, PlayersTableStageCell> =
          Object.fromEntries(
            poolNames.map((poolName) => {
              const pool = poolStatusMap[poolName];
              if (!pool) {
                return [
                  poolName,
                  {
                    hasPool: false,
                    mean: null,
                    stddev: null,
                    completed: 0,
                    failed: 0,
                    pending: 0,
                  },
                ] satisfies [string, PlayersTableStageCell];
              }

              const stageStats = stageScoreStatsByPool
                .get(poolName)
                ?.get(policy.policy.id);
              return [
                poolName,
                {
                  hasPool: true,
                  mean: stageStats?.mean ?? null,
                  stddev: stageStats?.stddev ?? null,
                  completed: pool.completed,
                  failed: pool.failed,
                  pending: pool.pending,
                },
              ] satisfies [string, PlayersTableStageCell];
            }),
          );

        return {
          policyId: policy.policy.id,
          policyLabel:
            policyLabelById.get(policy.policy.id) ??
            formatPolicyDisplay(policy),
          enteredAt: policy.entered_at,
          enteredAtLabel: formatRelativeTime(policy.entered_at),
          stages,
          defaultRank: index,
        };
      })
    : [];
  const chartSeries: PolicyStageSeries[] = shouldRenderPlayerTable
    ? tableRows.map((row) => ({
        policyId: row.policyId,
        policyLabel: row.policyLabel,
        points: poolNames.map((poolName) => {
          const stage = row.stages[poolName];
          return {
            stageKey: poolName,
            mean: stage?.hasPool ? stage.mean : null,
            stddev: stage?.hasPool ? stage.stddev : null,
            matches: stage?.hasPool ? stage.completed : 0,
          };
        }),
      }))
    : [];

  return (
    <div className="space-y-4">
      <ServerDebugDrain />
      {tournamentNotStarted && (
        <SubmitForm
          seasonName={seasonName}
          existingPolicyVersionIds={existingPolicyVersionIds}
        />
      )}
      {showPendingState ? (
        <div className="text-foreground-muted py-4">
          This stage has not started yet.
        </div>
      ) : showEmptyState ? (
        <div className="text-foreground-muted py-4">
          No players submitted yet
        </div>
      ) : (
        <div className="space-y-4">
          <PlayersStageScoreChart stages={chartStages} series={chartSeries} />
          <PlayersSortableTable
            seasonName={seasonName}
            hasTournamentProgress={Boolean(stageContext.progress)}
            showEnteredColumn={tournamentNotStarted}
            columns={stageColumns}
            rows={tableRows}
          />
        </div>
      )}
    </div>
  );
}
