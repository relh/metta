"use client";

import { InlineCode } from "@/components/InlineCode";
import type { PolicyVersionSummary } from "@/lib/observatoryClient";

type PolicyTagProps = {
  policy: PolicyVersionSummary;
  score?: number | null;
  onClick?: () => void;
};

export function PolicyTag({ policy, score, onClick }: PolicyTagProps) {
  const content = (
    <>
      <InlineCode>
        {policy.name ?? "Unnamed"}:v{policy.version ?? 0}
      </InlineCode>
      {score !== undefined && score !== null && (
        <span className="ml-1 text-xs text-[#8a9bb8]">
          ({score.toFixed(1)})
        </span>
      )}
    </>
  );

  if (onClick) {
    return (
      <button
        onClick={onClick}
        className="inline-flex items-center hover:opacity-70"
        title="Click to filter matches"
      >
        {content}
      </button>
    );
  }

  return <span className="inline-flex items-center">{content}</span>;
}
