import { notFound, redirect } from 'next/navigation'

const decodePathSegment = (value: string) => {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

const encodePathSegment = (value: string) => encodeURIComponent(decodePathSegment(value))

export type EvalTaskCreateRequest = {
  command: string
  git_hash: string | null
  attributes: Record<string, any>
}

export type TaskStatus = 'unprocessed' | 'running' | 'canceled' | 'done' | 'error' | 'system_error'

type TaskStatusMixin = {
  status: TaskStatus
  status_details: Record<string, any> | null
}

export type UserRow = {
  id: string
  name: string | null
  email: string | null
  is_softmax_team_member: boolean | null
}

type Ownable = {
  user_id: string
  user: UserRow | null
}

export type EvalTask = Ownable & {
  // eval_tasks table columns
  id: number
  command: string
  data_uri: string | null
  git_hash: string | null
  attributes: Record<string, any>
  created_at: string
  is_finished: boolean
  latest_attempt_id: number | null

  // Latest attempt columns (from JOIN)
  attempt_number: number | null
  assigned_at: string | null
  assignee: string | null
  started_at: string | null
  finished_at: string | null
  output_log_path: string | null
} & TaskStatusMixin

export type TaskAttempt = {
  id: number
  task_id: number
  attempt_number: number
  assigned_at: string | null
  assignee: string | null
  started_at: string | null
  finished_at: string | null
  output_log_path: string | null
} & TaskStatusMixin

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

export type TaskFilters = {
  command?: string
  user_id?: string
  status?: string
  assignee?: string
  git_hash?: string
  created_at?: string
  assigned_at?: string
}

// Policy-based scorecard types
export type PublicPolicyVersionRow = Ownable & {
  id: string
  policy_id: string
  created_at: string
  policy_created_at: string
  name: string
  version: number
  tags: Record<string, string>
  version_count?: number
}

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

export type PolicyVersionWithName = {
  id: string
  policy_id: string
  version: number
  name: string
  created_at: string
}

export type EpisodeQueryRequest = {
  primary_policy_version_ids?: string[]
  tag_filters?: Record<string, string[] | null>
  limit?: number | null
  offset?: number
  episode_ids?: string[]
}

export type EpisodeQueryResponse = {
  episodes: EpisodeWithTags[]
}

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

export const ALL_JOB_STATUSES = ['pending', 'dispatched', 'running', 'completed', 'failed'] as const

export type JobStatus = (typeof ALL_JOB_STATUSES)[number]

export type MatchStatus = 'pending' | 'scheduled' | 'running' | 'completed' | 'failed'

export type PoolInfo = {
  id: string | null
  name: string
  description: string
  config_id: string | null
}

export type SeasonDetail = {
  id: string
  name: string
  version: number
  canonical: boolean
  summary: string
  entry_pool: string | null
  leaderboard_pool: string | null
  is_default: boolean
  pools: PoolInfo[]
}

export type SeasonVersionInfo = {
  version: number
  canonical: boolean
  disabled_at: string | null
  created_at: string
}

export type PolicyVersionSummary = {
  id: string
  name: string | null
  version: number | null
}

export type JobPolicyVersionSummary = {
  position: number
  policy: PolicyVersionSummary
}

export type LeaderboardEntry = {
  rank: number
  policy: PolicyVersionSummary
  score: number
  matches: number
}

export type SubmissionResponse = {
  pools: string[]
}

export type PoolMembership = {
  pool_name: string
  active: boolean
  completed: number
  failed: number
  pending: number
}

export type PolicySummary = {
  policy: PolicyVersionSummary
  pools: PoolMembership[]
  entered_at: string
}

export type SeasonMatchPlayerSummary = {
  policy: PolicyVersionSummary
  policy_index: number
  score: number | null
}

export type SeasonMatchSummary = {
  id: string
  pool_name: string
  status: MatchStatus
  assignments: number[]
  players: SeasonMatchPlayerSummary[]
  job_id: string | null
  episode_id: string | null
  created_at: string
}

export type MembershipHistoryEntry = {
  season_name: string
  season_version: number | null
  pool_name: string
  action: string
  notes: string | null
  created_at: string
}

export type EpisodePolicyStat = {
  policy_version_id: string
  num_agents: number
  avg_reward: number | null
}

export type JobEpisodeInfo = {
  replay_url: string | null
  attributes: Record<string, any> | null
  policy_stats: EpisodePolicyStat[]
}

export type JobMatchInfo = {
  pool_name: string | null
  season_name: string | null
}

export type JobRequest = Ownable & {
  id: string
  job_type: string
  job: Record<string, any>
  status: JobStatus
  worker: string | null
  result: Record<string, any> | null
  error: string | null
  error_type?: string | null
  created_at: string
  dispatched_at: string | null
  running_at: string | null
  completed_at: string | null
  policy_versions: JobPolicyVersionSummary[]
  episode: JobEpisodeInfo | null
  match: JobMatchInfo | null
}

export type PolicyRow = Ownable & {
  id: string
  name: string
  created_at: string
  attributes: Record<string, any>
  version_count: number
}

export type PoliciesResponse = {
  entries: PolicyRow[]
  total_count: number
}

export type PolicyVersionsResponse = {
  entries: PublicPolicyVersionRow[]
  total_count: number
}

export type SmartPlugStatus = {
  key: string
  label: string
  alias?: string | null
  online?: boolean | null
  is_on?: boolean | null
  apower?: number | null
}

export type AgentStatsDetail = {
  agent_id: number
  reward: number
  metrics: Record<string, number>
}

export type PolicyStatsDetail = {
  position: number
  policy_version_id: string | null
  policy_name: string | null
  policy_version: number | null
  num_agents: number
  avg_metrics: Record<string, number>
  avg_reward: number
  agents: AgentStatsDetail[]
}

export type EpisodeStatsResponse = {
  game_stats: Record<string, number>
  policy_stats: PolicyStatsDetail[]
  steps: number | null
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
  async getPolicyVersion(policyVersionId: string): Promise<PolicyVersionWithName> {
    return this.apiCall<PolicyVersionWithName>(`/stats/policies/versions/${policyVersionId}`)
  }

  async getPolicyVersionsBatch(policyVersionIds: string[]): Promise<PublicPolicyVersionRow[]> {
    const chunkSize = 10
    const results: PublicPolicyVersionRow[] = []

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
    if (params?.limit !== undefined) searchParams.append('limit', params.limit.toString())
    if (params?.offset !== undefined) searchParams.append('offset', params.offset.toString())
    const query = searchParams.toString()
    return this.apiCall<PolicyVersionsResponse>(`/stats/policies/${policyId}/versions${query ? `?${query}` : ''}`)
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
}
