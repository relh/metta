import type { ProgressResponse, StageStats } from "@observatory/lib/api";

export type TournamentStageFlowEntry = ProgressResponse["stage_flow"][number];

type StageFlowSelectionEntry = Pick<
  TournamentStageFlowEntry,
  "input_pool" | "status"
>;

export function stageLabel(name: string): string {
  if (name.startsWith("team-round-"))
    return `Team Round ${name.split("-").pop()}`;
  if (name.startsWith("sample-")) return `Sample ${name.split("-").pop()}`;
  if (name.startsWith("stage-")) return `Stage ${name.split("-").pop()}`;
  if (name === "policy-scores" || name.startsWith("policy-scores-"))
    return "Final Scores";
  return name;
}

export function stageKindLabel(kind: TournamentStageFlowEntry["kind"]): string {
  switch (kind) {
    case "policy_eval":
      return "Policy Stage";
    case "sample_teams":
      return "Seed Teams";
    case "team_eval":
      return "Team Stage";
    case "score_policies":
      return "Score Policies";
    default:
      return kind;
  }
}

export function stageFlowLabel(
  stage: Pick<TournamentStageFlowEntry, "index" | "kind" | "name">,
): string {
  return `${stage.index}. ${stage.name || stageKindLabel(stage.kind)}`;
}

export function isTeamSeason(stages: StageStats[]): boolean {
  return stages.some(
    (stage) =>
      stage.name === "policy-scores" ||
      stage.name.startsWith("policy-scores-") ||
      stage.name.startsWith("stage-") ||
      stage.name.startsWith("sample-") ||
      stage.name.startsWith("team-round-"),
  );
}

export function defaultSelectedStage(
  stages: StageStats[],
  stageFlow: StageFlowSelectionEntry[],
  started = true,
): string {
  const stageNames = new Set(stages.map((stage) => stage.name));
  const firstStage = stageFlow[0]?.input_pool;
  if (!started) {
    return firstStage && stageNames.has(firstStage)
      ? firstStage
      : (stages[0]?.name ?? firstStage ?? "");
  }

  const active = stageFlow.find((stage) => stage.status === "active");
  if (active && stageNames.has(active.input_pool)) {
    return active.input_pool;
  }

  const finalStage =
    stageFlow.length > 0 ? stageFlow[stageFlow.length - 1].input_pool : null;
  if (finalStage && stageNames.has(finalStage)) {
    return finalStage;
  }

  const withMatches = stages.filter((stage) => stage.match_count > 0);
  return withMatches.length > 0
    ? withMatches[withMatches.length - 1].name
    : (firstStage ?? stages[0]?.name ?? "");
}

export function resolveSelectedStage(
  stages: StageStats[],
  stageFlow: StageFlowSelectionEntry[],
  rawStage: string | null,
  started = true,
): string {
  const fallback = defaultSelectedStage(stages, stageFlow, started);
  if (!rawStage) return fallback;
  const stageNames = new Set(stages.map((stage) => stage.name));
  if (stageNames.has(rawStage)) return rawStage;
  const flowInputPools = new Set(stageFlow.map((stage) => stage.input_pool));
  return flowInputPools.has(rawStage) ? rawStage : fallback;
}

export function stageKindForPool(
  stageFlow: TournamentStageFlowEntry[],
  poolName: string,
): TournamentStageFlowEntry["kind"] | null {
  const byInputPool = stageFlow.find((stage) => stage.input_pool === poolName);
  if (byInputPool) return byInputPool.kind;

  const byOutputPool = stageFlow.find(
    (stage) => stage.output_pool === poolName,
  );
  return byOutputPool?.kind ?? null;
}

export function nearestStageWithMatches(
  stages: StageStats[],
  selectedStage: string,
): string | null {
  const indexedStagesWithMatches = stages
    .map((stage, index) => ({ stage, index }))
    .filter(({ stage }) => stage.match_count > 0);
  if (indexedStagesWithMatches.length === 0) return null;

  const selectedIndex = stages.findIndex(
    (stage) => stage.name === selectedStage,
  );
  if (selectedIndex === -1) {
    return indexedStagesWithMatches[indexedStagesWithMatches.length - 1].stage
      .name;
  }

  let closest = indexedStagesWithMatches[0];
  let minDistance = Math.abs(selectedIndex - closest.index);
  for (const candidate of indexedStagesWithMatches.slice(1)) {
    const distance = Math.abs(selectedIndex - candidate.index);
    if (distance < minDistance) {
      closest = candidate;
      minDistance = distance;
    }
  }
  return closest.stage.name;
}
