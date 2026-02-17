import { LinkButton } from '@/components/LinkButton'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatPolicyVersion } from '@/utils/format'

import { PolicyDashboard } from './PolicyDashboard'

export default async function DashboardPage(props: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await props.params

  const repo = await getRepo()
  const pvInfo = await repo.getPolicyVersion(policyVersionId)
  const dashboardData = await repo.getDashboardData(policyVersionId)
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId)

  return (
    <div className="p-6 max-w-[1600px] mx-auto space-y-6">
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-foreground-muted tracking-wide">Policy Dashboard</p>
          <h1 className="text-2xl font-semibold text-foreground">{policyDisplay}</h1>
        </div>
        <LinkButton href={`/policies/versions/${policyVersionId}`} theme="tertiary">
          &larr; Back to policy version
        </LinkButton>
      </div>

      <PolicyDashboard policyVersionId={policyVersionId} data={dashboardData} />
    </div>
  )
}

export async function generateMetadata({ params }: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await params
  const repo = await getRepo()
  const pvInfo = await repo.getPolicyVersion(policyVersionId)
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId)
  return {
    title: `Dashboard: ${policyDisplay} | Observatory`,
  }
}
