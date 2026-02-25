"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { H2 } from "@/components/H2";
import { Table, TBody, TD, TH, THead, TR } from "@/components/Table";
import type {
  LeaderboardEntry,
  LeaderboardResponse,
  SeasonSummary,
  SeasonVersionInfo,
} from "@/lib/observatoryClient";

import { PolicyTag } from "./PolicyTag";

export function LeaderboardWithFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [seasons, setSeasons] = useState<SeasonSummary[]>([]);
  const [selectedSeason, setSelectedSeason] = useState("");
  const [seasonVersions, setSeasonVersions] = useState<SeasonVersionInfo[]>([]);
  const [selectedVersion, setSelectedVersion] =
    useState<SeasonVersionInfo | null>(null);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const seasonParam = searchParams.get("season") ?? "";
  const versionParam = searchParams.get("version") ?? "";

  const encodeSeasonRef = (value: string) => {
    try {
      return encodeURIComponent(decodeURIComponent(value));
    } catch {
      return encodeURIComponent(value);
    }
  };

  const updateSearchParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(updates)) {
        if (!value) {
          params.delete(key);
        } else {
          params.set(key, value);
        }
      }
      router.push(`?${params.toString()}`, { scroll: false });
    },
    [router, searchParams],
  );

  useEffect(() => {
    async function fetchSeasons() {
      try {
        const res = await fetch("/api/tournament/seasons");
        if (!res.ok) throw new Error("Failed to fetch seasons");
        const data: SeasonSummary[] = await res.json();
        setSeasons(data);
        const defaultSeason = data.find((s) => s.is_default) ?? data[0];
        if (defaultSeason) {
          setSelectedSeason(defaultSeason.name);
        }
      } catch (err) {
        console.error(err);
      }
    }
    fetchSeasons();
  }, []);

  useEffect(() => {
    if (seasons.length === 0) return;
    const defaultSeason = seasons.find((s) => s.is_default) ?? seasons[0];
    const validParam = seasonParam
      ? seasons.find((s) => s.name === seasonParam)
      : undefined;
    const desiredSeason = validParam?.name || defaultSeason?.name || "";
    if (desiredSeason && desiredSeason !== selectedSeason) {
      setSelectedSeason(desiredSeason);
    }
    if ((!seasonParam || !validParam) && desiredSeason) {
      updateSearchParams({ season: desiredSeason });
    }
  }, [seasons, seasonParam, selectedSeason, updateSearchParams]);

  useEffect(() => {
    async function fetchVersions() {
      if (!selectedSeason) {
        setSeasonVersions([]);
        setSelectedVersion(null);
        return;
      }
      setSeasonVersions([]);
      setSelectedVersion(null);
      setLoadingVersions(true);
      try {
        const res = await fetch(
          `/api/tournament/seasons/${encodeSeasonRef(selectedSeason)}/versions`,
        );
        if (!res.ok) throw new Error("Failed to fetch season versions");
        const data: SeasonVersionInfo[] = await res.json();
        setSeasonVersions(data);
        if (data.length > 0) {
          const requested = versionParam
            ? data.find((v) => v.version === Number(versionParam))
            : undefined;
          const canonical = data.find((v) => v.canonical) ?? data[0];
          if (versionParam && !requested) {
            updateSearchParams({ version: null });
          }
          setSelectedVersion(requested ?? canonical);
        }
      } catch (err) {
        console.error(err);
        setSeasonVersions([]);
        setSelectedVersion(null);
      } finally {
        setLoadingVersions(false);
      }
    }
    fetchVersions();
  }, [selectedSeason, updateSearchParams, versionParam]);

  const seasonRef = versionParam
    ? `${selectedSeason}:v${versionParam}`
    : selectedSeason;

  useEffect(() => {
    async function fetchLeaderboard() {
      if (!selectedSeason) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/tournament/seasons/${encodeSeasonRef(seasonRef)}/leaderboard`,
        );
        if (!res.ok) throw new Error("Failed to fetch leaderboard");
        const data: LeaderboardResponse = await res.json();
        setLeaderboard(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    fetchLeaderboard();
  }, [seasonRef, selectedSeason, seasons]);

  const addPolicyFilter = useCallback(
    (policyId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.get("policies")?.split(",").filter(Boolean) ?? [];
      if (!current.includes(policyId)) {
        current.push(policyId);
        params.set("policies", current.join(","));
        router.push(`?${params.toString()}`, { scroll: false });
      }
    },
    [router, searchParams],
  );

  if (error) {
    return (
      <section>
        <H2>Leaderboard</H2>
        <p className="text-red-500">Failed to load leaderboard.</p>
      </section>
    );
  }

  return (
    <section>
      <div className="mb-4 flex items-center gap-4">
        <H2>Leaderboard</H2>
        {seasons.length > 1 && (
          <select
            className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-3 py-1.5 text-sm font-medium text-[#0e2758] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none"
            value={selectedSeason}
            onChange={(e) => {
              const next = e.target.value;
              setSelectedSeason(next);
              setSelectedVersion(null);
              updateSearchParams({ season: next, version: null });
            }}
          >
            {seasons.map((season) => (
              <option key={season.name} value={season.name}>
                Season: {season.name}
              </option>
            ))}
          </select>
        )}
        {selectedSeason && (
          <select
            className="rounded-lg border border-[#d8d2bf] bg-[#fffef8] px-3 py-1.5 text-sm font-medium text-[#0e2758] focus:ring-2 focus:ring-[#4a5f8c] focus:outline-none"
            value={selectedVersion?.version ?? ""}
            onChange={(e) => {
              const next = Number(e.target.value);
              const version = seasonVersions.find((v) => v.version === next);
              setSelectedVersion(version ?? null);
              updateSearchParams({
                version: version ? String(version.version) : null,
              });
            }}
            disabled={!selectedSeason || loadingVersions}
          >
            <option value="">Version</option>
            {seasonVersions
              .slice()
              .sort((a, b) => b.version - a.version)
              .map((version) => (
                <option key={version.version} value={version.version}>
                  {`v${version.version}${version.canonical ? " (current)" : ""}`}
                </option>
              ))}
          </select>
        )}
      </div>
      <div className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
        {loading ? (
          <p className="text-[#4a5f8c]">Loading...</p>
        ) : leaderboard.length === 0 ? (
          <p className="text-[#4a5f8c]">No entries yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[600px]">
              <Table>
                <THead>
                  <TH>Rank</TH>
                  <TH>Score</TH>
                  <TH>Policy</TH>
                  <TH>Matches</TH>
                </THead>
                <TBody>
                  {leaderboard.map((entry) => (
                    <TR key={entry.policy.id}>
                      <TD>{entry.rank}</TD>
                      <TD>{entry.score.toFixed(2)}</TD>
                      <TD>
                        <PolicyTag
                          policy={entry.policy}
                          onClick={() => addPolicyFilter(entry.policy.id)}
                        />
                      </TD>
                      <TD>{entry.matches}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
