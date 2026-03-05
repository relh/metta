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
  if (!config.policyDashboardUrl) {
    return (
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Policy Dashboard is not configured
            </h1>
            <p className="text-foreground-muted mt-2">
              Set <code>OBSERVATORY_POLICY_DASHBOARD_URL</code> to the hosted
              Policy Dashboard URL for this environment.
            </p>
          </div>
        </div>
      </SoftmaxGuard>
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
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <PolicyDashboardEmbed src={dashboardUrl} />
      </div>
    </SoftmaxGuard>
  );
}
