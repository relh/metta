"use client";

import { FC, useState } from "react";

import { METTASCOPE_REPLAY_URL_PREFIX } from "../constants";
import { A } from "./A";
import { SmallHeader } from "./SmallHeader";

export function normalizeReplayUrl(
  replayUrl: string | null | undefined,
): string | null {
  if (!replayUrl) return null;
  if (replayUrl.startsWith(METTASCOPE_REPLAY_URL_PREFIX)) {
    return replayUrl;
  }
  return `${METTASCOPE_REPLAY_URL_PREFIX}${replayUrl}`;
}

type ReplayViewerProps = {
  replayUrl: string | null | undefined;
  label?: string;
  height?: number;
  showExternalLink?: boolean;
};

export const ReplayViewer: FC<ReplayViewerProps> = ({
  replayUrl,
  label,
  height = 480,
  showExternalLink = true,
}) => {
  const [copied, setCopied] = useState(false);

  const normalized = normalizeReplayUrl(replayUrl);

  if (!normalized) {
    return (
      <div className="text-foreground-muted text-sm">No replay available.</div>
    );
  }

  const handleCopyUrl = () => {
    if (normalized) {
      navigator.clipboard.writeText(normalized);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-2">
      {label ? <SmallHeader>{label}</SmallHeader> : null}
      <div
        className="border-border w-full overflow-hidden rounded border bg-black"
        style={{ minHeight: "360px", height }}
      >
        <iframe
          src={normalized}
          title={label ?? "Episode replay"}
          className="h-full w-full"
          allowFullScreen
        />
      </div>
      {showExternalLink ? (
        <div className="flex items-center gap-3 text-sm">
          <A href={normalized} target="_blank" rel="noopener noreferrer">
            Open in MettaScope
          </A>
          <button
            onClick={handleCopyUrl}
            className="cursor-pointer text-blue-600 hover:text-blue-800 hover:underline"
          >
            {copied ? "Copied!" : "Copy Url"}
          </button>
        </div>
      ) : null}
    </div>
  );
};
