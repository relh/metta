"use client";

import { useRouter } from "next/navigation";
import { FC, use, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Button } from "@observatory/components/Button";

export const StartTournamentButton: FC<{
  seasonName: string;
  policyCount: number;
}> = ({ seasonName, policyCount }) => {
  const { repo, isSoftmaxTeamMember } = use(AppContext);
  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStart = async () => {
    setStarting(true);
    setError(null);
    try {
      await repo.startSeason(seasonName);
      router.refresh();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Failed to start tournament",
      );
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-foreground-muted text-sm">
        {policyCount} {policyCount === 1 ? "policy" : "policies"} in pool.
        {isSoftmaxTeamMember
          ? " Start the tournament to begin stage 1 evaluation."
          : " Waiting for the tournament to be started."}
      </p>
      {isSoftmaxTeamMember && (
        <Button
          onClick={handleStart}
          theme="primary"
          disabled={starting || policyCount === 0}
        >
          {starting ? "Starting..." : "Start Tournament"}
        </Button>
      )}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
};
