import { config } from "@observatory/config";

import { SurfaceEmbed } from "../SurfaceEmbed";
import { SurfaceNotConfigured, SurfacePageShell } from "../SurfacePageShell";

export default function TrainBoardPage() {
  if (!config.trainBoardUrl) {
    return (
      <SurfaceNotConfigured
        serviceName="Train Board"
        envVar="OBSERVATORY_TRAIN_BOARD_URL"
      />
    );
  }

  return (
    <SurfacePageShell>
      <SurfaceEmbed src={config.trainBoardUrl} serviceName="Train Board" />
    </SurfacePageShell>
  );
}
