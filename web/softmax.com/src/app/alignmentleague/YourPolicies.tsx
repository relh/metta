"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useCallback, useState } from "react";

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
                                <p className="text-xs font-medium text-[#4a5f8c]">
                                  Membership History
                                </p>
                                <div className="space-y-1">
                                  {membershipHistory.map((entry, i) => (
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
