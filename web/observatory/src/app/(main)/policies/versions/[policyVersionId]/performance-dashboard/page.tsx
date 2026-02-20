import { redirect } from 'next/navigation'

export default async function PerformanceDashboardPage(props: PageProps<'/policies/versions/[policyVersionId]'>) {
  const { policyVersionId } = await props.params
  const standaloneDashboardBaseUrl =
    process.env.OBSERVATORY_STANDALONE_DASHBOARD_URL?.replace(/\/$/, '') ?? 'http://localhost:5174'
  const standaloneDashboardHref = `${standaloneDashboardBaseUrl}/?policyVersionId=${encodeURIComponent(policyVersionId)}`
  redirect(standaloneDashboardHref)
}

export async function generateMetadata(_: PageProps<'/policies/versions/[policyVersionId]'>) {
  return {
    title: 'Performance Dashboard | Observatory',
  }
}
