import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";

export default function ChatpropPage() {
  if (!config.chatpropUrl) {
    return (
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Chatprop is not configured
            </h1>
            <p className="text-foreground-muted mt-2">
              Set <code>OBSERVATORY_CHATPROP_URL</code> to the hosted Chatprop
              service URL for this environment.
            </p>
          </div>
        </div>
      </SoftmaxGuard>
    );
  }

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <iframe
          title="Chatprop"
          src={config.chatpropUrl}
          className="bg-background h-full w-full border-0"
          referrerPolicy="no-referrer"
        />
      </div>
    </SoftmaxGuard>
  );
}
