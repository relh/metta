import { Metadata } from "next";

import { config } from "@observatory/config";

import { SurfaceEmbed } from "../SurfaceEmbed";
import { SurfaceNotConfigured, SurfacePageShell } from "../SurfacePageShell";

export default function PantheonPage() {
  if (!config.pantheonUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Pantheon"
        envVar="OBSERVATORY_PANTHEON_URL"
      />
    );
  }

  return (
    <SurfacePageShell>
      <SurfaceEmbed src={config.pantheonUrl} serviceName="Pantheon" />
    </SurfacePageShell>
  );
}

export const metadata: Metadata = {
  title: "Pantheon | Observatory",
};
