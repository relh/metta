import { notFound, redirect } from "next/navigation";

import type {
  AIQueryResponse,
  EpisodeQueryRequest,
  EpisodeQueryResponse,
  EpisodeStatsResponse,
  JobRequest,
  JobStatus,
  LeaderboardEntry,
  MembershipHistoryEntry,
  PoliciesResponse,
  PolicySummary,
  PolicyVersionRow,
  PolicyVersionsResponse,
  ProgressResponse,
  ScorePoliciesLeaderboardEntry,
  SeasonDetail,
  SeasonLeaderboardQuery,
  SeasonMatchSummary,
  SeasonSummary,
  SeasonTeamsQuery,
  SeasonVersionInfo,
  ServiceAccountCreateResponse,
  ServiceAccountResponseBase,
  SmartPlugStatus,
  SQLQueryRequest,
  SQLQueryResponse,
  StageLeaderboardQuery,
  StageLeaderboardType,
  StageStats,
  SubmissionResponse,
  TableInfo,
  TableSchema,
  TeamSummary,
} from "@observatory/lib/api";
import { isOutageSimulated } from "@observatory/lib/debug/simulate-outage";
import { policiesRoute } from "@observatory/lib/routes";

// Re-export generated API types so existing `import { X } from '@/lib/repo'`
// statements continue to work.
export type {
  AgentStatsDetail,
  AIQueryRequest,
  AIQueryResponse,
  EpisodePolicyStat,
  EpisodeQueryRequest,
  EpisodeQueryResponse,
  EpisodeStatsResponse,
  EpisodeWithTags,
  JobEpisodeInfo,
  JobMatchInfo,
  JobPolicyVersionSummary,
  JobRequest,
  JobStatus,
  LeaderboardEntry,
  MembershipHistoryEntry,
  PoliciesResponse,
  PolicyRow,
  PolicyStatsDetail,
  PolicySummary,
  PolicyVersionRow,
  PolicyVersionsResponse,
  PolicyVersionSummary,
  PoolInfo,
  PoolMembership,
  ProgressResponse,
  ScorePoliciesLeaderboardEntry,
  SeasonDetail,
  SeasonLeaderboardQuery,
  SeasonMatchPlayerSummary,
  SeasonMatchSummary,
  SeasonSummary,
  SeasonTeamsQuery,
  SeasonVersionInfo,
  ServiceAccountCreateResponse,
  ServiceAccountResponseBase,
  SmartPlugStatus,
  SQLQueryRequest,
  SQLQueryResponse,
  StageLeaderboardQuery,
  StageLeaderboardType,
  StageStats,
  SubmissionResponse,
  TableInfo,
  TableSchema,
  TeamCogSummary,
  TeamSummary,
  UserRow,
} from "@observatory/lib/api";

// ── Frontend-only types (not from the API spec) ─────────────────────────

const decodePathSegment = (value: string) => {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
};

const encodePathSegment = (value: string) =>
  encodeURIComponent(decodePathSegment(value));

export type MatchStatus =
  | "pending"
  | "scheduled"
  | "running"
  | "completed"
  | "failed";

export const ALL_JOB_STATUSES = [
  "pending",
  "dispatched",
  "running",
  "completed",
  "failed",
] as const;

export type RequestLogEntry = {
  id: string;
  endpoint: string;
  method: string;
  durationMs: number;
  status: number;
  error?: string;
  source: "server" | "client";
  timestamp: number;
};

export type OnRequestCallback = (entry: RequestLogEntry) => void;

let nextRequestId = 0;

export class Repo {
  constructor(
    public baseUrl: string = "http://localhost:8000",
    private authHeaders: Record<string, string> | null = null,
    private onRequest?: OnRequestCallback,
    private actAsExternal: boolean = false,
  ) {}

  private getHeaders(contentType?: string): Record<string, string> {
    const headers: Record<string, string> = { ...this.authHeaders };

    if (contentType) {
      headers["Content-Type"] = contentType;
    }

    if (this.actAsExternal) {
      headers["X-Act-As-External"] = "true";
    }

    return headers;
  }

