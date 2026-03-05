import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";

export default function BardoPage() {
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

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-57px)]">
        <iframe
          title="Bardo"
          src={config.bardoUrl}
          className="bg-background h-full w-full border-0"
          referrerPolicy="no-referrer"
        />
      </div>
    </SoftmaxGuard>
  );
}
