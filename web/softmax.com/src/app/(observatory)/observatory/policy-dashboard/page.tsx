import { config } from "@observatory/config";
import {
  buildEmbeddedPolicyDashboardUrl,
  parsePolicyDashboardTab,
} from "@observatory/lib/policy-dashboard";

import { SurfaceEmbed } from "../SurfaceEmbed";
import { SurfaceNotConfigured, SurfacePageShell } from "../SurfacePageShell";

type PolicyDashboardSearchParams = {
  policyVersionId?: string | string[];
  tab?: string | string[];
};

export default async function PolicyDashboardPage(props: {
  searchParams: Promise<PolicyDashboardSearchParams>;
}) {
  if (!config.policyDashboardUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Policy Dashboard"
        envVar="OBSERVATORY_POLICY_DASHBOARD_URL"
      />
    );
  }

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
    <SurfacePageShell>
      <SurfaceEmbed
        src={dashboardUrl}
        serviceName="Policy Dashboard"
        iframeTitle="Policy Dashboard"
      />
    </SurfacePageShell>
  );
}
