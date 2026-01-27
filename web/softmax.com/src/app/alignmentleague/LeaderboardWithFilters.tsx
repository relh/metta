"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { H2 } from "@/components/H2";
import { Table, TBody, TD, TH, THead, TR } from "@/components/Table";
import type {
  LeaderboardEntry,
  LeaderboardResponse,
  SeasonResponse,
} from "@/lib/observatoryClient";

import { PolicyTag } from "./PolicyTag";

export function LeaderboardWithFilters() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [seasons, setSeasons] = useState<SeasonResponse[]>([]);
  const [selectedSeason, setSelectedSeason] = useState("beta");
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchSeasons() {
      try {
        const res = await fetch("/api/tournament/seasons");
        if (!res.ok) throw new Error("Failed to fetch seasons");
        const data: SeasonResponse[] = await res.json();
        setSeasons(data);
        const beta = data.find((s) => s.name === "beta");
        if (!beta && data.length > 0) {
          setSelectedSeason(data[0].name);
        }
      } catch (err) {
        console.error(err);
      }
    }
    fetchSeasons();
  }, []);

  useEffect(() => {
    async function fetchLeaderboard() {
      if (!selectedSeason) return;
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(
          `/api/tournament/seasons/${encodeURIComponent(selectedSeason)}/leaderboard`,
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
  }, [selectedSeason, seasons]);

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
            onChange={(e) => setSelectedSeason(e.target.value)}
          >
            {seasons.map((season) => (
              <option key={season.name} value={season.name}>
                Season: {season.name}
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
