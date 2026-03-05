import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import {
  buildEmbeddedPolicyDashboardUrl,
  parsePolicyDashboardTab,
} from "@observatory/lib/policy-dashboard";

import { PolicyDashboardEmbed } from "./PolicyDashboardEmbed";

type PolicyDashboardSearchParams = {
  policyVersionId?: string | string[];
  tab?: string | string[];
};

export default async function PolicyDashboardPage(props: {
  searchParams: Promise<PolicyDashboardSearchParams>;
}) {
  const searchParams = await props.searchParams;
  const policyVersionId = searchParams.policyVersionId;
  const tab = searchParams.tab;

  const dashboardUrl = buildEmbeddedPolicyDashboardUrl(
    config.policyDashboardUrl,
    {
      policyVersionId:
        typeof policyVersionId === "string" && policyVersionId.trim()
          ? policyVersionId
          : null,
      tab: parsePolicyDashboardTab(typeof tab === "string" ? tab : null),
    },
  );

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <PolicyDashboardEmbed src={dashboardUrl} />
      </div>
    </SoftmaxGuard>
  );
}
