import { Metadata } from "next";

import { config } from "@observatory/config";
import { buildEmbeddedDiagnoseUrl } from "@observatory/lib/diagnose";

import { SurfaceEmbed } from "../SurfaceEmbed";
import { SurfaceNotConfigured, SurfacePageShell } from "../SurfacePageShell";

export default function DiagnosePage() {
  if (!config.diagnoseUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Diagnose"
        envVar="OBSERVATORY_DIAGNOSE_URL"
      />
    );
  }

  const diagnoseUrl = buildEmbeddedDiagnoseUrl(config.diagnoseUrl);

  return (
    <SurfacePageShell>
      <SurfaceEmbed src={diagnoseUrl} serviceName="Diagnose" />
    </SurfacePageShell>
  );
}

export const metadata: Metadata = {
  title: "Diagnose | Observatory",
};
