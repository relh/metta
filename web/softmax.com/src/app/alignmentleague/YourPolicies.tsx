"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useCallback, useMemo, useState } from "react";

import { H2 } from "@/components/H2";
import { Table, TBody, TD, TH, THead, TR } from "@/components/Table";
import type {
  MembershipHistoryEntry,
  PolicySummary,
} from "@/lib/observatoryClient";

import { PolicyTag } from "./PolicyTag";

export function YourPolicies({ policies }: { policies: PolicySummary[] }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [expandedPolicyId, setExpandedPolicyId] = useState<string | null>(null);
  const [membershipHistory, setMembershipHistory] = useState<
    MembershipHistoryEntry[]
  >([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [selectedSeason, setSelectedSeason] = useState<string>("__all__");
  const [selectedVersion, setSelectedVersion] = useState<string>("__all__");

  const seasonOptions = useMemo(() => {
    const unique = [...new Set(membershipHistory.map((m) => m.season_name))];
    return unique.sort();
  }, [membershipHistory]);

  const seasonVersions = useMemo(() => {
    const map = new Map<string, number[]>();
    for (const entry of membershipHistory) {
      if (entry.season_version === null) continue;
      const existing = map.get(entry.season_name) ?? [];
      if (!existing.includes(entry.season_version)) {
        existing.push(entry.season_version);
      }
      map.set(entry.season_name, existing);
    }
    for (const [season, versions] of map.entries()) {
      versions.sort((a, b) => b - a);
      map.set(season, versions);
    }
    return map;
  }, [membershipHistory]);

  const versionOptions = useMemo(() => {
    if (selectedSeason === "__all__") {
      return [];
    }
    return seasonVersions.get(selectedSeason) ?? [];
  }, [seasonVersions, selectedSeason]);

  const filteredHistory = useMemo(
    () =>
      membershipHistory.filter((m) => {
        if (selectedSeason !== "__all__" && m.season_name !== selectedSeason) {
          return false;
        }
        if (selectedVersion !== "__all__") {
          return m.season_version === Number(selectedVersion);
        }
        return true;
      }),
    [membershipHistory, selectedSeason, selectedVersion],
  );

  const addPolicyFilter = useCallback(
    (policyId: string) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.get("policies")?.split(",").filter(Boolean) ?? [];
      if (!current.includes(policyId)) {
        current.push(policyId);
        params.set("policies", current.join(","));
        router.push(`?${params.toString()}#recent-matches`, { scroll: true });
      }
    },
    [router, searchParams],
  );

  const toggleExpand = useCallback(
    async (policyId: string) => {
      if (expandedPolicyId === policyId) {
        setExpandedPolicyId(null);
        setMembershipHistory([]);
        return;
      }

      setExpandedPolicyId(policyId);
      setLoadingHistory(true);
      setMembershipHistory([]);
      setSelectedSeason("__all__");
      setSelectedVersion("__all__");

      try {
        const res = await fetch(
          `/api/tournament/policies/${policyId}/memberships`,
        );
        if (res.ok) {
          const data = await res.json();
          setMembershipHistory(Array.isArray(data) ? data : []);
        }
      } catch (err) {
        console.error("Failed to fetch membership history:", err);
      } finally {
        setLoadingHistory(false);
      }
    },
    [expandedPolicyId],
  );

  return (
    <section className="mt-8">
      <H2>Your Policies</H2>
      <p className="mb-4 text-sm text-[#4a5f8c]">
        See the{" "}
        <a
          href="https://github.com/Metta-AI/cogames"
          className="underline hover:text-[#0e2758]"
          target="_blank"
          rel="noopener noreferrer"
        >
          README
        </a>{" "}
        for how to upload and submit policies.
      </p>
      <div className="rounded-2xl border border-[#d8d2bf] bg-[#fffef8] p-6">
        {policies.length === 0 ? (
          <p className="text-[#8a9bb8]">No policies submitted yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <div className="min-w-[500px]">
              <Table>
                <THead>
                  <TH>Policy</TH>
                  <TH>Pools</TH>
                  <TH>Entered</TH>
                </THead>
                <TBody>
                  {policies.map((p) => (
                    <Fragment key={p.policy.id}>
                      <TR
                        className={
                          expandedPolicyId === p.policy.id ? "bg-[#f5f3ed]" : ""
                        }
                      >
                        <TD>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={() => toggleExpand(p.policy.id)}
                              className="text-[#4a5f8c] hover:text-[#0e2758]"
                              title={
                                expandedPolicyId === p.policy.id
                                  ? "Collapse"
                                  : "Expand"
                              }
                            >
                              {expandedPolicyId === p.policy.id ? "v" : ">"}
                            </button>
                            <PolicyTag
                              policy={p.policy}
                              onClick={() => addPolicyFilter(p.policy.id)}
                            />
                          </div>
                        </TD>
                        <TD>
                          <div className="flex flex-wrap gap-1">
                            {p.pools.map((pool) => (
                              <span
                                key={pool.pool_name}
                                className={`rounded px-2 py-0.5 text-xs ${
                                  pool.active
                                    ? "bg-green-100 text-green-800"
                                    : "bg-gray-100 text-gray-600"
                                }`}
                              >
                                {pool.pool_name}
                                {pool.completed > 0 && (
                                  <span className="ml-1">{pool.completed}</span>
                                )}
                              </span>
                            ))}
                          </div>
                        </TD>
                        <TD>{new Date(p.entered_at).toLocaleDateString()}</TD>
                      </TR>
                      {expandedPolicyId === p.policy.id && (
                        <tr>
                          <td colSpan={3} className="bg-[#f9f8f4] px-4 py-3">
                            {loadingHistory ? (
                              <p className="text-sm text-[#4a5f8c]">
                                Loading history...
                              </p>
                            ) : membershipHistory.length === 0 ? (
                              <p className="text-sm text-[#8a9bb8]">
                                No membership changes recorded.
                              </p>
                            ) : (
                              <div className="space-y-2">
                                <div className="flex items-center gap-3">
                                  <p className="text-xs font-medium text-[#4a5f8c]">
                                    Membership History
                                  </p>
                                  {seasonOptions.length > 1 && (
                                    <select
                                      value={selectedSeason}
                                      onChange={(e) => {
                                        setSelectedSeason(e.target.value);
                                        setSelectedVersion("__all__");
                                      }}
                                      className="rounded border border-[#d8d2bf] bg-white px-2 py-0.5 text-xs text-[#4a5f8c]"
                                    >
                                      <option value="__all__">
                                        All seasons
                                      </option>
                                      {seasonOptions.map((s) => (
                                        <option key={s} value={s}>
                                          {s}
                                        </option>
                                      ))}
                                    </select>
                                  )}
                                  {selectedSeason !== "__all__" &&
                                    versionOptions.length > 0 && (
                                      <select
                                        value={selectedVersion}
                                        onChange={(e) =>
                                          setSelectedVersion(e.target.value)
                                        }
                                        className="rounded border border-[#d8d2bf] bg-white px-2 py-0.5 text-xs text-[#4a5f8c]"
                                      >
                                        <option value="__all__">
                                          All versions
                                        </option>
                                        {versionOptions.map((version) => (
                                          <option
                                            key={version}
                                            value={String(version)}
                                          >
                                            v{version}
                                          </option>
                                        ))}
                                      </select>
                                    )}
                                </div>
                                <div className="space-y-1">
                                  {filteredHistory.map((entry, i) => (
                                    <div
                                      key={i}
                                      className="flex items-center gap-3 text-sm"
                                    >
                                      <span className="text-xs text-[#8a9bb8]">
                                        {new Date(
                                          entry.created_at,
                                        ).toLocaleDateString()}
                                      </span>
                                      <span
                                        className={`rounded px-2 py-0.5 text-xs ${
                                          entry.action === "add"
                                            ? "bg-green-100 text-green-800"
                                            : entry.action === "remove"
                                              ? "bg-red-100 text-red-800"
                                              : "bg-gray-100 text-gray-600"
                                        }`}
                                      >
                                        {entry.action}
                                      </span>
                                      <span className="text-xs text-[#8a9bb8]">
                                        {entry.season_version
                                          ? `${entry.season_name} v${entry.season_version}`
                                          : entry.season_name}
                                      </span>
                                      <span className="text-[#0e2758]">
                                        {entry.pool_name}
                                      </span>
                                      {entry.notes && (
                                        <span className="text-[#8a9bb8]">
                                          - {entry.notes}
                                        </span>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
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
