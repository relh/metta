import { config } from '@/config'
import { buildEmbeddedPolicyDashboardUrl, parsePolicyDashboardTab } from '@/lib/policy-dashboard'

import { PolicyDashboardEmbed } from './PolicyDashboardEmbed'

type PolicyDashboardSearchParams = {
  policyVersionId?: string | string[]
  tab?: string | string[]
}

export default async function PolicyDashboardPage(props: { searchParams: Promise<PolicyDashboardSearchParams> }) {
  const searchParams = await props.searchParams
  const policyVersionId = searchParams.policyVersionId
  const tab = searchParams.tab

  const dashboardUrl = buildEmbeddedPolicyDashboardUrl(config.policyDashboardUrl, {
    policyVersionId: typeof policyVersionId === 'string' && policyVersionId.trim() ? policyVersionId : null,
    tab: parsePolicyDashboardTab(typeof tab === 'string' ? tab : null),
  })

  return (
    <div className="h-[calc(100vh-57px)]">
      <PolicyDashboardEmbed src={dashboardUrl} />
    </div>
  )
}
