import { Suspense } from 'react'

import { Card } from '@/components/Card'
import { CopyableUri } from '@/components/CopyableUri'
import { LinkButton } from '@/components/LinkButton'
import { Spinner } from '@/components/Spinner'
import { UserDisplay } from '@/components/UserDisplay'
import { TasksTable } from '@/EvalTasks/TasksTable'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { policyDashboardRoute, policyRoute } from '@/lib/routes'
import { getRepo } from '@/lib/repo/server'
import { formatDate } from '@/utils/datetime'
import { formatPolicyVersion } from '@/utils/format'

import { PolicyVersionJobsCard } from './PolicyVersionJobsCard'
import { PolicyVersionTournamentMembershipsCard } from './PolicyVersionTournamentMembershipsCard'

export default async function PolicyVersionPage(props: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await props.params
  const standaloneDashboardHref = policyDashboardRoute({ policyVersionId })

  const repo = await getRepo()
  const pvInfo = await repo.getPolicyVersion(policyVersionId)

  const policyCreatedAt = pvInfo?.created_at || null
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId)

  return (
    <div className="p-6 max-w-[1600px] mx-auto space-y-6">
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-foreground-muted tracking-wide">Policy Version</p>
          <h1 className="text-2xl font-semibold text-foreground">{policyDisplay}</h1>
          <div className="flex flex-wrap gap-3 text-sm text-foreground-muted">
            {policyCreatedAt && <span className="text-foreground-muted">Created: {formatDate(policyCreatedAt)}</span>}
            <span className="text-foreground-muted">
              User: <UserDisplay user={pvInfo.user} userId={pvInfo.user_id} />
            </span>
            <span className="flex items-center gap-1 text-foreground-muted">
              Policy Version ID:
              <span className="font-mono text-xs text-foreground-subtle">{pvInfo.id}</span>
            </span>
          </div>
        </div>
        {pvInfo && (
          <div className="flex gap-2">
            <LinkButton href={standaloneDashboardHref} theme="secondary">
              View Dashboard
            </LinkButton>
            <LinkButton href={policyRoute(pvInfo.policy_id)} theme="tertiary">
              &larr; Back to policy
            </LinkButton>
          </div>
        )}
      </div>

      <CopyableUri uri={`metta://policy/${pvInfo.name}:v${pvInfo.version}`} />

      <Suspense fallback={<Spinner />}>
        <PolicyVersionJobsCard policyVersionId={policyVersionId} searchParams={props.searchParams} />
      </Suspense>

      <Suspense fallback={<Spinner />}>
        <PolicyVersionTournamentMembershipsCard policyVersionId={policyVersionId} />
      </Suspense>

      <Card title="Tasks">
        <TasksTable initialFilters={{ command: policyVersionId }} hideFilters />
      </Card>
    </div>
  )
}

export async function generateMetadata({ params }: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await params
  const repo = await getRepo()
  const pvInfo = await repo.getPolicyVersion(policyVersionId)
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId)
  return {
    title: `${policyDisplay} | Observatory`,
  }
}