  private logRequest(
    endpoint: string,
    method: string,
    startTime: number,
    status: number,
    error?: string,
  ) {
    if (!this.onRequest) return;
    this.onRequest({
      id: `req-${nextRequestId++}-${Date.now()}`,
      endpoint,
      method,
      durationMs: Math.round(performance.now() - startTime),
      status,
      error,
      source: typeof window === "undefined" ? "server" : "client",
      timestamp: Date.now(),
    });
  }

  private throwIfOutage(endpoint: string, method: string): void {
    if (!isOutageSimulated()) return;
    const startTime = performance.now();
    this.logRequest(endpoint, method, startTime, 0, "Simulated API outage");
    throw new Error("Simulated API outage");
  }

  private async handleErrorResponse(response: Response): Promise<never> {
    if (response.status === 401) {
      if (typeof window === "undefined") {
        redirect(policiesRoute());
      } else {
        window.location.href = policiesRoute();
        throw new Error("Session expired, redirecting to login...");
      }
    }
    if (response.status === 404) {
      if (typeof window === "undefined") {
        notFound();
      }
      throw new Error("Not found");
    }
    if (response.status === 503) {
      throw new Error("Service temporarily unavailable — please try again");
    }
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = body.detail;
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(
      detail
        ? JSON.stringify(detail, null, 2)
        : `API call failed: ${response.status} ${response.statusText}`,
    );
  }

