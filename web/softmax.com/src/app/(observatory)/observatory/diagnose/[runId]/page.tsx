import { Metadata } from "next";

import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import { buildEmbeddedPolicyDashboardDiagnoseUrl } from "@observatory/lib/policy-dashboard";

import { PolicyDashboardEmbed } from "../../policy-dashboard/PolicyDashboardEmbed";

type DiagnoseRunParams = {
  runId: string;
};

export default async function DiagnoseRunPage({
  params,
}: {
  params: Promise<DiagnoseRunParams>;
}) {
  if (!config.policyDashboardUrl) {
    return (
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Diagnose is not configured
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

  const { runId } = await params;
  const diagnoseUrl = buildEmbeddedPolicyDashboardDiagnoseUrl(
    config.policyDashboardUrl,
    runId,
  );

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <PolicyDashboardEmbed src={diagnoseUrl} />
      </div>
    </SoftmaxGuard>
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<DiagnoseRunParams>;
}): Promise<Metadata> {
  const { runId } = await params;
  return {
    title: `Diagnose ${runId} | Observatory`,
  };
}
