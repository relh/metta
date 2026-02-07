import { Suspense } from 'react'

import { Card } from '@/components/Card'
import { CopyableUri } from '@/components/CopyableUri'
import { LinkButton } from '@/components/LinkButton'
import { Spinner } from '@/components/Spinner'
import { UserDisplay } from '@/components/UserDisplay'
import { TasksTable } from '@/EvalTasks/TasksTable'
import { ServerDebugDrain } from '@/lib/debug/ServerDebugDrain'
import { getRepo } from '@/lib/repo/server'
import { formatDate } from '@/utils/datetime'
import { formatPolicyVersion } from '@/utils/format'

import { PolicyVersionJobsCard } from './PolicyVersionJobsCard'
import { PolicyVersionTournamentMembershipsCard } from './PolicyVersionTournamentMembershipsCard'

export default async function PolicyVersionPage(props: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await props.params

  const repo = await getRepo()
  const pvInfo = await repo.getPolicyVersion(policyVersionId)

  const policyCreatedAt = pvInfo?.created_at || null
  const policyDisplay = formatPolicyVersion(pvInfo, policyVersionId)

  return (
    <div className="p-6 max-w-[1600px] mx-auto space-y-6">
      <ServerDebugDrain />
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-gray-500 tracking-wide">Policy Version</p>
          <h1 className="text-2xl font-semibold text-gray-900">{policyDisplay}</h1>
          <div className="flex flex-wrap gap-3 text-sm text-gray-600">
            {policyCreatedAt && <span className="text-gray-500">Created: {formatDate(policyCreatedAt)}</span>}
            <span className="text-gray-500">
              User: <UserDisplay user={pvInfo.user} userId={pvInfo.user_id} />
            </span>
            <span className="flex items-center gap-1 text-gray-500">
              Policy Version ID:
              <span className="font-mono text-xs text-gray-700">{pvInfo.id}</span>
            </span>
          </div>
        </div>
        {pvInfo && (
          <LinkButton href={`/policies/${pvInfo.policy_id}`} theme="tertiary">
            ← Back to policy
          </LinkButton>
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
