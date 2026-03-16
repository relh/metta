import { Metadata } from "next";

import { config } from "@observatory/config";
import { buildEmbeddedBardoUrl } from "@observatory/lib/bardo";

import { SurfaceEmbed } from "../SurfaceEmbed";
import { SurfaceNotConfigured, SurfacePageShell } from "../SurfacePageShell";

type BardoSearchParams = {
  q?: string | string[];
};

export default async function BardoPage({
  searchParams,
}: {
  searchParams: Promise<BardoSearchParams>;
}) {
  if (!config.bardoUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Bardo"
        envVar="OBSERVATORY_BARDO_URL"
      />
    );
  }

  const params = await searchParams;
  const nameFilter = params.q;
  const bardoUrl = buildEmbeddedBardoUrl(config.bardoUrl, {
    nameFilter:
      typeof nameFilter === "string" && nameFilter.trim() ? nameFilter : null,
  });

  return (
    <SurfacePageShell>
      <SurfaceEmbed
        src={bardoUrl}
        serviceName="Bardo"
        iframeTitle="Policy Bardo"
      />
    </SurfacePageShell>
  );
}

export const metadata: Metadata = {
  title: "Bardo | Observatory",
};
