"use client";
import { FC } from "react";

import { Select } from "@observatory/components/Select";
import type { PolicySummary } from "@observatory/lib/api";

import { formatPolicyDisplay } from "../utils";
import { useMatchFilter } from "./hooks";

export const MatchFilters: FC<{
  policies: PolicySummary[];
}> = ({ policies }) => {
  const [matchFilter, setMatchFilter] = useMatchFilter();

  const playerOptions = policies.map((p) => ({
    value: p.policy.id,
    label: formatPolicyDisplay(p),
  }));

  return (
    <div className="border-border-subtle mb-4 border-b pb-4">
      <div className="text-foreground-muted mb-1 text-xs">Players</div>
      <Select
        isMulti
        options={playerOptions}
        value={playerOptions.filter((o) =>
          matchFilter.policy_version_ids.includes(o.value),
        )}
        onChange={(selected) =>
          setMatchFilter((f) => ({
            ...f,
            policy_version_ids: selected.map((s) => s.value),
          }))
        }
        placeholder="All players"
        isClearable
        instanceId="player-select"
      />
    </div>
  );
};
