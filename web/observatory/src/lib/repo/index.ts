import { notFound, redirect } from 'next/navigation'

import type {
  AIQueryRequest,
  AIQueryResponse,
  EpisodeQueryRequest,
  EpisodeQueryResponse,
  EpisodeStatsResponse,
  EvalTask,
  EvalTaskCreateRequest,
  JobRequest,
  JobStatus,
  LeaderboardEntry,
  MembershipHistoryEntry,
  PaginatedEvalTasksResponse,
  PoliciesResponse,
  PolicySummary,
  PolicyVersionRow,
  PolicyVersionSummary,
  PolicyVersionsResponse,
  SQLQueryRequest,
  SQLQueryResponse,
  SeasonDetail,
  SeasonMatchSummary,
  SeasonVersionInfo,
  SmartPlugStatus,
  SubmissionResponse,
  TableInfo,
  TableSchema,
  TaskAttemptsResponse,
} from '@/lib/api'
import { isOutageSimulated } from '@/lib/debug/simulate-outage'

// Re-export generated API types so existing `import { X } from '@/lib/repo'`
// statements continue to work.
export type {
  AIQueryRequest,
  AIQueryResponse,
  AgentStatsDetail,
  EpisodePolicyStat,
  EpisodeQueryRequest,
  EpisodeQueryResponse,
  EpisodeStatsResponse,
  EpisodeWithTags,
  EvalTask,
  EvalTaskCreateRequest,
  TaskAttempt,
  TaskStatus,
  JobEpisodeInfo,
  JobMatchInfo,
  JobPolicyVersionSummary,
  JobRequest,
  JobStatus,
  LeaderboardEntry,
  MembershipHistoryEntry,
  PaginatedEvalTasksResponse,
  PoliciesResponse,
  PolicyRow,
  PolicyStatsDetail,
  PolicySummary,
  PolicyVersionRow,
  PolicyVersionSummary,
  PolicyVersionsResponse,
  PoolInfo,
  PoolMembership,
  SQLQueryRequest,
  SQLQueryResponse,
  SeasonDetail,
  SeasonMatchPlayerSummary,
  SeasonMatchSummary,
  SeasonVersionInfo,
  SmartPlugStatus,
  SubmissionResponse,
  TableInfo,
  TableSchema,
  TaskAttemptsResponse,
  UserRow,
} from '@/lib/api'

// ── Frontend-only types (not from the API spec) ─────────────────────────