  private async apiCall<T>(endpoint: string): Promise<T> {
    this.throwIfOutage(endpoint, "GET");
    const startTime = performance.now();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: this.getHeaders(),
      });
    } catch (err: any) {
      this.logRequest(endpoint, "GET", startTime, 0, err.message);
      throw err;
    }
    this.logRequest(
      endpoint,
      "GET",
      startTime,
      response.status,
      response.ok ? undefined : `${response.status}`,
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  private async apiCallWithBody<T>(endpoint: string, body: any): Promise<T> {
    this.throwIfOutage(endpoint, "POST");
    const startTime = performance.now();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: "POST",
        headers: this.getHeaders("application/json"),
        body: JSON.stringify(body),
      });
    } catch (err: any) {
      this.logRequest(endpoint, "POST", startTime, 0, err.message);
      throw err;
    }
    this.logRequest(
      endpoint,
      "POST",
      startTime,
      response.status,
      response.ok ? undefined : `${response.status}`,
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.json();
  }

  private async apiCallDelete(endpoint: string): Promise<void> {
    this.throwIfOutage(endpoint, "DELETE");
    const startTime = performance.now();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        method: "DELETE",
        headers: this.getHeaders(),
      });
    } catch (err: any) {
      this.logRequest(endpoint, "DELETE", startTime, 0, err.message);
      throw err;
    }
    this.logRequest(
      endpoint,
      "DELETE",
      startTime,
      response.status,
      response.ok ? undefined : `${response.status}`,
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
  }

  // Service account methods
  async listServiceAccounts(): Promise<ServiceAccountResponseBase[]> {
    return this.apiCall<ServiceAccountResponseBase[]>("/service-accounts");
  }

  async createServiceAccount(
    name: string,
  ): Promise<ServiceAccountCreateResponse> {
    return this.apiCallWithBody<ServiceAccountCreateResponse>(
      "/service-accounts",
      { name },
    );
  }

  async deleteServiceAccount(id: string): Promise<void> {
    return this.apiCallDelete(`/service-accounts/${id}`);
  }

  // User methods
  async whoami(): Promise<{
    user_email: string;
    is_softmax_team_member: boolean;
    is_softmax_admin: boolean;
  }> {
    return this.apiCall<{
      user_email: string;
      is_softmax_team_member: boolean;
      is_softmax_admin: boolean;
    }>("/whoami");
  }

  async getAdminUsersScaffold(): Promise<{
    message: string;
  }> {
    return this.apiCall<{
      message: string;
    }>("/admin/users");
  }

  async getSmartPlugStatus(): Promise<{
    refreshed_at: string;
    items: SmartPlugStatus[];
  }> {
    return this.apiCall<{ refreshed_at: string; items: SmartPlugStatus[] }>(
      "/infra/smart-plugs/status",
    );
  }

  async setSmartPlugPower(request: {
    key: string;
    on: boolean;
    toggle_after?: number | null;
  }): Promise<void> {
    await this.apiCallWithBody<unknown>("/infra/smart-plugs/power", request);
  }

  // SQL query methods
  async listTables(): Promise<TableInfo[]> {
    return this.apiCall<TableInfo[]>("/sql/tables");
  }

  async getTableSchema(tableName: string): Promise<TableSchema> {
    return this.apiCall<TableSchema>(
      `/sql/tables/${encodeURIComponent(tableName)}/schema`,
    );
  }

  async executeQuery(request: SQLQueryRequest): Promise<SQLQueryResponse> {
    return this.apiCallWithBody<SQLQueryResponse>("/sql/query", request);
  }

  async generateAIQuery(description: string): Promise<AIQueryResponse> {
    return this.apiCallWithBody<AIQueryResponse>("/sql/generate-query", {
      description,
    });
  }

  // Policy methods
  async getPolicyVersion(policyVersionId: string): Promise<PolicyVersionRow> {
    return this.apiCall<PolicyVersionRow>(
      `/stats/policy-versions/${policyVersionId}`,
    );
  }

  async getPolicyVersionsBatch(
    policyVersionIds: string[],
  ): Promise<PolicyVersionRow[]> {
    const chunkSize = 10;
    const results: PolicyVersionRow[] = [];

    for (let i = 0; i < policyVersionIds.length; i += chunkSize) {
      const chunk = policyVersionIds.slice(i, i + chunkSize);
      const params = chunk.map((id) => `policy_version_ids=${id}`).join("&");
      const response = await this.apiCall<PolicyVersionsResponse>(
        `/stats/policy-versions?${params}&limit=${chunk.length}`,
      );
      results.push(...response.entries);
    }

    return results;
  }

  async queryEpisodes(
    request: EpisodeQueryRequest,
  ): Promise<EpisodeQueryResponse> {
    return this.apiCallWithBody<EpisodeQueryResponse>(
      "/stats/episodes/query",
      request,
    );
  }

  async getPolicies(params?: {
    name_exact?: string;
    name_fuzzy?: string;
    limit?: number;
    offset?: number;
  }): Promise<PoliciesResponse> {
    const searchParams = new URLSearchParams();
    if (params?.name_exact)
      searchParams.append("name_exact", params.name_exact);
    if (params?.name_fuzzy)
      searchParams.append("name_fuzzy", params.name_fuzzy);
    if (params?.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params?.offset !== undefined)
      searchParams.append("offset", params.offset.toString());
    const query = searchParams.toString();
    return this.apiCall<PoliciesResponse>(
      `/stats/policies${query ? `?${query}` : ""}`,
    );
  }

  async getPolicyVersions(params?: {
    name_exact?: string;
    name_fuzzy?: string;
    limit?: number;
    offset?: number;
  }): Promise<PolicyVersionsResponse> {
    const searchParams = new URLSearchParams();
    if (params?.name_exact)
      searchParams.append("name_exact", params.name_exact);
    if (params?.name_fuzzy)
      searchParams.append("name_fuzzy", params.name_fuzzy);
    if (params?.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params?.offset !== undefined)
      searchParams.append("offset", params.offset.toString());
    const query = searchParams.toString();
    return this.apiCall<PolicyVersionsResponse>(
      `/stats/policy-versions${query ? `?${query}` : ""}`,
    );
  }

  async getVersionsForPolicy(
    policyId: string,
    params?: { limit?: number; offset?: number },
  ): Promise<PolicyVersionsResponse> {
    const searchParams = new URLSearchParams();
    searchParams.append("policy_id", policyId);
    if (params?.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params?.offset !== undefined)
      searchParams.append("offset", params.offset.toString());
    return this.apiCall<PolicyVersionsResponse>(
      `/stats/policy-versions?${searchParams}`,
    );
  }

  async getJobs(params?: {
    job_type?: string;
    statuses?: JobStatus[];
    job_id?: string;
    policy_version_id?: string;
    season_id?: string;
    pool_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<JobRequest[]> {
    const searchParams = new URLSearchParams();
    if (params?.job_type) searchParams.append("job_type", params.job_type);
    if (params?.job_id) searchParams.append("job_id", params.job_id);
    if (params?.policy_version_id)
      searchParams.append("policy_version_id", params.policy_version_id);
    if (params?.season_id) searchParams.append("season_id", params.season_id);
    if (params?.pool_id) searchParams.append("pool_id", params.pool_id);
    if (params?.statuses) {
      for (const status of params.statuses) {
        searchParams.append("statuses", status);
      }
    }
    if (params?.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params?.offset !== undefined)
      searchParams.append("offset", params.offset.toString());
    const query = searchParams.toString();
    return this.apiCall<JobRequest[]>(`/jobs${query ? `?${query}` : ""}`);
  }

  async getJobArtifact(jobId: string, artifactType: string): Promise<string> {
    const endpoint = `/jobs/${jobId}/artifacts/${artifactType}`;
    this.throwIfOutage(endpoint, "GET");
    const startTime = performance.now();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: this.getHeaders(),
      });
    } catch (err: any) {
      this.logRequest(endpoint, "GET", startTime, 0, err.message);
      throw err;
    }
    this.logRequest(
      endpoint,
      "GET",
      startTime,
      response.status,
      response.ok ? undefined : `${response.status}`,
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.text();
  }

  async getJobEpisodeStats(jobId: string): Promise<EpisodeStatsResponse> {
    return this.apiCall<EpisodeStatsResponse>(`/jobs/${jobId}/episode-stats`);
  }

  // Policy logs use a separate endpoint from getJobArtifact because they require an
  // agent index parameter. See job_artifacts.py for backend unification notes.
  async listJobPolicyLogs(jobId: string): Promise<string[]> {
    return this.apiCall<string[]>(`/jobs/${jobId}/policy-logs`);
  }

  async getJobPolicyLogContent(
    jobId: string,
    agentIdx: number,
  ): Promise<string> {
    const endpoint = `/jobs/${jobId}/policy-logs/${agentIdx}`;
    this.throwIfOutage(endpoint, "GET");
    const startTime = performance.now();
    let response: Response;
    try {
      response = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: this.getHeaders(),
      });
    } catch (err: any) {
      this.logRequest(endpoint, "GET", startTime, 0, err.message);
      throw err;
    }
    this.logRequest(
      endpoint,
      "GET",
      startTime,
      response.status,
      response.ok ? undefined : `${response.status}`,
    );
    if (!response.ok) {
      await this.handleErrorResponse(response);
    }
    return response.text();
  }

  // Tournament methods
  async getSeasons(): Promise<SeasonSummary[]> {
    return this.apiCall<SeasonSummary[]>("/tournament/seasons");
  }

  async getSeason(seasonName: string): Promise<SeasonDetail> {
    return this.apiCall<SeasonDetail>(
      `/tournament/seasons/${encodePathSegment(seasonName)}`,
    );
  }

  async getSeasonVersions(seasonName: string): Promise<SeasonVersionInfo[]> {
    return this.apiCall<SeasonVersionInfo[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/versions`,
    );
  }

  async getSeasonLeaderboard(
    seasonName: string,
    params?: SeasonLeaderboardQuery,
  ): Promise<LeaderboardEntry[]> {
    const searchParams = new URLSearchParams();
    if (params?.pool) searchParams.append("pool", params.pool);
    const query = searchParams.toString();
    return this.apiCall<LeaderboardEntry[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/leaderboard${query ? `?${query}` : ""}`,
    );
  }

  async getSeasonStageLeaderboard(
    seasonName: string,
    leaderboardType: "policy",
    poolName: string,
    params?: StageLeaderboardQuery,
  ): Promise<LeaderboardEntry[]>;
  async getSeasonStageLeaderboard(
    seasonName: string,
    leaderboardType: "team",
    poolName: string,
    params?: StageLeaderboardQuery,
  ): Promise<TeamSummary[]>;
  async getSeasonStageLeaderboard(
    seasonName: string,
    leaderboardType: "score-policies",
    poolName: string,
    params?: StageLeaderboardQuery,
  ): Promise<ScorePoliciesLeaderboardEntry[]>;
  async getSeasonStageLeaderboard(
    seasonName: string,
    leaderboardType: StageLeaderboardType,
    poolName: string,
    params?: StageLeaderboardQuery,
  ): Promise<
    LeaderboardEntry[] | TeamSummary[] | ScorePoliciesLeaderboardEntry[]
  > {
    const query = "";
    return this.apiCall<
      LeaderboardEntry[] | TeamSummary[] | ScorePoliciesLeaderboardEntry[]
    >(
      `/tournament/seasons/${encodePathSegment(seasonName)}/leaderboard/${encodePathSegment(leaderboardType)}/${encodePathSegment(poolName)}${query ? `?${query}` : ""}`,
    );
  }

  async getSeasonPolicies(seasonName: string): Promise<PolicySummary[]> {
    return this.apiCall<PolicySummary[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/policies`,
    );
  }

  async getSeasonMatches(
    seasonName: string,
    params?: {
      limit?: number;
      offset?: number;
      pool_names?: string[];
      policy_version_ids?: string[];
    },
  ): Promise<SeasonMatchSummary[]> {
    const searchParams = new URLSearchParams();
    if (params?.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params?.offset !== undefined)
      searchParams.append("offset", params.offset.toString());
    if (params?.pool_names) {
      for (const name of params.pool_names) {
        searchParams.append("pool_names", name);
      }
    }
    if (params?.policy_version_ids) {
      for (const id of params.policy_version_ids) {
        searchParams.append("policy_version_ids", id);
      }
    }
    const query = searchParams.toString();
    return this.apiCall<SeasonMatchSummary[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/matches${query ? `?${query}` : ""}`,
    );
  }

  async submitToSeason(
    seasonName: string,
    policyVersionId: string,
  ): Promise<SubmissionResponse> {
    return this.apiCallWithBody<SubmissionResponse>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/submissions`,
      { policy_version_id: policyVersionId },
    );
  }

  async getPolicyMemberships(
    policyVersionId: string,
  ): Promise<MembershipHistoryEntry[]> {
    return this.apiCall<MembershipHistoryEntry[]>(
      `/tournament/policies/${encodeURIComponent(policyVersionId)}/memberships`,
    );
  }

  async getSeasonProgress(seasonName: string): Promise<ProgressResponse> {
    return this.apiCall<ProgressResponse>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/progress`,
    );
  }

  async startSeason(seasonName: string): Promise<ProgressResponse> {
    return this.apiCallWithBody<ProgressResponse>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/start`,
      {},
    );
  }

  async getAvailableCompatVersions(): Promise<string[]> {
    return this.apiCall<string[]>("/tournament/compat-versions");
  }

  async rollSeason(
    seasonId: string,
    compatVersion: string,
    migrateActivePlayers = false,
  ): Promise<SeasonSummary> {
    return this.apiCallWithBody<SeasonSummary>(
      `/tournament/seasons/${encodePathSegment(seasonId)}/roll`,
      {
        compat_version: compatVersion,
        migrate_active_players: migrateActivePlayers,
      },
    );
  }

  async updateCurrentSeasonCompatVersion(
    seasonId: string,
    compatVersion: string,
  ): Promise<SeasonSummary> {
    return this.apiCallWithBody<SeasonSummary>(
      `/tournament/seasons/${encodePathSegment(seasonId)}/update-current-season-compat-version`,
      { compat_version: compatVersion },
    );
  }

  async getSeasonStages(seasonName: string): Promise<StageStats[]> {
    return this.apiCall<StageStats[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/stages`,
    );
  }

  async getSeasonTeams(
    seasonName: string,
    params?: SeasonTeamsQuery,
  ): Promise<TeamSummary[]> {
    const searchParams = new URLSearchParams();
    if (params?.limit !== undefined)
      searchParams.append("limit", params.limit.toString());
    if (params?.offset !== undefined)
      searchParams.append("offset", params.offset.toString());
    if (params?.pool_name) searchParams.append("pool_name", params.pool_name);
    if (params?.eliminated !== undefined && params.eliminated !== null) {
      searchParams.append("eliminated", params.eliminated.toString());
    }
    if (params?.policy_version_id)
      searchParams.append("policy_version_id", params.policy_version_id);
    const query = searchParams.toString();
    return this.apiCall<TeamSummary[]>(
      `/tournament/seasons/${encodePathSegment(seasonName)}/teams${query ? `?${query}` : ""}`,
    );
  }
}
