/**
 * Re-exports generated API types from the internal OpenAPI spec.
 *
 * Usage:
 *   import type { PolicyRow, JobRequest } from '@/lib/api'
 *
 * To regenerate after backend changes:
 *   cd web/observatory && npm run generate-api-types
 *
 * Some types below apply `Required<>` or override individual fields because
 * the generated OpenAPI spec marks Pydantic defaults as optional, or uses
 * `additionalProperties: {}` → `unknown` for dict fields.  As the backend
 * spec improves (roadmap step 9), these overrides can be removed.
 */

import type { components } from './generated/schema'

// Shorthand for all component schemas
export type Schemas = components['schemas']

// Utility: make `user` field required-but-nullable (Pydantic always returns it)
type WithUser<T extends { user?: Schemas['UserRow'] | null }> = Omit<T, 'user'> & {
  user: Schemas['UserRow'] | null
}

// ── User ────────────────────────────────────────────────────────────────
export type UserRow = Schemas['UserRow']

// Utility: Pydantic `dict[str, Any]` → OpenAPI `additionalProperties: {}`
// → TS `{ [key: string]: unknown }`.  Override to `Record<string, any>` so
// property access works without narrowing.  Removable after roadmap step 9.
type AnyDict<T, K extends keyof T> = Omit<T, K> & { [P in K]: Record<string, any> }

// ── Eval tasks ──────────────────────────────────────────────────────────
export type EvalTask = WithUser<
  Omit<Required<Schemas['EvalTaskRow']>, 'attributes' | 'status_details'> & {
    attributes: Record<string, any>
    status_details: Record<string, any> | null
  }
>
export type TaskAttempt = Omit<Schemas['TaskAttemptRow'], 'status_details'> & {
  status_details: Record<string, any> | null
}
export type PaginatedEvalTasksResponse = Omit<Schemas['PaginatedTasksResponse'], 'tasks'> & {
  tasks: EvalTask[]
}
export type TaskAttemptsResponse = Omit<Schemas['TaskAttemptsResponse'], 'attempts'> & {
  attempts: TaskAttempt[]
}
export type EvalTaskCreateRequest = Schemas['TaskCreateRequest']

// ── Policies ────────────────────────────────────────────────────────────
export type PolicyRow = WithUser<Schemas['PolicyRow']>
export type PublicPolicyVersionRow = WithUser<Schemas['PublicPolicyVersionRow']>
export type PolicyVersionWithName = WithUser<Schemas['PolicyVersionWithName']>
export type PoliciesResponse = {
  entries: PolicyRow[]
  total_count: number
}
export type PolicyVersionsResponse = {
  entries: PublicPolicyVersionRow[]
  total_count: number
}

// ── Episodes ────────────────────────────────────────────────────────────
export type EpisodeWithTags = {
  id: string
  replay_url: string | null
  thumbnail_url: string | null
  attributes: Record<string, any>
  eval_task_id: string | null
  created_at: string
  tags: Record<string, string>
  avg_rewards: Record<string, number>
  job_id: string | null
}
export type EpisodeQueryRequest = Schemas['EpisodeQueryRequest']
export type EpisodeQueryResponse = {
  episodes: EpisodeWithTags[]
}
export type EpisodePolicyStat = Schemas['EpisodePolicyStat']

// ── Jobs ────────────────────────────────────────────────────────────────
export type JobStatus = Schemas['JobStatus']
export type JobPolicyVersionSummary = Schemas['JobPolicyVersionSummary']
export type JobEpisodeInfo = {
  replay_url: string | null
  attributes: Record<string, any> | null
  policy_stats: EpisodePolicyStat[]
}
export type JobRequest = Omit<WithUser<Schemas['JobRequestResponse']>, 'episode' | 'job' | 'result'> & {
  episode?: JobEpisodeInfo | null
  job: Record<string, any>
  result: Record<string, any> | null
}
export type JobMatchInfo = Schemas['JobMatchInfo']

// ── Stats ───────────────────────────────────────────────────────────────
export type AgentStatsDetail = Schemas['AgentStatsDetail']
export type PolicyStatsDetail = Schemas['PolicyStatsDetail']
export type EpisodeStatsResponse = Schemas['EpisodeStatsResponse']

// ── Tournament ──────────────────────────────────────────────────────────
export type PolicyVersionSummary = Schemas['PolicyVersionSummary']
export type LeaderboardEntry = Schemas['LeaderboardEntry']
export type PoolInfo = Schemas['PoolInfo']
export type PoolMembership = Schemas['PoolMembership']
export type PolicySummary = Schemas['PolicySummary']
export type SeasonDetail = Schemas['SeasonResponse']
export type SeasonVersionInfo = Schemas['SeasonVersionInfo']
export type MatchStatus = Schemas['MatchSummary-Output']['status']
export type SeasonMatchSummary = Schemas['MatchSummary-Output']
export type SeasonMatchPlayerSummary = Schemas['MatchPlayerSummary']
export type SubmissionResponse = Schemas['SubmitResponse']
export type MembershipHistoryEntry = Schemas['MembershipHistoryEntry']

// ── SQL ─────────────────────────────────────────────────────────────────
export type TableInfo = Schemas['TableInfo']
export type TableSchema = {
  table_name: string
  columns: Array<{
    name: string
    type: string
    nullable: boolean
    default: string | null
    max_length: number | null
  }>
}
export type SQLQueryRequest = Schemas['SQLQueryRequest']
export type SQLQueryResponse = {
  columns: string[]
  rows: any[][]
  row_count: number
}
export type AIQueryRequest = Schemas['AIQueryRequest']
export type AIQueryResponse = Schemas['AIQueryResponse']

// ── Smart Plugs ─────────────────────────────────────────────────────────
export type SmartPlugStatus = Schemas['SmartPlugStatus']
