import { Metadata } from "next";

import { config } from "@observatory/config";
import { buildEmbeddedDiagnoseUrl } from "@observatory/lib/diagnose";

import { SurfaceEmbed } from "../../SurfaceEmbed";
import { SurfaceNotConfigured, SurfacePageShell } from "../../SurfacePageShell";

type DiagnoseRunParams = {
  runId: string;
};

export default async function DiagnoseRunPage({
  params,
}: {
  params: Promise<DiagnoseRunParams>;
}) {
  if (!config.diagnoseUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Diagnose"
        envVar="OBSERVATORY_DIAGNOSE_URL"
      />
    );
  }

  const { runId } = await params;
  const diagnoseUrl = buildEmbeddedDiagnoseUrl(config.diagnoseUrl, runId);

  return (
    <SurfacePageShell>
      <SurfaceEmbed src={diagnoseUrl} serviceName="Diagnose" />
    </SurfacePageShell>
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
