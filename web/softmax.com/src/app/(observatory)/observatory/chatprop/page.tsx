import { config } from "@observatory/config";

import { SurfaceNotConfigured, SurfacePageShell } from "../SurfacePageShell";

export default function ChatpropPage() {
  if (!config.chatpropUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Chatprop"
        envVar="OBSERVATORY_CHATPROP_URL"
      />
    );
  }

  return (
    <SurfacePageShell>
      <iframe
        title="Chatprop"
        src={config.chatpropUrl}
        className="bg-background h-full w-full border-0"
        referrerPolicy="no-referrer"
      />
    </SurfacePageShell>
  );
}
