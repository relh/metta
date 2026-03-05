import { Metadata } from "next";

import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";
import { buildEmbeddedBardoUrl } from "@observatory/lib/bardo";

import { BardoEmbed } from "./BardoEmbed";

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
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Bardo is not configured
            </h1>
            <p className="text-foreground-muted mt-2">
              Set <code>OBSERVATORY_BARDO_URL</code> to the hosted Bardo service
              URL for this environment.
            </p>
          </div>
        </div>
      </SoftmaxGuard>
    );
  }

  const params = await searchParams;
  const nameFilter = params.q;
  const bardoUrl = buildEmbeddedBardoUrl(config.bardoUrl, {
    nameFilter:
      typeof nameFilter === "string" && nameFilter.trim() ? nameFilter : null,
  });

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-57px)]">
        <BardoEmbed src={bardoUrl} />
      </div>
    </SoftmaxGuard>
  );
}

export const metadata: Metadata = {
  title: "Bardo | Observatory",
};
