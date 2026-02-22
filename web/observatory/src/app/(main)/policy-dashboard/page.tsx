import { config } from '@/config'
import { buildEmbeddedPolicyDashboardUrl, parsePolicyDashboardTab } from '@/lib/policy-dashboard'
import { getRepo } from '@/lib/repo/server'

import { PolicyDashboardEmbed } from './PolicyDashboardEmbed'

type PolicyDashboardSearchParams = {
  policyVersionId?: string | string[]
  tab?: string | string[]
}

export default async function PolicyDashboardPage(props: { searchParams: Promise<PolicyDashboardSearchParams> }) {
  const searchParams = await props.searchParams
  const policyVersionId = searchParams.policyVersionId
  const tab = searchParams.tab
  const repo = await getRepo()

  let defaultPolicyVersionId: string | null = null
  if (typeof policyVersionId !== 'string' || !policyVersionId.trim()) {
    const seasons = await repo.getSeasons()
    const defaultSeason = seasons.find((season) => season.is_default) ?? seasons[0]
    if (defaultSeason) {
      const leaderboard = await repo.getSeasonLeaderboard(defaultSeason.name)
      const topPolicy = leaderboard[0]?.policy
      if (topPolicy?.id) {
        defaultPolicyVersionId = topPolicy.id
      }
    }
  }

  const dashboardUrl = buildEmbeddedPolicyDashboardUrl(config.policyDashboardUrl, {
    policyVersionId:
      typeof policyVersionId === 'string' && policyVersionId.trim() ? policyVersionId : defaultPolicyVersionId,
    tab: parsePolicyDashboardTab(typeof tab === 'string' ? tab : null),
  })

  return (
    <div className="h-[calc(100vh-57px)]">
      <PolicyDashboardEmbed src={dashboardUrl} />
    </div>
  )
}
