type SeasonTabMode = "freeplay" | "tournament";

export function policiesRoute() {
  return "/observatory/policies";
}

export function policyRoute(policyId: string) {
  return `/observatory/policies/${policyId}`;
}

export function policyVersionRoute(policyVersionId: string) {
  return `/observatory/policies/versions/${policyVersionId}`;
}

export function policyDashboardRoute(params?: {
  policyVersionId?: string | null;
  tab?: string | null;
}) {
  const searchParams = new URLSearchParams();
  if (params?.policyVersionId) {
    const trimmed = params.policyVersionId.trim();
    if (trimmed) searchParams.set("policyVersionId", trimmed);
  }
  if (params?.tab) {
    const trimmed = params.tab.trim();
    if (trimmed) searchParams.set("tab", trimmed);
  }
  const query = searchParams.toString();
  return query
    ? `/observatory/policy-dashboard?${query}`
    : "/observatory/policy-dashboard";
}

export function diagnoseRoute(runId?: string | null) {
  if (!runId) return "/observatory/diagnose";
  const trimmed = runId.trim();
  if (!trimmed) return "/observatory/diagnose";
  return `/observatory/diagnose/${encodeURIComponent(trimmed)}`;
}

export function pantheonRoute() {
  return "/observatory/pantheon";
}

export function tournamentRoute(params?: { mode?: SeasonTabMode }) {
  const searchParams = new URLSearchParams();
  if (params?.mode) {
    searchParams.set("mode", params.mode);
  }
  const query = searchParams.toString();
  return query ? `/observatory/tournament?${query}` : "/observatory/tournament";
}

export function seasonRoute(
  seasonName: string,
  params?: { mode?: SeasonTabMode },
) {
  const searchParams = new URLSearchParams();
  if (params?.mode) {
    searchParams.set("mode", params.mode);
  }
  const query = searchParams.toString();
  return query
    ? `/observatory/tournament/${seasonName}?${query}`
    : `/observatory/tournament/${seasonName}`;
}

export function seasonLeaderboardRoute(
  seasonName: string,
  params?: { mode?: SeasonTabMode },
) {
  const searchParams = new URLSearchParams();
  searchParams.set("view", "leaderboard");
  if (params?.mode) {
    searchParams.set("mode", params.mode);
  }
  return `/observatory/tournament/${seasonName}?${searchParams.toString()}`;
}

export function seasonPlayersRoute(
  seasonName: string,
  params?: { stage?: string; mode?: SeasonTabMode },
) {
  const searchParams = new URLSearchParams();
  if (params?.stage) searchParams.set("stage", params.stage);
  if (params?.mode) searchParams.set("mode", params.mode);
  const query = searchParams.toString();
  return query
    ? `/observatory/tournament/${seasonName}/players?${query}`
    : `/observatory/tournament/${seasonName}/players`;
}

export function matchesRoute(
  seasonName: string,
  params: {
    stage?: string;
    pool_names?: string[];
    policy_version_ids?: string[];
    match_page?: number;
  },
) {
  const searchParams = new URLSearchParams();
  if (params.stage) {
    searchParams.append("stage", params.stage);
  }
  if (params.pool_names) {
    for (const poolName of params.pool_names) {
      searchParams.append("pool_names", poolName);
    }
  }
  if (params.policy_version_ids) {
    for (const policyVersionId of params.policy_version_ids) {
      searchParams.append("policy_version_ids", policyVersionId);
    }
  }
  if (params.match_page !== undefined) {
    searchParams.append("match_page", params.match_page.toString());
  }
  const query = searchParams.toString();
  return query
    ? `/observatory/tournament/${seasonName}/matches?${query}`
    : `/observatory/tournament/${seasonName}/matches`;
}

export function seasonTeamsRoute(seasonName: string) {
  return `/observatory/tournament/${seasonName}/teams`;
}

export function episodeRoute(episodeId: string) {
  return `/observatory/episodes/${episodeId}`;
}

export function episodeJobsRoute(params?: { jobId?: string }) {
  if (params?.jobId) return `/observatory/episode-jobs?jobId=${params.jobId}`;
  return "/observatory/episode-jobs";
}

export function evalTasksRoute() {
  return "/observatory/eval-tasks";
}

export function trainBoardRoute() {
  return "/observatory/train-board";
}

export function chatpropRoute() {
  return "/observatory/chatprop";
}

export function bardoRoute() {
  return "/observatory/bardo";
}

export function sqlQueryRoute() {
  return "/observatory/sql-query";
}

export function smartPlugsRoute() {
  return "/observatory/infra/smart-plugs";
}

export function serviceAccountsRoute() {
  return "/observatory/service-accounts";
}

export function authLoginRoute() {
  return "/observatory/auth/login";
}
