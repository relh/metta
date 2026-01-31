'use client'

import { FC, use, useEffect, useState } from 'react'

import { AppContext } from '@/app/(main)/AppContext'
import { Card } from '@/components/Card'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { EpisodeStatsResponse, PolicyStatsDetail } from '@/lib/repo'

function fmt(v: number | undefined): string {
  if (v === undefined) return '-'
  return Number.isInteger(v) ? v.toString() : v.toFixed(2)
}

export const GameStats: FC<{ attributes: Record<string, any> }> = ({ attributes }) => {
  const gameStats: Record<string, number> | undefined = attributes?.stats?.game
  if (!gameStats || Object.keys(gameStats).length === 0) return null

  return (
    <Card title="Game Stats">
      <div className="overflow-x-auto">
        <Table>
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
  )
}

const PolicyGroup: FC<{ policy: PolicyStatsDetail }> = ({ policy }) => {
  const [expanded, setExpanded] = useState(false)
  const metricNames = Object.keys(policy.avg_metrics).sort()
  const label = policy.policy_name
    ? `${policy.policy_name} v${policy.policy_version}`
    : `Policy position ${policy.position}`

  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="font-medium text-gray-900">{label}</span>
          <span className="ml-2 text-sm text-gray-500">({policy.num_agents} agents)</span>
        </div>
        <span className="font-mono text-sm">avg reward: {fmt(policy.avg_reward)}</span>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TH>Metric</TH>
            <TH>Average</TH>
          </TableHeader>
          <TableBody>
            {metricNames.map((name) => (
              <TR key={name}>
                <TD>{name}</TD>
                <TD>
                  <span className="font-mono">{fmt(policy.avg_metrics[name])}</span>
                </TD>
              </TR>
            ))}
          </TableBody>
        </Table>
      </div>

      <button onClick={() => setExpanded(!expanded)} className="mt-3 text-sm text-blue-600 hover:text-blue-800">
        {expanded ? 'Hide' : 'Show'} per-agent details ({policy.num_agents} agents)
      </button>

      {expanded && (
        <div className="mt-3 overflow-x-auto">
          <Table theme="inner">
            <TableHeader>
              <TH>Agent</TH>
              <TH>Reward</TH>
              {metricNames.map((name) => (
                <TH key={name}>{name}</TH>
              ))}
            </TableHeader>
            <TableBody>
              {policy.agents.map((agent) => (
                <TR key={agent.agent_id}>
                  <TD className="font-medium">Agent {agent.agent_id}</TD>
                  <TD>
                    <span className="font-mono">{fmt(agent.reward)}</span>
                  </TD>
                  {metricNames.map((name) => (
                    <TD key={name}>
                      <span className="font-mono">{fmt(agent.metrics[name])}</span>
                    </TD>
                  ))}
                </TR>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

const PolicyGroupedStats: FC<{ data: EpisodeStatsResponse }> = ({ data }) => {
  if (data.policy_stats.length === 0) return null

  return (
    <Card title="Agent Stats">
      <div className="space-y-4">
        {data.policy_stats.map((policy, idx) => (
          <PolicyGroup key={policy.policy_version_id ?? idx} policy={policy} />
        ))}
      </div>
    </Card>
  )
}

const UngroupedAgentStats: FC<{ attributes: Record<string, any> }> = ({ attributes }) => {
  const [expanded, setExpanded] = useState(false)
  const agentStats: Record<string, number>[] | undefined = attributes?.stats?.agent
  if (!agentStats || agentStats.length === 0) return null

  const metricNames = [...new Set(agentStats.flatMap(Object.keys))].sort()

  const averages: Record<string, number> = {}
  for (const name of metricNames) {
    let sum = 0
    let count = 0
    for (const agent of agentStats) {
      if (name in agent) {
        sum += agent[name]
        count++
      }
    }
    if (count > 0) averages[name] = sum / count
  }

  return (
    <Card title="Agent Stats">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TH>Metric</TH>
            <TH>Average</TH>
          </TableHeader>
          <TableBody>
            {metricNames.map((name) => (
              <TR key={name}>
                <TD>{name}</TD>
                <TD>
                  <span className="font-mono">{fmt(averages[name])}</span>
                </TD>
              </TR>
            ))}
          </TableBody>
        </Table>
      </div>

      <button onClick={() => setExpanded(!expanded)} className="mt-3 text-sm text-blue-600 hover:text-blue-800">
        {expanded ? 'Hide' : 'Show'} per-agent details ({agentStats.length} agents)
      </button>

      {expanded && (
        <div className="mt-3 overflow-x-auto">
          <Table theme="inner">
            <TableHeader>
              <TH>Agent</TH>
              {metricNames.map((name) => (
                <TH key={name}>{name}</TH>
              ))}
            </TableHeader>
            <TableBody>
              {agentStats.map((agent, idx) => (
                <TR key={idx}>
                  <TD className="font-medium">Agent {idx}</TD>
                  {metricNames.map((name) => (
                    <TD key={name}>
                      <span className="font-mono">{fmt(agent[name])}</span>
                    </TD>
                  ))}
                </TR>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </Card>
  )
}

export const AgentStats: FC<{ attributes: Record<string, any>; jobId?: string }> = ({ attributes, jobId }) => {
  const { repo } = use(AppContext)
  const [episodeStats, setEpisodeStats] = useState<EpisodeStatsResponse | null>(null)
  const [fetchFailed, setFetchFailed] = useState(false)

  useEffect(() => {
    if (!jobId) return
    let ignore = false
    repo
      .getJobEpisodeStats(jobId)
      .then((data) => {
        if (!ignore) setEpisodeStats(data)
      })
      .catch(() => {
        if (!ignore) setFetchFailed(true)
      })
    return () => {
      ignore = true
    }
  }, [repo, jobId])

  if (jobId && episodeStats) {
    return <PolicyGroupedStats data={episodeStats} />
  }

  if (jobId && !fetchFailed) {
    return null
  }

  return <UngroupedAgentStats attributes={attributes} />
}
