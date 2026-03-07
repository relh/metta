"use client";

import { SurfaceEmbed } from "../SurfaceEmbed";

export function PolicyDashboardEmbed({ src }: { src: string }) {
  return (
    <SurfaceEmbed
      src={src}
      serviceName="Policy Dashboard"
      iframeTitle="Policy Dashboard"
    />
  );
}
