import { config } from "@observatory/config";
import { SoftmaxGuard } from "@observatory/components/SoftmaxGuard";

import { SurfaceEmbed } from "../SurfaceEmbed";

export default function TrainBoardPage() {
  if (!config.trainBoardUrl) {
    return (
      <SoftmaxGuard>
        <div className="mx-auto max-w-3xl p-6">
          <div className="border-border-strong bg-surface rounded border p-4">
            <h1 className="text-foreground text-lg font-semibold">
              Train Board is not configured
            </h1>
            <p className="text-foreground-muted mt-2">
              Set <code>OBSERVATORY_TRAIN_BOARD_URL</code> to the hosted Train
              Board service URL for this environment.
            </p>
          </div>
        </div>
      </SoftmaxGuard>
    );
  }

  return (
    <SoftmaxGuard>
      <div className="h-[calc(100vh-114px)]">
        <SurfaceEmbed src={config.trainBoardUrl} serviceName="Train Board" />
      </div>
    </SoftmaxGuard>
  );
}
