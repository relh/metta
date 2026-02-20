"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { H2 } from "@/components/H2";
import { Table, TBody, TD, TH, THead, TR } from "@/components/Table";
import { MATCHES_PAGE_SIZE, METTASCOPE_BASE_URL } from "@/lib/constants";
import type {
  MatchResponse,
  SeasonDetail,
  SeasonSummary,
} from "@/lib/observatoryClient";
import { formatPolicyLabel } from "@/lib/policyUtils";

import { PolicyTag } from "./PolicyTag";

type PolicyOption = {
  id: string;
  name: string | null;
  version: number | null;
  label: string;
};

export function RecentMatches() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tableRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const seasonParam = searchParams.get("season") ?? "";
  const versionParam = searchParams.get("version") ?? "";

  const encodeSeasonRef = (value: string) => {
    try {
      return encodeURIComponent(decodeURIComponent(value));
    } catch {
      return encodeURIComponent(value);
    }
  };

  const [seasonName, setSeasonName] = useState("");
  const [matches, setMatches] = useState<MatchResponse[]>([]);
  const [pools, setPools] = useState<{ name: string; description: string }[]>(
    [],
  );
  const [seasonList, setSeasonList] = useState<SeasonSummary[]>([]);
  const [policyInfoCache, setPolicyInfoCache] = useState<
    Map<string, PolicyOption>
  >(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [policyDropdownOpen, setPolicyDropdownOpen] = useState(false);
  const [replayUrls, setReplayUrls] = useState<Map<string, string>>(new Map());

  const selectedPool = searchParams.get("pool") ?? "competition";
  const selectedPolicyIds =
    searchParams.get("policies")?.split(",").filter(Boolean) ?? [];

  const selectedPolicies = selectedPolicyIds
    .map((id) => policyInfoCache.get(id))
    .filter((p): p is PolicyOption => p !== undefined);

  useEffect(() => {
    async function fetchSeasonData() {
      try {
        const res = await fetch("/api/tournament/seasons");
        if (res.ok) {
          const seasons: SeasonSummary[] = await res.json();
          setSeasonList(seasons);
        }
      } catch (err) {
        console.error(err);
      }
    }
    fetchSeasonData();
  }, []);

  useEffect(() => {
    if (seasonList.length === 0) return;
    const defaultSeason = seasonList.find((s) => s.is_default) ?? seasonList[0];
    const desiredSeason = seasonParam || defaultSeason?.name || "";
    const season =
      seasonList.find((s) => s.name === desiredSeason) ?? defaultSeason;
    if (season) {
      if (season.name !== seasonName) {
        setSeasonName(season.name);
      }
    }
  }, [seasonList, seasonParam, seasonName]);

  useEffect(() => {
    let cancelled = false;
    async function fetchSeasonDetail() {
      if (!seasonName) {
        setPools([]);
        return;
      }
      try {
        const res = await fetch(
          `/api/tournament/seasons/${encodeSeasonRef(seasonName)}`,
        );
        if (!res.ok) throw new Error("Failed to fetch season detail");
        const season: SeasonDetail = await res.json();
        if (!cancelled) {
          setPools(season.pools);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) {
          setPools([]);
        }
      }
    }
    fetchSeasonDetail();
    return () => {
      cancelled = true;
    };
  }, [seasonName]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setPolicyDropdownOpen(false);
      }
    }
    if (policyDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () =>
        document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [policyDropdownOpen]);

  useEffect(() => {
    async function fetchMatches() {
      if (!seasonName) return;
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams();
        params.set("limit", String(MATCHES_PAGE_SIZE + 1));
        params.set("offset", String(page * MATCHES_PAGE_SIZE));
        if (selectedPool && selectedPool !== "all") {
          params.set("pool", selectedPool);
        }
        if (selectedPolicyIds.length > 0) {
          params.set("policies", selectedPolicyIds.join(","));
        }
        const seasonRef = versionParam
          ? `${seasonName}:v${versionParam}`
          : seasonName;
        const res = await fetch(
          `/api/tournament/seasons/${encodeSeasonRef(seasonRef)}/matches?${params.toString()}`,
        );
        if (!res.ok) throw new Error("Failed to fetch matches");
        const data: MatchResponse[] = await res.json();
        setHasMore(data.length > MATCHES_PAGE_SIZE);
        const matchesToShow = data.slice(0, MATCHES_PAGE_SIZE);
        setMatches(matchesToShow);
        setPolicyInfoCache((prev) => {
          const next = new Map(prev);
          for (const match of data) {
            for (const player of match.players) {
              if (!next.has(player.policy.id)) {
                next.set(player.policy.id, {
                  id: player.policy.id,
                  name: player.policy.name,
                  version: player.policy.version,
                  label: formatPolicyLabel(player.policy),
                });
              }
            }
          }
          return next;
        });

        const episodeIds = matchesToShow
          .filter((m) => m.episode_id)
          .map((m) => m.episode_id as string);
        if (episodeIds.length > 0) {
          const episodesRes = await fetch("/api/episodes/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ episode_ids: episodeIds }),
          });
          if (episodesRes.ok) {
            const episodesData = await episodesRes.json();
            const urlMap = new Map<string, string>();
            for (const ep of episodesData.episodes ?? []) {
              if (ep.id && ep.replay_url) {
                urlMap.set(ep.id, ep.replay_url);
              }
            }
            setReplayUrls(urlMap);
          }
        } else {
          setReplayUrls(new Map());
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    fetchMatches();
  }, [
    page,
    selectedPool,
    selectedPolicyIds.join(","),
    seasonName,
    versionParam,
  ]);

  const updateFilters = useCallback(
    (pool: string | null, policyIds: string[]) => {
      const params = new URLSearchParams(searchParams.toString());
      if (pool) params.set("pool", pool);
      else params.delete("pool");
      if (policyIds.length > 0) params.set("policies", policyIds.join(","));
      else params.delete("policies");
      setPage(0);
      router.push(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  const setPoolFilter = useCallback(
    (pool: string) => {
      updateFilters(pool || null, selectedPolicyIds);
    },
    [updateFilters, selectedPolicyIds],
  );

  const addPolicyFilter = useCallback(
    (policyId: string) => {
      if (!selectedPolicyIds.includes(policyId)) {
        updateFilters(selectedPool || null, [...selectedPolicyIds, policyId]);
      }
    },
    [updateFilters, selectedPool, selectedPolicyIds],
  );

  const removePolicyFilter = useCallback(
    (policyId: string) => {
      updateFilters(
        selectedPool || null,
        selectedPolicyIds.filter((id) => id !== policyId),
      );
    },
    [updateFilters, selectedPool, selectedPolicyIds],
  );

  if (error) {
    return (
      <section className="mt-8">
        <H2>Recent Matches</H2>
        <p className="text-red-500">Failed to load matches.</p>
      </section>
    );
  }

  return (
    <section id="recent-matches" className="mt-8">
      <div className="mb-4 flex flex-wrap items-center gap-4">
        <H2>Recent Matches</H2>
        <select
          value={selectedPool}
          onChange={(e) => setPoolFilter(e.target.value)}
          className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-3 py-1.5 text-sm text-[#0e2758] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none"
        >
          <option value="all">Pool: All</option>
          {pools.map((pool) => (
            <option key={pool.name} value={pool.name}>
              Pool: {pool.name}
            </option>
          ))}
        </select>

        <div ref={dropdownRef} className="relative">
          <button
            onClick={() => setPolicyDropdownOpen(!policyDropdownOpen)}
            className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-3 py-1.5 text-sm text-[#0e2758] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none"
          >
            {selectedPolicies.length === 0
              ? "All policies"
              : `${selectedPolicies.length} selected`}
          </button>
          {policyDropdownOpen && (
            <div className="absolute top-full left-0 z-10 mt-1 w-64 rounded-lg border border-[#d8d2bf] bg-[#fffef8] p-3 shadow-lg">
              <p className="text-sm text-[#4a5f8c]">
                Click on a policy name in the leaderboard or matches table to
                filter.
              </p>
            </div>
          )}
        </div>
      </div>

      {selectedPolicies.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="text-sm text-[#4a5f8c]">Filtering by:</span>
          {selectedPolicies.map((policy) => (
            <button
              key={policy.id}
              onClick={() => removePolicyFilter(policy.id)}
              className="inline-flex items-center gap-1 rounded bg-[#0e2758] px-2 py-1 text-xs text-white hover:bg-[#1a3a6e]"
            >
              {policy.label}
              <span className="ml-1">x</span>
            </button>
          ))}
        </div>
      )}

      <div
        ref={tableRef}
        className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6"
      >
        {loading ? (
          <p className="text-[#4a5f8c]">Loading...</p>
        ) : matches.length === 0 ? (
          <p className="text-[#4a5f8c]">No matches found.</p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <div className="min-w-[700px]">
                <Table fixed>
                  <THead>
                    <TH className="w-36">Date</TH>
                    <TH className="w-20">Replay</TH>
                    <TH className="w-24">Status</TH>
                    <TH className="w-28">Pool</TH>
                    <TH className="w-24">Agents</TH>
                    <TH>Policies</TH>
                    <TH className="w-16 text-right">Score</TH>
                  </THead>
                  <TBody>
                    {matches.map((match) => {
                      const replayUrl = match.episode_id
                        ? replayUrls.get(match.episode_id)
                        : undefined;
                      return (
                        <TR key={match.id}>
                          <TD className="w-36 align-top">
                            {new Date(match.created_at).toLocaleString([], {
                              month: "short",
                              day: "numeric",
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                          </TD>
                          <TD className="w-20 align-top">
                            {replayUrl ? (
                              <a
                                href={`${METTASCOPE_BASE_URL}?replay=${encodeURIComponent(replayUrl)}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-sm text-[#4a5f8c] underline hover:text-[#0e2758]"
                              >
                                Replay
                              </a>
                            ) : (
                              <span className="text-xs text-[#8a9bb8]">-</span>
                            )}
                          </TD>
                          <TD className="w-24 align-top">
                            <span
                              className={`rounded px-2 py-0.5 text-xs ${
                                match.status === "completed"
                                  ? "bg-green-100 text-green-800"
                                  : match.status === "failed"
                                    ? "bg-red-100 text-red-800"
                                    : "bg-yellow-100 text-yellow-800"
                              }`}
                            >
                              {match.status}
                            </span>
                          </TD>
                          <TD className="w-28 align-top">
                            <button
                              onClick={() => setPoolFilter(match.pool_name)}
                              className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 hover:bg-gray-200"
                            >
                              {match.pool_name}
                            </button>
                          </TD>
                          <TD className="w-24 align-top tabular-nums">
                            <div className="min-h-[2.75rem] space-y-1">
                              {match.players.map((player, i) => (
                                <div key={i} className="text-sm">
                                  {player.num_agents}
                                </div>
                              ))}
                            </div>
                          </TD>
                          <TD className="align-top">
                            <div className="min-h-[2.75rem] space-y-1">
                              {match.players.map((player, i) => (
                                <div key={i}>
                                  <PolicyTag
                                    policy={player.policy}
                                    onClick={() =>
                                      addPolicyFilter(player.policy.id)
                                    }
                                  />
                                </div>
                              ))}
                            </div>
                          </TD>
                          <TD className="w-16 text-right align-top tabular-nums">
                            <div className="min-h-[2.75rem] space-y-1">
                              {match.players.map((player, i) => (
                                <div key={i} className="text-sm">
                                  {player.score !== null
                                    ? player.score.toFixed(2)
                                    : "-"}
                                </div>
                              ))}
                            </div>
                          </TD>
                        </TR>
                      );
                    })}
                  </TBody>
                </Table>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-4 py-2 text-sm font-medium text-[#0e2758] transition-colors hover:bg-[#f5f3ed] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                Previous
              </button>
              <span className="text-sm text-[#4a5f8c]">Page {page + 1}</span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={!hasMore}
                className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-4 py-2 text-sm font-medium text-[#0e2758] transition-colors hover:bg-[#f5f3ed] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
