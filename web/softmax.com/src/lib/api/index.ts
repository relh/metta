import type { components } from "./generated/schema";

type Schemas = components["schemas"];

// ── Tournament ──────────────────────────────────────────────────────────
export type PolicyVersionSummary = Schemas["PolicyVersionSummary"];
export type PoolInfo = Schemas["PoolInfo"];
export type SeasonSummary = Schemas["SeasonSummary"];
export type SeasonDetail = Schemas["SeasonDetail"];
export type LeaderboardEntry = Schemas["LeaderboardEntry"];
export type PoolMembership = Schemas["PoolMembership"];
export type PolicySummary = Schemas["PolicySummary"];
export type MatchResponse = Schemas["MatchResponse"];
export type MatchPlayerInfo = Schemas["MatchPlayerInfo"];
export type MembershipHistoryEntry = Schemas["MembershipHistoryEntry"];
export type SeasonVersionInfo = Schemas["SeasonVersionInfo"];
