import { redirect } from 'next/navigation'

import { buildPolicyDashboardPath } from '@/lib/policy-dashboard'

export default async function PerformanceDashboardPage(props: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await props.params
  redirect(buildPolicyDashboardPath({ policyVersionId }))
}

export async function generateMetadata(_: PageProps<'/policies/versions/[policyVersionId]'>) {
  return {
    title: 'Performance Dashboard | Observatory',
  }
}
