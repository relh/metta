"use client";

import { useQueryStates } from "nuqs";
import { FC } from "react";

import { Select } from "@observatory/components/Select";
import type { StageStats } from "@observatory/lib/api";

import { nuqsParams } from "./searchParams";

export const TeamFilters: FC<{ stages: StageStats[] }> = ({ stages }) => {
  const [filters, setFilters] = useQueryStates(nuqsParams, { shallow: false });

  const poolOptions = stages
    .filter(
      (s) =>
        s.team_count !== null && s.team_count !== undefined && s.team_count > 0,
    )
    .map((s) => ({ value: s.name, label: s.name }));

  const statusOptions = [
    { value: "", label: "All" },
    { value: "alive", label: "Alive" },
    { value: "eliminated", label: "Eliminated" },
  ];

  return (
    <div className="border-border-subtle mb-4 flex gap-4 border-b pb-4">
      <div className="flex-1">
        <div className="text-foreground-muted mb-1 text-xs">Pool</div>
        <Select
          options={poolOptions}
          value={poolOptions.find((o) => o.value === filters.pool_name) ?? null}
          onChange={(selected) =>
            setFilters((f) => ({
              ...f,
              pool_name: selected?.value ?? "",
              teams_page: 0,
            }))
          }
          placeholder="All pools"
          isClearable
          instanceId="team-pool-select"
        />
      </div>
      <div className="flex-1">
        <div className="text-foreground-muted mb-1 text-xs">Status</div>
        <Select
          options={statusOptions}
          value={
            statusOptions.find((o) => o.value === filters.eliminated) ??
            statusOptions[0]
          }
          onChange={(selected) =>
            setFilters((f) => ({
              ...f,
              eliminated: selected?.value ?? "",
              teams_page: 0,
            }))
          }
          instanceId="team-status-select"
        />
      </div>
    </div>
  );
};
