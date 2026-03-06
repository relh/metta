import { Metadata } from "next";

import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";

import { PolicyDashboardEmbed } from "../policy-dashboard/PolicyDashboardEmbed";

export default function PantheonPage() {
  if (!config.pantheonUrl) {
    return (
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Pantheon is not configured
            </h1>
            <p className="text-foreground-muted mt-2">
              Set <code>OBSERVATORY_PANTHEON_URL</code> to the hosted Pantheon
              URL for this environment.
            </p>
          </div>
        </div>
      </SoftmaxGuard>
    );
  }

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <PolicyDashboardEmbed src={config.pantheonUrl} />
      </div>
    </SoftmaxGuard>
  );
}

export const metadata: Metadata = {
  title: "Pantheon | Observatory",
};
