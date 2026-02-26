"use client";

import { FC, useState } from "react";
import type { SeasonDetail } from "@/lib/api";

const EPISODE_RUNNER_GHCR_URL =
  "https://github.com/orgs/Metta-AI/packages/container/package/episode-runner";
const EXTERNAL_LINK_CLASS =
  "text-blue-600 dark:text-blue-400 no-underline hover:underline";
const COPYABLE_COMMAND_CLASS =
  "inline-flex items-center rounded border border-border px-1.5 py-0.5 text-[11px] font-semibold text-foreground-muted hover:border-border-strong hover:text-foreground transition-colors";

type TournamentDescriptionMetaSeason = Pick<
  SeasonDetail,
  "name" | "compat_version" | "status"
>;

export const TournamentDescriptionMeta: FC<{
  season: TournamentDescriptionMetaSeason;
}> = ({ season }) => {
  const [copied, setCopied] = useState(false);
  const compatTag = season.compat_version
    ? `compat-v${season.compat_version}`
    : null;
  const compatGhcrHref = compatTag
    ? `${EPISODE_RUNNER_GHCR_URL}?tag=${encodeURIComponent(compatTag)}`
    : null;
  const submitCommand = `cogames upload --name my-policy --policy ./run --season ${season.name}`;
  const showSubmitCommand = season.status === "not_started";

  if (!season.compat_version && !showSubmitCommand) {
    return null;
  }

  const copySubmitCommand = async () => {
    if (
      typeof navigator === "undefined" ||
      typeof navigator.clipboard === "undefined"
    ) {
      return;
    }
    try {
      await navigator.clipboard.writeText(submitCommand);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.error("Failed to copy submit command:", error);
    }
  };

  return (
    <>
      {showSubmitCommand && (
        <span className="inline-flex items-center gap-1">
          Submission command:
          <button
            type="button"
            onClick={copySubmitCommand}
            className={COPYABLE_COMMAND_CLASS}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </span>
      )}
      {season.compat_version && (
        <span className="ml-auto inline-flex items-center gap-1">
          Compat version:{" "}
          <span className="font-mono">{season.compat_version}</span>
          {compatGhcrHref && (
            <>
              (
              <a
                href={compatGhcrHref}
                target="_blank"
                rel="noopener noreferrer"
                className={EXTERNAL_LINK_CLASS}
              >
                GHCR
              </a>
              )
            </>
          )}
        </span>
      )}
    </>
  );
};