const decodePathSegment = (value: string) => {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

const encodePathSegment = (value: string) => encodeURIComponent(decodePathSegment(value))

export type MatchStatus = 'pending' | 'scheduled' | 'running' | 'completed' | 'failed'

export type TaskFilters = {
  command?: string
  user_id?: string
  status?: string
  assignee?: string
  git_hash?: string
  created_at?: string
  assigned_at?: string
}

export const ALL_JOB_STATUSES = ['pending', 'dispatched', 'running', 'completed', 'failed'] as const

// Dashboard types (frontend-only, not from API spec)
export type DashboardKpis = {
  move_efficiency: number
  action_success_rate: number
  vibe_change_rate: number
  resource_retention: number
  freeze_vulnerability: number
  junction_control_rate: number
  alignment_stability: number
  net_alignment_rate: number
  avg_reward: number
  noop_rate: number
  resource_efficiency_per_step: number
  hearts_to_junction_rate: number
  reward_consistency: number
  reward_nonzero_pct: number
  profile_aggressive: number
  profile_defensive: number
  profile_resource_hoarder: number
  profile_junction_hunter: number
  profile_mobile_scout: number
  diagnostics: string[]
}

export type DashboardTeamCompStats = {
  composition: string
  count: number
  avg_reward: number
  avg_move_efficiency: number
  avg_junction_aligned: number
  avg_resource_gained: number
}

export type DashboardOpponentStats = {
  count: number
  total_reward: number
  avg_reward: number
  avg_metrics: Record<string, number>
  strategy_profile: Record<string, number>
}

export type DashboardDerived = {
  kpis: DashboardKpis
  team_comp: DashboardTeamCompStats[]
  opponent_metrics: Record<string, DashboardOpponentStats>
}

export type DashboardEpisode = {
  episode_id: string
  job_id: string
  opponent_name: string
  opponent_version: number
  team_composition: string
  reward: number
  status: string
  error_type: string | null
  steps: number
  metrics: Record<string, number>
}

export type DashboardPolicy = {
  id: string
  name: string
  version: number
  rank: number | null
  score: number | null
  matches: number
}

export type DashboardResponse = {
  policy: DashboardPolicy
  episodes: DashboardEpisode[]
  season: string
  generated_at: string
  derived: DashboardDerived
}

export type DashboardAnalysisResponse = {
  analysis: string
}

export type RequestLogEntry = {
  id: string
  endpoint: string
  method: string
  durationMs: number
  status: number
  error?: string
  source: 'server' | 'client'
  timestamp: number
}

export type OnRequestCallback = (entry: RequestLogEntry) => void

let nextRequestId = 0

export class Repo {
  constructor(
    public baseUrl: string = 'http://localhost:8000',
    private token: string | null = null,
    private onRequest?: OnRequestCallback
  ) {}

  private getHeaders(contentType?: string): Record<string, string> {
    const headers: Record<string, string> = {}

    if (contentType) {
      headers['Content-Type'] = contentType
    }

    const token = this.token
    if (token) {
      headers['X-Auth-Token'] = token
    }

    return headers
  }

  private logRequest(endpoint: string, method: string, startTime: number, status: number, error?: string) {
    if (!this.onRequest) return
    this.onRequest({
      id: `req-${nextRequestId++}-${Date.now()}`,
      endpoint,
      method,
      durationMs: Math.round(performance.now() - startTime),
      status,
      error,
      source: typeof window === 'undefined' ? 'server' : 'client',
      timestamp: Date.now(),
    })
  }

  private throwIfOutage(endpoint: string, method: string): void {
    if (!isOutageSimulated()) return
    const startTime = performance.now()
    this.logRequest(endpoint, method, startTime, 0, 'Simulated API outage')
    throw new Error('Simulated API outage')
  }

  private async handleErrorResponse(response: Response): Promise<never> {
    if (response.status === 401) {
      if (typeof window === 'undefined') {
        redirect('/')
      } else {
        window.location.href = '/'
        throw new Error('Session expired, redirecting to login...')
      }
    }
    if (response.status === 404) {
      if (typeof window === 'undefined') {
        notFound()
      }
      throw new Error('Not found')
    }
    if (response.status === 503) {
      throw new Error('Service temporarily unavailable — please try again')
    }
    let detail: string | undefined
    try {
      const body = await response.json()
      detail = body.detail
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(
      detail ? JSON.stringify(detail, null, 2) : `API call failed: ${response.status} ${response.statusText}`
    )
  }

  private async apiCall<T>(endpoint: string): Promise<T> {
    this.throwIfOutage(endpoint, 'GET')
    const startTime = performance.now()
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: this.getHeaders(),
      })
    } catch (err: any) {
      this.logRequest(endpoint, 'GET', startTime, 0, err.message)
      throw err
    }
    this.logRequest(endpoint, 'GET', startTime, response.status, response.ok ? undefined : `${response.status}`)
    if (!response.ok) {
      await this.handleErrorResponse(response)
    }
    return response.json()
  }

  private async apiCallWithBody<T>(endpoint: string, body: any): Promise<T> {
    this.throwIfOutage(endpoint, 'POST')
    const startTime = performance.now()
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'POST',
        headers: this.getHeaders('application/json'),
        body: JSON.stringify(body),
      })
    } catch (err: any) {
      this.logRequest(endpoint, 'POST', startTime, 0, err.message)
      throw err
    }
    this.logRequest(endpoint, 'POST', startTime, response.status, response.ok ? undefined : `${response.status}`)
    if (!response.ok) {
      await this.handleErrorResponse(response)
    }
    return response.json()
  }

  private async apiCallWithBodyPut<T>(endpoint: string, body: any): Promise<T> {
    this.throwIfOutage(endpoint, 'PUT')
    const startTime = performance.now()
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'PUT',
        headers: this.getHeaders('application/json'),
        body: JSON.stringify(body),
      })
    } catch (err: any) {
      this.logRequest(endpoint, 'PUT', startTime, 0, err.message)
      throw err
    }
    this.logRequest(endpoint, 'PUT', startTime, response.status, response.ok ? undefined : `${response.status}`)
    if (!response.ok) {
      await this.handleErrorResponse(response)
    }
    return response.json()
  }

  private async apiCallDelete(endpoint: string): Promise<void> {
    this.throwIfOutage(endpoint, 'DELETE')
    const startTime = performance.now()
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: 'DELETE',
        headers: this.getHeaders(),
      })
    } catch (err: any) {
      this.logRequest(endpoint, 'DELETE', startTime, 0, err.message)
      throw err
    }
    this.logRequest(endpoint, 'DELETE', startTime, response.status, response.ok ? undefined : `${response.status}`)
    if (!response.ok) {
      await this.handleErrorResponse(response)
    }
  }

  // User methods
  async whoami(): Promise<{ user_email: string }> {
    return this.apiCall<{ user_email: string }>('/whoami')
  }

  async getSmartPlugStatus(): Promise<{ refreshed_at: string; items: SmartPlugStatus[] }> {
    return this.apiCall<{ refreshed_at: string; items: SmartPlugStatus[] }>('/infra/smart-plugs/status')
  }

  async setSmartPlugPower(request: { key: string; on: boolean; toggle_after?: number | null }): Promise<void> {
    await this.apiCallWithBody<unknown>('/infra/smart-plugs/power', request)
  }

  // SQL query methods
  async listTables(): Promise<TableInfo[]> {
    return this.apiCall<TableInfo[]>('/sql/tables')
  }

  async getTableSchema(tableName: string): Promise<TableSchema> {
    return this.apiCall<TableSchema>(`/sql/tables/${encodeURIComponent(tableName)}/schema`)
  }

  async executeQuery(request: SQLQueryRequest): Promise<SQLQueryResponse> {
    return this.apiCallWithBody<SQLQueryResponse>('/sql/query', request)
  }

  async generateAIQuery(description: string): Promise<AIQueryResponse> {
    return this.apiCallWithBody<AIQueryResponse>('/sql/generate-query', {
      description,
    })
  }

  async createEvalTask(request: EvalTaskCreateRequest): Promise<EvalTask> {
    return this.apiCallWithBody<EvalTask>('/tasks', request)
  }

  async getEvalTasksPaginated(
    page: number,
    pageSize: number,
    filters: TaskFilters
  ): Promise<PaginatedEvalTasksResponse> {
    const params = new URLSearchParams()
    params.append('page', page.toString())
    params.append('page_size', pageSize.toString())

    // Only append non-empty filter values
    if (filters.command?.trim()) params.append('command', filters.command.trim())
    if (filters.user_id?.trim()) params.append('user_id', filters.user_id.trim())
    if (filters.status?.trim()) params.append('status', filters.status.trim())
    if (filters.assignee?.trim()) params.append('assignee', filters.assignee.trim())
    if (filters.git_hash?.trim()) params.append('git_hash', filters.git_hash.trim())
    if (filters.created_at?.trim()) params.append('created_at', filters.created_at.trim())
    if (filters.assigned_at?.trim()) params.append('assigned_at', filters.assigned_at.trim())

    return this.apiCall<PaginatedEvalTasksResponse>(`/tasks/paginated?${params}`)
  }

  async getEvalTask(taskId: number): Promise<EvalTask> {
    return this.apiCall<EvalTask>(`/tasks/${taskId}`)
  }

  async getTaskAttempts(taskId: number): Promise<TaskAttemptsResponse> {
    return this.apiCall<TaskAttemptsResponse>(`/tasks/${taskId}/attempts`)
  }

  getTaskLogUrl(taskId: number, logType: 'output'): string {
    return `${this.baseUrl}/tasks/${taskId}/logs/${logType}`
  }

  // Policy methods
  async getPolicyVersion(policyVersionId: string): Promise<PolicyVersionRow> {
    return this.apiCall<PolicyVersionRow>(`/stats/policy-versions/${policyVersionId}`)
  }

  async getPolicyVersionsBatch(policyVersionIds: string[]): Promise<PolicyVersionRow[]> {
    const chunkSize = 10
    const results: PolicyVersionRow[] = []

    for (let i = 0; i < policyVersionIds.length; i += chunkSize) {
      const chunk = policyVersionIds.slice(i, i + chunkSize)
      const params = chunk.map((id) => `policy_version_ids=${id}`).join('&')
      const response = await this.apiCall<PolicyVersionsResponse>(
        `/stats/policy-versions?${params}&limit=${chunk.length}`
      )
      results.push(...response.entries)
    }

    return results
  }

  async queryEpisodes(request: EpisodeQueryRequest): Promise<EpisodeQueryResponse> {
    return this.apiCallWithBody<EpisodeQueryResponse>('/stats/episodes/query', request)
  }

  async getPolicies(params?: {
    name_exact?: string
    name_fuzzy?: string
    limit?: number
    offset?: number
  }): Promise<PoliciesResponse> {
    const searchParams = new URLSearchParams()
    if (params?.name_exact) searchParams.append('name_exact', params.name_exact)
    if (params?.name_fuzzy) searchParams.append('name_fuzzy', params.name_fuzzy)
    if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString())
    if (params?.offset !== undefined) searchParams.append('offset', params.offset.toString())
    const query = searchParams.toString()
    return this.apiCall<PoliciesResponse>(`/stats/policies${query ? `?${query}` : ''}`)
  }

  async getPolicyVersions(params?: {
    name_exact?: string
    name_fuzzy?: string
    limit?: number
    offset?: number
  }): Promise<PolicyVersionsResponse> {
    const searchParams = new URLSearchParams()
    if (params?.name_exact) searchParams.append('name_exact', params.name_exact)
    if (params?.name_fuzzy) searchParams.append('name_fuzzy', params.name_fuzzy)
    if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString())
    if (params?.offset !== undefined) searchParams.append('offset', params.offset.toString())
    const query = searchParams.toString()
    return this.apiCall<PolicyVersionsResponse>(`/stats/policy-versions${query ? `?${query}` : ''}`)
  }

  async getVersionsForPolicy(
    policyId: string,
    params?: { limit?: number; offset?: number }
  ): Promise<PolicyVersionsResponse> {
    const searchParams = new URLSearchParams()
    searchParams.append('policy_id', policyId)
    if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString())
    if (params?.offset !== undefined) searchParams.append('offset', params.offset.toString())
    return this.apiCall<PolicyVersionsResponse>(`/stats/policy-versions?${searchParams}`)
  }

  async getJobs(params?: {
    job_type?: string
    statuses?: JobStatus[]
    job_id?: string
    policy_version_id?: string
    season_id?: string
    pool_id?: string
    limit?: number
    offset?: number
  }): Promise<JobRequest[]> {
    const searchParams = new URLSearchParams()
    if (params?.job_type) searchParams.append('job_type', params.job_type)
    if (params?.job_id) searchParams.append('job_id', params.job_id)
    if (params?.policy_version_id) searchParams.append('policy_version_id', params.policy_version_id)
    if (params?.season_id) searchParams.append('season_id', params.season_id)
    if (params?.pool_id) searchParams.append('pool_id', params.pool_id)
    if (params?.statuses) {
      for (const status of params.statuses) {
        searchParams.append('statuses', status)
      }
    }
    if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString())
    if (params?.offset !== undefined) searchParams.append('offset', params.offset.toString())
    const query = searchParams.toString()
    return this.apiCall<JobRequest[]>(`/jobs${query ? `?${query}` : ''}`)
  }

  async getJobArtifact(jobId: string, artifactType: string): Promise<string> {
    const endpoint = `/jobs/${jobId}/artifacts/${artifactType}`
    this.throwIfOutage(endpoint, 'GET')
    const startTime = performance.now()
    let response: Response
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: this.getHeaders(),
      })
    } catch (err: any) {
      this.logRequest(endpoint, 'GET', startTime, 0, err.message)
      throw err
    }
    this.logRequest(endpoint, 'GET', startTime, response.status, response.ok ? undefined : `${response.status}`)
    if (!response.ok) {
      await this.handleErrorResponse(response)
    }
    return response.text()
  }

  async getJobEpisodeStats(jobId: string): Promise<EpisodeStatsResponse> {
    return this.apiCall<EpisodeStatsResponse>(`/jobs/${jobId}/episode-stats`)
  }

  // Tournament methods
  async getSeasons(): Promise<SeasonDetail[]> {
    return this.apiCall<SeasonDetail[]>('/tournament/seasons')
  }

  async getSeason(seasonName: string): Promise<SeasonDetail> {
    return this.apiCall<SeasonDetail>(`/tournament/seasons/${encodePathSegment(seasonName)}`)
  }

  async getSeasonVersions(seasonName: string): Promise<SeasonVersionInfo[]> {
    return this.apiCall<SeasonVersionInfo[]>(`/tournament/seasons/${encodePathSegment(seasonName)}/versions`)
  }

  async getSeasonLeaderboard(seasonName: string): Promise<LeaderboardEntry[]> {
    return this.apiCall<LeaderboardEntry[]>(`/tournament/seasons/${encodePathSegment(seasonName)}/leaderboard`)
  }

  async getSeasonPolicies(seasonName: string): Promise<PolicySummary[]> {
    return this.apiCall<PolicySummary[]>(`/tournament/seasons/${encodePathSegment(seasonName)}/policies`)
  }

  async getSeasonMatches(
    seasonName: string,
    params?: {
      limit?: number
      offset?: number
      pool_names?: string[]
      policy_version_ids?: string[]
    }
  ): Promise<SeasonMatchSummary[]> {
    const searchParams = new URLSearchParams()
    if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString())
    if (params?.offset !== undefined) searchParams.append('offset', params.offset.toString())
    if (params?.pool_names) {
      for (const name of params.pool_names) {
        searchParams.append('pool_names', name)
      }
    }
    if (params?.policy_version_ids) {
      for (const id of params.policy_version_ids) {
        searchParams.append('policy_version_ids', id)
      }
    }
    const query = searchParams.toString()
    return this.apiCall<SeasonMatchSummary[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/matches${query ? `?${query}` : ''}`
    )
  }

  async submitToSeason(seasonName: string, policyVersionId: string): Promise<SubmissionResponse> {
    return this.apiCallWithBody<SubmissionResponse>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/submissions`,
      { policy_version_id: policyVersionId }
    )
  }

  async getPolicyMemberships(policyVersionId: string): Promise<MembershipHistoryEntry[]> {
    return this.apiCall<MembershipHistoryEntry[]>(
      `/tournament/policies/${encodeURIComponent(policyVersionId)}/memberships`
    )
  }

  // Dashboard methods
  async getDashboardData(policyVersionId: string): Promise<DashboardResponse> {
    return this.apiCallWithBody<DashboardResponse>(
      `/stats/policies/versions/${encodeURIComponent(policyVersionId)}/dashboard-data`,
      {}
    )
  }

  async getDashboardAnalysis(
    policyVersionId: string,
    summary: Record<string, any>
  ): Promise<DashboardAnalysisResponse> {
    return this.apiCallWithBody<DashboardAnalysisResponse>(
      `/stats/policies/versions/${encodeURIComponent(policyVersionId)}/dashboard-analysis`,
      { summary }
    )
  }
}
