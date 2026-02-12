import type { components } from "./generated/schema";

type Schemas = components["schemas"];

// ── Tournament ──────────────────────────────────────────────────────────
export type PolicyVersionSummary = Schemas["PolicyVersionSummary"];
export type PoolInfo = Schemas["PoolInfo"];
export type SeasonResponse = Schemas["SeasonResponse"];
export type LeaderboardEntry = Schemas["LeaderboardEntry"];
export type PoolMembership = Schemas["PoolMembership"];
export type PolicySummary = Schemas["PolicySummary"];
export type MatchSummary = Schemas["MatchSummary-Output"];
export type MatchPlayerSummary = Schemas["MatchPlayerSummary"];
export type MembershipHistoryEntry = Schemas["MembershipHistoryEntry"];
export type SeasonVersionInfo = Schemas["SeasonVersionInfo"];
