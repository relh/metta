export function matchesRoute(
  seasonName: string,
  params: { pool_names?: string[]; policy_version_ids?: string[]; match_page?: number }
) {
  const searchParams = new URLSearchParams()
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
  return `/tournament/${seasonName}/matches?${searchParams.toString()}`
}
