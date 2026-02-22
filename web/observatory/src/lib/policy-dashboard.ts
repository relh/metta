export type PolicyDashboardTab =
  | 'overview'
  | 'episodes'
  | 'opponents'
  | 'health'
  | 'roles'
  | 'capabilities'
  | 'cogames_diagnose'

const POLICY_DASHBOARD_TABS: PolicyDashboardTab[] = [
  'overview',
  'episodes',
  'opponents',
  'health',
  'roles',
  'capabilities',
  'cogames_diagnose',
]

type PolicyDashboardPathArgs = {
  policyVersionId?: string | null
  tab?: PolicyDashboardTab
}

export function buildPolicyDashboardPath({ policyVersionId, tab }: PolicyDashboardPathArgs = {}): string {
  const params = new URLSearchParams()

  if (policyVersionId) {
    const trimmed = policyVersionId.trim()
    if (trimmed) params.set('policyVersionId', trimmed)
  }

  if (tab) {
    params.set('tab', tab)
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

  if (tab) {
    url.searchParams.set('tab', tab)
  }

  return url.toString()
}

export function parsePolicyDashboardTab(value: string | null | undefined): PolicyDashboardTab | undefined {
  if (!value) return undefined
  return POLICY_DASHBOARD_TABS.find((tab) => tab === value)
}
