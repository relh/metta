type SeasonTabMode = 'freeplay' | 'tournament'

export function policiesRoute() {
  return '/policies'
}

export function policyRoute(policyId: string) {
  return `/policies/${policyId}`
}

export function policyVersionRoute(policyVersionId: string) {
  return `/policies/versions/${policyVersionId}`
}

export function policyDashboardRoute(params?: { policyVersionId?: string | null; tab?: string | null }) {
  const searchParams = new URLSearchParams()
  if (params?.policyVersionId) {
    const trimmed = params.policyVersionId.trim()
    if (trimmed) searchParams.set('policyVersionId', trimmed)
  }
  if (params?.tab) {
    const trimmed = params.tab.trim()
    if (trimmed) searchParams.set('tab', trimmed)
  }
  const query = searchParams.toString()
  return query ? `/policy-dashboard?${query}` : '/policy-dashboard'
}

export function tournamentRoute(params?: { mode?: SeasonTabMode }) {
  const searchParams = new URLSearchParams()
  if (params?.mode) {
    searchParams.set('mode', params.mode)
  }
  const query = searchParams.toString()
  return query ? `/tournament?${query}` : '/tournament'
}

export function seasonRoute(seasonName: string, params?: { mode?: SeasonTabMode }) {
  const searchParams = new URLSearchParams()
  if (params?.mode) {
    searchParams.set('mode', params.mode)
  }
  const query = searchParams.toString()
  return query ? `/tournament/${seasonName}?${query}` : `/tournament/${seasonName}`
}

export function seasonLeaderboardRoute(seasonName: string, params?: { mode?: SeasonTabMode }) {
  const searchParams = new URLSearchParams()
  searchParams.set('view', 'leaderboard')
  if (params?.mode) {
    searchParams.set('mode', params.mode)
  }
  return `/tournament/${seasonName}?${searchParams.toString()}`
}

export function seasonPlayersRoute(seasonName: string, params?: { stage?: string; mode?: SeasonTabMode }) {
  const searchParams = new URLSearchParams()
  if (params?.stage) searchParams.set('stage', params.stage)
  if (params?.mode) searchParams.set('mode', params.mode)
  const query = searchParams.toString()
  return query ? `/tournament/${seasonName}/players?${query}` : `/tournament/${seasonName}/players`
}

export function matchesRoute(
  seasonName: string,
  params: { stage?: string; pool_names?: string[]; policy_version_ids?: string[]; match_page?: number }
) {
  const searchParams = new URLSearchParams()
  if (params.stage) {
    searchParams.append('stage', params.stage)
  }
  if (params.pool_names) {
    for (const poolName of params.pool_names) {
      searchParams.append('pool_names', poolName)
    }
  }
  if (params.policy_version_ids) {
    for (const policyVersionId of params.policy_version_ids) {
      searchParams.append('policy_version_ids', policyVersionId)
    }
  }
  if (params.match_page !== undefined) {
    searchParams.append('match_page', params.match_page.toString())
  }
  const query = searchParams.toString()
  return query ? `/tournament/${seasonName}/matches?${query}` : `/tournament/${seasonName}/matches`
}

export function seasonTeamsRoute(seasonName: string) {
  return `/tournament/${seasonName}/teams`
}

export function episodeRoute(episodeId: string) {
  return `/episodes/${episodeId}`
}

export function episodeJobsRoute(params?: { jobId?: string }) {
  if (params?.jobId) return `/episode-jobs?jobId=${params.jobId}`
  return '/episode-jobs'
}

export function evalTasksRoute() {
  return '/eval-tasks'
}

export function sqlQueryRoute() {
  return '/sql-query'
}

export function smartPlugsRoute() {
  return '/infra/smart-plugs'
}

export function serviceAccountsRoute() {
  return '/service-accounts'
}

export function authLoginRoute() {
  return '/auth/login'
}
