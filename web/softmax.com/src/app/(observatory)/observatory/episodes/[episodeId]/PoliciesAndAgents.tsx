"use client";

import { FC, use, useCallback, useEffect, useMemo, useState } from "react";

import { AppContext } from "@observatory-app/AppContext";
import { Card } from "@observatory/components/Card";
import { StyledLink } from "@observatory/components/StyledLink";
import {
  Table,
  TableBody,
  TableHeader,
  TD,
  TH,
  TR,
} from "@observatory/components/Table";
import {
  EpisodeStatsResponse,
  PolicyStatsDetail,
  PolicyVersionRow,
} from "@observatory/lib/repo";
import { policyVersionRoute } from "@observatory/lib/routes";
import { formatPolicyVersion } from "@observatory/utils/format";

function fmt(v: number | null | undefined): string {
  if (v == null) return "-";
  return Number.isInteger(v) ? v.toString() : v.toFixed(2);
}

type Sort = { key: string; desc: boolean };

function toggleSort(prev: Sort, key: string): Sort {
  if (prev.key === key) return { key, desc: !prev.desc };
  return { key, desc: false };
}

function numCmp(
  a: number | null | undefined,
  b: number | null | undefined,
): number {
  if (a == null && b == null) return 0;
  if (a == null) return -1;
  if (b == null) return 1;
  return a - b;
}

const SortTH: FC<
  React.ThHTMLAttributes<HTMLTableCellElement> & {
    sortKey: string;
    active: Sort;
    onSort: (key: string) => void;
  }
> = ({ sortKey, active, onSort, children, ...props }) => (
  <TH
    onClick={() => onSort(sortKey)}
    className="cursor-pointer whitespace-nowrap select-none"
    {...props}
  >
    <span className="inline-flex items-center gap-0.5">
      {children}
      <span className="text-foreground-muted text-[10px]">
        {active.key === sortKey
          ? active.desc
            ? "\u25BC"
            : "\u25B2"
          : "\u25B4\u25BE"}
      </span>
    </span>
  </TH>
);

