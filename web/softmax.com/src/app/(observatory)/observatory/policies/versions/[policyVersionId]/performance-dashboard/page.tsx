import { redirect } from "next/navigation";

import { policyDashboardRoute } from "@observatory/lib/routes";

export default async function PerformanceDashboardPage(
  props: PageProps<"/observatory/policies/versions/[policyVersionId]">,
) {
  const { policyVersionId } = await props.params;
  redirect(policyDashboardRoute({ policyVersionId }));
}

export async function generateMetadata(
  _: PageProps<"/observatory/policies/versions/[policyVersionId]">,
) {
  return {
    title: "Performance Dashboard | Observatory",
  };
}
