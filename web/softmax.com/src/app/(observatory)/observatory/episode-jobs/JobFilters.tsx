"use client";
import { parseAsString, useQueryState } from "nuqs";
import {
  FC,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useTransition,
} from "react";

import { AsyncSelect } from "@observatory/components/AsyncSelect";
import { Select } from "@observatory/components/Select";
import { Spinner } from "@observatory/components/Spinner";
import {
  ALL_JOB_STATUSES,
  JobStatus,
  PolicyVersionRow,
  SeasonDetail,
  SeasonSummary,
} from "@observatory/lib/repo";

type Option = { value: string; label: string };

function formatPolicyOption(pv: PolicyVersionRow): string {
  if (pv.name && pv.version != null) return `${pv.name}:v${pv.version}`;
  return pv.id.slice(0, 8);
}

async function searchPolicies(query: string): Promise<Option[]> {
  const params = new URLSearchParams({ limit: "20" });
  if (query) params.set("name_fuzzy", query);
  const resp = await fetch(`/api/observatory/stats/policy-versions?${params}`);
  const entries: PolicyVersionRow[] = await resp.json();
  return entries.map((pv) => ({ value: pv.id, label: formatPolicyOption(pv) }));
}

const DEBOUNCE_MS = 300;

const PolicySelect: FC<{ defaultPolicyVersionId?: string }> = ({
  defaultPolicyVersionId,
}) => {
  const [isPending, startTransition] = useTransition();
  const [policyVersionId, setPolicyVersionId] = useQueryState(
    "policyVersionId",
    parseAsString.withDefault("").withOptions({
      shallow: false,
      history: "replace",
      startTransition,
    }),
  );

  const effectiveId = policyVersionId || defaultPolicyVersionId || "";
  const [selected, setSelected] = useState<Option | null>(null);
  const lastResolvedId = useRef("");

  useEffect(() => {
    if (effectiveId && effectiveId !== lastResolvedId.current) {
      lastResolvedId.current = effectiveId;
      searchPolicies("").then((options) => {
        const match = options.find((o) => o.value === effectiveId);
        if (match) setSelected(match);
        else
          setSelected({ value: effectiveId, label: effectiveId.slice(0, 8) });
      });
    } else if (!effectiveId) {
      lastResolvedId.current = "";
      setSelected(null);
    }
  }, [effectiveId]);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const loadOptions = useCallback(
    (inputValue: string, callback: (options: Option[]) => void) => {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        searchPolicies(inputValue).then(callback);
      }, DEBOUNCE_MS);
    },
    [],
  );

  return (
    <div className="flex items-center gap-2">
      <div className="w-64">
        <AsyncSelect<Option>
          value={selected}
          onChange={(opt) => {
            setSelected(opt);
            setPolicyVersionId(opt?.value ?? null);
          }}
          loadOptions={loadOptions}
          defaultOptions
          placeholder="Search policies..."
          isClearable
          instanceId="policy-select"
          cacheOptions
        />
      </div>
      <span className={isPending ? "visible" : "invisible"}>
        <Spinner />
      </span>
    </div>
  );
};

const StatusSelect: FC = () => {
  const [isPending, startTransition] = useTransition();
  const [status, setStatus] = useQueryState(
    "status",
    parseAsString.withDefault("").withOptions({
      shallow: false,
      history: "replace",
      startTransition,
    }),
  );

  const options: Option[] = ALL_JOB_STATUSES.map((s) => ({
    value: s,
    label: s,
  }));
  const selected = options.find((o) => o.value === status) ?? null;

  return (
    <div className="flex items-center gap-2">
      <div className="w-40">
        <Select<Option>
          options={options}
          value={selected}
          onChange={(opt) => setStatus((opt?.value as JobStatus) ?? null)}
          placeholder="All statuses"
          isClearable
          instanceId="status-select"
        />
      </div>
      <span className={isPending ? "visible" : "invisible"}>
        <Spinner />
      </span>
    </div>
  );
};

const SeasonSelect: FC<{ seasons: SeasonSummary[] }> = ({ seasons }) => {
  const [isPending, startTransition] = useTransition();
  const [seasonId, setSeasonId] = useQueryState(
    "seasonId",
    parseAsString.withDefault("").withOptions({
      shallow: false,
      history: "replace",
      startTransition,
    }),
  );

  type SeasonOption = Option & { version: number };
  const options: SeasonOption[] = useMemo(
    () =>
      seasons.map((s) => ({ value: s.id, label: s.name, version: s.version })),
    [seasons],
  );
  const selected = options.find((o) => o.value === seasonId) ?? null;

  return (
    <div className="flex items-center gap-2">
      <div className="w-48">
        <Select<SeasonOption>
          options={options}
          value={selected}
          onChange={(opt) => setSeasonId(opt?.value ?? null)}
          formatOptionLabel={(opt) => (
            <span>
              {opt.label}{" "}
              <span className="text-foreground-muted">(v{opt.version})</span>
            </span>
          )}
          placeholder="All seasons"
          isClearable
          instanceId="season-select"
        />
      </div>
      <span className={isPending ? "visible" : "invisible"}>
        <Spinner />
      </span>
    </div>
  );
};

const PoolSelect: FC<{ selectedSeason: SeasonDetail | null }> = ({
  selectedSeason,
}) => {
  const [isPending, startTransition] = useTransition();
  const [poolId, setPoolId] = useQueryState(
    "poolId",
    parseAsString.withDefault("").withOptions({
      shallow: false,
      history: "replace",
      startTransition,
    }),
  );

  const options: Option[] = useMemo(() => {
    if (!selectedSeason) return [];
    return selectedSeason.pools.flatMap((p) =>
      p.id ? [{ value: p.id, label: p.name }] : [],
    );
  }, [selectedSeason]);

  useEffect(() => {
    if (poolId && !options.find((o) => o.value === poolId)) {
      setPoolId(null);
    }
  }, [options, poolId, setPoolId]);

  const selected = options.find((o) => o.value === poolId) ?? null;

  return (
    <div className="flex items-center gap-2">
      <div className="w-48">
        <Select<Option>
          options={options}
          value={selected}
          onChange={(opt) => setPoolId(opt?.value ?? null)}
          placeholder={selectedSeason ? "All pools" : "Select a season first"}
          isDisabled={!selectedSeason}
          isClearable
          instanceId="pool-select"
        />
      </div>
      <span className={isPending ? "visible" : "invisible"}>
        <Spinner />
      </span>
    </div>
  );
};

export const JobFilters: FC<{
  seasons: SeasonSummary[];
  selectedSeason: SeasonDetail | null;
  defaultPolicyVersionId?: string;
}> = ({ seasons, selectedSeason, defaultPolicyVersionId }) => {
  return (
    <>
      <div>
        <div className="text-foreground-muted mb-1 text-xs">Policy</div>
        <PolicySelect defaultPolicyVersionId={defaultPolicyVersionId} />
      </div>
      <div>
        <div className="text-foreground-muted mb-1 text-xs">Status</div>
        <StatusSelect />
      </div>
      <div>
        <div className="text-foreground-muted mb-1 text-xs">Season</div>
        <SeasonSelect seasons={seasons} />
      </div>
      <div>
        <div className="text-foreground-muted mb-1 text-xs">Pool</div>
        <PoolSelect selectedSeason={selectedSeason} />
      </div>
    </>
  );
};
