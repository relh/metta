import { Metadata } from "next";

import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import { buildEmbeddedDiagnoseUrl } from "@observatory/lib/diagnose";

import { PolicyDashboardEmbed } from "../policy-dashboard/PolicyDashboardEmbed";

export default function DiagnosePage() {
  if (!config.diagnoseUrl) {
    return (
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Diagnose is not configured
            </h1>
            <p className="text-foreground-muted mt-2">
              Set <code>OBSERVATORY_DIAGNOSE_URL</code> to the hosted Diagnose
              URL for this environment.
            </p>
          </div>
        </div>
      </SoftmaxGuard>
    );
  }

  const diagnoseUrl = buildEmbeddedDiagnoseUrl(config.diagnoseUrl);

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <PolicyDashboardEmbed src={diagnoseUrl} />
      </div>
    </SoftmaxGuard>
  );
}

export const metadata: Metadata = {
  title: "Diagnose | Observatory",
};
