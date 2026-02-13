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

// ── Eval tasks (not in generated spec — routes have include_in_schema=False) ──
export type TaskStatus = 'unprocessed' | 'running' | 'canceled' | 'done' | 'error' | 'system_error'

export type EvalTask = {
  user_id: string
  user: UserRow | null
  id: number
  command: string
  data_uri: string | null
  git_hash: string | null
  attributes: Record<string, any>
  created_at: string
  is_finished: boolean
  latest_attempt_id: number | null
  attempt_number: number
  status: TaskStatus
  status_details: Record<string, any> | null
  assigned_at: string | null
  assignee: string | null
  started_at: string | null
  finished_at: string | null
  output_log_path: string | null
}

export type TaskAttempt = {
  id: number
  task_id: number
  attempt_number: number
  assigned_at: string | null
  assignee: string | null
  started_at: string | null
  finished_at: string | null
  output_log_path: string | null
  status: TaskStatus
  status_details: Record<string, any> | null
}

export type PaginatedEvalTasksResponse = {
  tasks: EvalTask[]
  total_count: number
  page: number
  page_size: number
  total_pages: number
}

export type TaskAttemptsResponse = {
  attempts: TaskAttempt[]
}

export type EvalTaskCreateRequest = {
  command: string
  git_hash?: string | null
  data_file?: Record<string, any> | null
  attributes?: Record<string, any>
}

// ── Policies ────────────────────────────────────────────────────────────
export type PolicyRow = WithUser<Schemas['PolicyRow']>
export type PolicyVersionRow = WithUser<Schemas['PolicyVersionRow']>
export type PoliciesResponse = {
  entries: PolicyRow[]
  total_count: number
}
export type PolicyVersionsResponse = {
  entries: PolicyVersionRow[]
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
export type SeasonMatchSummary = Schemas['MatchResponse']
export type SeasonMatchPlayerSummary = Schemas['MatchPlayerInfo']
export type SubmissionResponse = Schemas['SubmitResponse']
export type MembershipHistoryEntry = Schemas['MembershipHistoryEntry']

// ── SQL (not in generated spec — routes have include_in_schema=False) ──
export type TableInfo = {
  table_name: string
  column_count: number
  row_count: number
}
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
export type SQLQueryRequest = {
  query: string
}
export type SQLQueryResponse = {
  columns: string[]
  rows: any[][]
  row_count: number
}
export type AIQueryRequest = {
  description: string
}
export type AIQueryResponse = {
  query: string
}

// ── Smart Plugs (not in generated spec — routes have include_in_schema=False) ──
export type SmartPlugStatus = {
  key: string
  label: string
  alias?: string | null
  online?: boolean | null
  is_on?: boolean | null
  apower?: number | null
}
