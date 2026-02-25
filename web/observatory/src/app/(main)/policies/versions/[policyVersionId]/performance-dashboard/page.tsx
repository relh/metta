import { redirect } from 'next/navigation'

import { policyDashboardRoute } from '@/lib/routes'

export default async function PerformanceDashboardPage(props: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await props.params
  redirect(policyDashboardRoute({ policyVersionId }))
}

export async function generateMetadata(_: PageProps<'/policies/versions/[policyVersionId]'>) {
  return {
    title: 'Performance Dashboard | Observatory',
  }
}