export const GameStats: FC<{ attributes: Record<string, any> }> = ({
  attributes,
}) => {
  const gameStats: Record<string, number> | undefined = attributes?.stats?.game;
  if (!gameStats || Object.keys(gameStats).length === 0) return null;

  return (
    <Card title="Game Stats" padding="sm">
      <div className="overflow-x-auto">
        <Table theme="inner">
          <TableHeader>
            <TH>Metric</TH>
            <TH>Value</TH>
          </TableHeader>
          <TableBody>
            {Object.entries(gameStats)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([name, value]) => (
                <TR key={name}>
                  <TD>{name}</TD>
                  <TD>
                    <span className="font-mono">{fmt(value)}</span>
                  </TD>
                </TR>
              ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
};

function policyLabel(
  policy: PolicyStatsDetail,
  info?: PolicyVersionRow,
): string {
  if (info) return formatPolicyVersion(info);
  if (policy.policy_name)
    return `${policy.policy_name} v${policy.policy_version}`;
  return `Policy position ${policy.position}`;
}

function policyMetric(
  p: PolicyStatsDetail,
  metric: string,
): number | null | undefined {
  return metric === "reward" ? p.avg_reward : p.avg_metrics[metric];
}

function generateCsv(policies: PolicyStatsDetail[], labels: string[]): string {
  const allMetrics = [
    ...new Set(policies.flatMap((p) => Object.keys(p.avg_metrics))),
  ].sort();

  let csv = `metric,${labels.join(",")}\n`;
  csv += `reward,${policies.map((p) => fmt(p.avg_reward)).join(",")}\n`;
  for (const m of allMetrics) {
    csv += `${m},${policies.map((p) => fmt(p.avg_metrics[m])).join(",")}\n`;
  }

  csv += `\nagent_id,policy,reward,${allMetrics.join(",")}\n`;
  for (let i = 0; i < policies.length; i++) {
    for (const agent of policies[i].agents) {
      csv += `${agent.agent_id},${labels[i]},${fmt(agent.reward)},${allMetrics.map((m) => fmt(agent.metrics[m])).join(",")}\n`;
    }
  }

  return csv;
}

function downloadBlob(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

const SortablePolicyHeader: FC<{
  policy: PolicyStatsDetail;
  info?: PolicyVersionRow;
  sortKey: string;
  active: Sort;
  onSort: (key: string) => void;
}> = ({ policy, info, sortKey, active, onSort }) => {
  const label = policyLabel(policy, info);
  return (
    <SortTH sortKey={sortKey} active={active} onSort={onSort}>
      <div className="flex flex-col gap-0.5">
        {policy.policy_version_id && info ? (
          <StyledLink href={policyVersionRoute(policy.policy_version_id)}>
            {label}
          </StyledLink>
        ) : (
          <span>{label}</span>
        )}
        <span className="text-foreground-muted font-normal">
          {policy.num_agents} agents
        </span>
      </div>
    </SortTH>
  );
};

const Section: FC<
  React.PropsWithChildren<{
    label: string;
    count: string;
    open: boolean;
    onToggle: () => void;
  }>
> = ({ label, count, open, onToggle, children }) => (
  <div>
    <button
      onClick={onToggle}
      className="text-foreground-subtle hover:text-foreground flex items-center gap-1 py-1 text-xs"
    >
      <span className="text-[10px]">{open ? "\u25BC" : "\u25B6"}</span>
      <span className="font-medium">{label}</span>
      <span className="text-foreground-muted">({count})</span>
    </button>
    {open && <div className="mt-1">{children}</div>}
  </div>
);

export const PoliciesAndAgents: FC<{ jobId?: string }> = ({ jobId }) => {
  const { repo } = use(AppContext);
  const [episodeStats, setEpisodeStats] = useState<EpisodeStatsResponse | null>(
    null,
  );
  const [policyInfo, setPolicyInfo] = useState<
    Record<string, PolicyVersionRow>
  >({});
  const [showMetrics, setShowMetrics] = useState(false);
  const [showAgents, setShowAgents] = useState(false);
  const [metricFilter, setMetricFilter] = useState("");
  const [metricSort, setMetricSort] = useState<Sort>({
    key: "name",
    desc: false,
  });
  const [agentSort, setAgentSort] = useState<Sort>({
    key: "agent_id",
    desc: false,
  });

  useEffect(() => {
    if (!jobId) return;
    let ignore = false;
    repo
      .getJobEpisodeStats(jobId)
      .then((data) => {
        if (ignore) return;
        setEpisodeStats(data);
        const ids = data.policy_stats
          .map((p) => p.policy_version_id)
          .filter((id): id is string => id != null);
        if (ids.length > 0) {
          repo
            .getPolicyVersionsBatch(ids)
            .then((versions) => {
              if (ignore) return;
              const map: Record<string, PolicyVersionRow> = {};
              for (const v of versions) map[v.id] = v;
              setPolicyInfo(map);
            })
            .catch(() => {});
        }
      })
      .catch(() => {});
    return () => {
      ignore = true;
    };
  }, [repo, jobId]);

  const policies = episodeStats?.policy_stats ?? [];
  const labels = useMemo(
    () =>
      policies.map((p) =>
        policyLabel(
          p,
          p.policy_version_id ? policyInfo[p.policy_version_id] : undefined,
        ),
      ),
    [policies, policyInfo],
  );
  const allMetricNames = useMemo(
    () => [
      "reward",
      ...[
        ...new Set(policies.flatMap((p) => Object.keys(p.avg_metrics))),
      ].sort(),
    ],
    [policies],
  );

  const filteredMetrics = useMemo(() => {
    if (!metricFilter) return allMetricNames;
    const q = metricFilter.toLowerCase();
    return allMetricNames.filter((m) => m.toLowerCase().includes(q));
  }, [allMetricNames, metricFilter]);

  const sortedMetrics = useMemo(() => {
    const rows = [...filteredMetrics];
    if (metricSort.key === "name") {
      rows.sort((a, b) => a.localeCompare(b));
    } else {
      const pIdx = parseInt(metricSort.key.split(":")[1]);
      if (pIdx < policies.length) {
        rows.sort((a, b) =>
          numCmp(
            policyMetric(policies[pIdx], a),
            policyMetric(policies[pIdx], b),
          ),
        );
      }
    }
    if (metricSort.desc) rows.reverse();
    return rows;
  }, [filteredMetrics, metricSort, policies]);

  const sortedAgents = useMemo(() => {
    const agents = policies.flatMap((p, pIdx) =>
      p.agents.map((a) => ({ ...a, pIdx })),
    );
    agents.sort((a, b) => {
      let cmp: number;
      switch (agentSort.key) {
        case "agent_id":
          cmp = a.agent_id - b.agent_id;
          break;
        case "policy":
          cmp = a.pIdx - b.pIdx;
          break;
        case "reward":
          cmp = numCmp(a.reward, b.reward);
          break;
        default:
          cmp = numCmp(a.metrics[agentSort.key], b.metrics[agentSort.key]);
      }
      return agentSort.desc ? -cmp : cmp;
    });
    return agents;
  }, [policies, agentSort]);

  const onMetricSort = useCallback(
    (key: string) => setMetricSort((s) => toggleSort(s, key)),
    [],
  );
  const onAgentSort = useCallback(
    (key: string) => setAgentSort((s) => toggleSort(s, key)),
    [],
  );

  if (!jobId) return null;
  if (!episodeStats) return null;

  if (policies.length === 0) {
    return (
      <Card title="Policies & Agents" padding="sm">
        <div className="text-foreground-muted text-xs">
          No policy data available.
        </div>
      </Card>
    );
  }

  const totalAgents = policies.reduce((s, p) => s + p.num_agents, 0);
  const agentMetricCols = allMetricNames.filter((m) => m !== "reward");

  return (
    <Card title="Policies & Agents" padding="sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <input
          type="text"
          value={metricFilter}
          onChange={(e) => setMetricFilter(e.target.value)}
          placeholder="Filter metrics..."
          className="border-border bg-surface text-foreground w-48 rounded border px-2 py-0.5 text-xs focus:border-blue-400 focus:outline-none"
        />
        <button
          onClick={() =>
            downloadBlob(generateCsv(policies, labels), "episode-stats.csv")
          }
          className="text-xs whitespace-nowrap text-blue-600 hover:text-blue-800"
        >
          Download CSV
        </button>
      </div>

      <div className="space-y-2">
        <Section
          label="Policy Averages"
          count={`${policies.length} policies, ${sortedMetrics.length} metrics`}
          open={showMetrics}
          onToggle={() => setShowMetrics((v) => !v)}
        >
          <div className="overflow-x-auto">
            <Table theme="inner">
              <TableHeader>
                <SortTH
                  sortKey="name"
                  active={metricSort}
                  onSort={onMetricSort}
                >
                  Metric
                </SortTH>
                {policies.map((p, i) => (
                  <SortablePolicyHeader
                    key={p.policy_version_id ?? p.position}
                    policy={p}
                    info={
                      p.policy_version_id
                        ? policyInfo[p.policy_version_id]
                        : undefined
                    }
                    sortKey={`p:${i}`}
                    active={metricSort}
                    onSort={onMetricSort}
                  />
                ))}
              </TableHeader>
              <TableBody>
                {sortedMetrics.map((name) => (
                  <TR key={name}>
                    <TD className={name === "reward" ? "font-medium" : ""}>
                      {name}
                    </TD>
                    {policies.map((p) => (
                      <TD key={p.policy_version_id ?? p.position}>
                        <span className="font-mono">
                          {fmt(policyMetric(p, name))}
                        </span>
                      </TD>
                    ))}
                  </TR>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>

        <Section
          label="Per-Agent Details"
          count={`${totalAgents} agents`}
          open={showAgents}
          onToggle={() => setShowAgents((v) => !v)}
        >
          <div className="overflow-x-auto">
            <Table theme="inner">
              <TableHeader>
                <SortTH
                  sortKey="agent_id"
                  active={agentSort}
                  onSort={onAgentSort}
                >
                  Agent
                </SortTH>
                <SortTH
                  sortKey="policy"
                  active={agentSort}
                  onSort={onAgentSort}
                >
                  Policy
                </SortTH>
                <SortTH
                  sortKey="reward"
                  active={agentSort}
                  onSort={onAgentSort}
                >
                  Reward
                </SortTH>
                {agentMetricCols.map((name) => (
                  <SortTH
                    key={name}
                    sortKey={name}
                    active={agentSort}
                    onSort={onAgentSort}
                  >
                    {name}
                  </SortTH>
                ))}
              </TableHeader>
              <TableBody>
                {sortedAgents.map((agent) => (
                  <TR key={agent.agent_id}>
                    <TD className="font-medium">Agent {agent.agent_id}</TD>
                    <TD className="text-foreground-muted">
                      {labels[agent.pIdx]}
                    </TD>
                    <TD>
                      <span className="font-mono">{fmt(agent.reward)}</span>
                    </TD>
                    {agentMetricCols.map((name) => (
                      <TD key={name}>
                        <span className="font-mono">
                          {fmt(agent.metrics[name])}
                        </span>
                      </TD>
                    ))}
                  </TR>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      </div>
    </Card>
  );
};
