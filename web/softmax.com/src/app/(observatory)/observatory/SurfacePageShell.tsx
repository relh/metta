import { PropsWithChildren } from "react";

import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";

type SurfacePageShellProps = PropsWithChildren;

type SurfaceNotConfiguredProps = {
  serviceName: string;
  envVar: string;
};

export function SurfacePageShell({ children }: SurfacePageShellProps) {
  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">{children}</div>
    </SoftmaxGuard>
  );
}

export function SurfaceNotConfigured({
  serviceName,
  envVar,
}: SurfaceNotConfiguredProps) {
  return (
    <SoftmaxGuard>
      <div className="mx-auto max-w-3xl p-6">
        <div className="border-border-strong bg-surface rounded border p-4">
          <h1 className="text-foreground text-lg font-semibold">
            {serviceName} is not configured
          </h1>
          <p className="text-foreground-muted mt-2">
            Set <code>{envVar}</code> to the hosted {serviceName} service URL
            for this environment.
          </p>
        </div>
      </div>
    </SoftmaxGuard>
  );
}
