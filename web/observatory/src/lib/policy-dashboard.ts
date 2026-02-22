export type PolicyDashboardTab = string

type PolicyDashboardPathArgs = {
  policyVersionId?: string | null
  tab?: PolicyDashboardTab | null
}

function normalizeDashboardTab(value: string | null | undefined): PolicyDashboardTab | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  if (!trimmed) return undefined
  return trimmed
}

export function buildPolicyDashboardPath({ policyVersionId, tab }: PolicyDashboardPathArgs = {}): string {
  const params = new URLSearchParams()

  if (policyVersionId) {
    const trimmed = policyVersionId.trim()
    if (trimmed) params.set('policyVersionId', trimmed)
  }

  const normalizedTab = normalizeDashboardTab(tab)
  if (normalizedTab) {
    params.set('tab', normalizedTab)
  }

  const query = params.toString()
  return query ? `/policy-dashboard?${query}` : '/policy-dashboard'
}

export function buildEmbeddedPolicyDashboardUrl(
  baseUrl: string,
  { policyVersionId, tab }: PolicyDashboardPathArgs = {}
): string {
  const url = new URL(baseUrl)

  if (policyVersionId) {
    const trimmed = policyVersionId.trim()
    if (trimmed) url.searchParams.set('policyVersionId', trimmed)
  }

  const normalizedTab = normalizeDashboardTab(tab)
  if (normalizedTab) {
    url.searchParams.set('tab', normalizedTab)
  }

  return url.toString()
}

export function parsePolicyDashboardTab(value: string | null | undefined): PolicyDashboardTab | undefined {
  return normalizeDashboardTab(value)
}
