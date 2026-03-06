/**
 * Re-exports generated API types from the internal OpenAPI spec.
 *
 * Usage:
 *   import type { PolicyRow, JobRequest } from '@/lib/api'
 *
 * To regenerate after backend changes:
 *   cd web/softmax.com && pnpm run generate-api-types
 *
 * Some types below apply `Required<>` or override individual fields because
 * the generated OpenAPI spec marks Pydantic defaults as optional, or uses
 * `additionalProperties: {}` → `unknown` for dict fields.  As the backend
 * spec improves (roadmap step 9), these overrides can be removed.
 */

import type { components, operations } from "./generated/schema";

// Shorthand for all component schemas
export type Schemas = components["schemas"];
export type Operations = operations;

// Utility: make `user` field required-but-nullable (Pydantic always returns it)
type WithUser<T extends { user?: Schemas["UserRow"] | null }> = Omit<
  T,
  "user"
> & {
  user: Schemas["UserRow"] | null;
};

// ── User ────────────────────────────────────────────────────────────────
export type UserRow = Schemas["UserRow"];

// ── Policies ────────────────────────────────────────────────────────────
export type PolicyRow = WithUser<Schemas["PolicyRow"]>;
export type PolicyVersionRow = WithUser<Schemas["PolicyVersionRow"]>;
export type PoliciesResponse = {
  entries: PolicyRow[];
  total_count: number;
};
export type PolicyVersionsResponse = {
  entries: PolicyVersionRow[];
  total_count: number;
};

// ── Episodes ────────────────────────────────────────────────────────────
export type EpisodeWithTags = {
  id: string;
  replay_url: string | null;
  thumbnail_url: string | null;
  attributes: Record<string, any>;
  eval_task_id: string | null;
  created_at: string;
  tags: Record<string, string>;
  avg_rewards: Record<string, number>;
  job_id: string | null;
};
export type EpisodeQueryRequest = Schemas["EpisodeQueryRequest"];
export type EpisodeQueryResponse = {
  episodes: EpisodeWithTags[];
};
export type EpisodePolicyStat = Schemas["EpisodePolicyStat"];

// ── Jobs ────────────────────────────────────────────────────────────────
export type JobStatus = Schemas["JobStatus"];
export type JobPolicyVersionSummary = Schemas["JobPolicyVersionSummary"];
export type JobEpisodeInfo = {
  replay_url: string | null;
  attributes: Record<string, any> | null;
  policy_stats: EpisodePolicyStat[];
};
export type JobRequest = Omit<
  WithUser<Schemas["JobRequestResponse"]>,
  "episode" | "job" | "result"
> & {
  episode?: JobEpisodeInfo | null;
  job: Record<string, any>;
  result: Record<string, any> | null;
};
export type JobMatchInfo = Schemas["JobMatchInfo"];

// ── Stats ───────────────────────────────────────────────────────────────
export type AgentStatsDetail = Schemas["AgentStatsDetail"];
export type PolicyStatsDetail = Schemas["PolicyStatsDetail"];
export type EpisodeStatsResponse = Schemas["EpisodeStatsResponse"];

// ── Tournament ──────────────────────────────────────────────────────────
export type PolicyVersionSummary = Schemas["PolicyVersionSummary"];
export type LeaderboardEntry = Schemas["LeaderboardEntry"];
export type ScorePoliciesLeaderboardEntry =
  Schemas["ScorePoliciesLeaderboardEntry"];
export type StageLeaderboardType =
  operations["get_stage_leaderboard_by_type_tournament_seasons__season_name__leaderboard__leaderboard_type___pool_name__get"]["parameters"]["path"]["leaderboard_type"];
export type StageLeaderboardQuery = NonNullable<
  operations["get_stage_leaderboard_by_type_tournament_seasons__season_name__leaderboard__leaderboard_type___pool_name__get"]["parameters"]["query"]
>;
export type SeasonLeaderboardQuery = NonNullable<
  operations["get_leaderboard_tournament_seasons__season_name__leaderboard_get"]["parameters"]["query"]
>;
export type SeasonTeamsQuery = NonNullable<
  operations["get_teams_tournament_seasons__season_name__teams_get"]["parameters"]["query"]
>;
export type PoolInfo = Schemas["PoolInfo"];
export type PoolMembership = Schemas["PoolMembership"];
export type PolicySummary = Schemas["PolicySummary"];
export type SeasonSummary = Schemas["SeasonSummary"];
export type SeasonDetail = Schemas["SeasonDetail"];
export type SeasonVersionInfo = Schemas["SeasonVersionInfo"];
export type SeasonMatchSummary = Schemas["MatchResponse"];
export type SeasonMatchPlayerSummary = Schemas["MatchPlayerInfo"];
export type SubmissionResponse = Schemas["SubmitResponse"];
export type MembershipHistoryEntry = Schemas["MembershipHistoryEntry"];
export type ProgressResponse = Omit<
  Schemas["TeamTournamentProgress"],
  "stage_flow"
> & {
  stage_flow: NonNullable<Schemas["TeamTournamentProgress"]["stage_flow"]>;
};
export type StageStats = Schemas["StageStats"];
export type TeamSummary = Schemas["TeamSummary"];
export type TeamCogSummary = Schemas["TeamCogSummary"];

// ── SQL (not in generated spec — routes have include_in_schema=False) ──
export type TableInfo = {
  table_name: string;
  column_count: number;
  row_count: number;
};
export type TableSchema = {
  table_name: string;
  columns: Array<{
    name: string;
    type: string;
    nullable: boolean;
    default: string | null;
    max_length: number | null;
  }>;
};
export type SQLQueryRequest = {
  query: string;
};
export type SQLQueryResponse = {
  columns: string[];
  rows: any[][];
  row_count: number;
};
export type AIQueryRequest = {
  description: string;
};
export type AIQueryResponse = {
  query: string;
};

// ── Service Accounts ────────────────────────────────────────────────────
export type ServiceAccountResponseBase = Schemas["ServiceAccountResponseBase"];
export type ServiceAccountCreateResponse =
  Schemas["ServiceAccountCreateResponse"];

// ── Smart Plugs (not in generated spec — routes have include_in_schema=False) ──
export type SmartPlugStatus = {
  key: string;
  label: string;
  alias?: string | null;
  online?: boolean | null;
  is_on?: boolean | null;
  apower?: number | null;
};
