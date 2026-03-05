const GENERATED_AT = '2026-03-04T20:25:16Z'

type TrainBoardBet = {
  gid: string
  title: string
  score: number
  avgAxis: number
  avgExecution: number
  url: string
}

const TOP_BETS: TrainBoardBet[] = [
  {
    gid: '1209437894242831',
    title: 'Robust Autonomy Emerges from Self-Play',
    score: 0.773,
    avgAxis: 0.875,
    avgExecution: 0.583,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1209437894242831',
  },
  {
    gid: '1209513563278634',
    title: 'Muesli: Combining Improvements in Policy Optimization',
    score: 0.733,
    avgAxis: 0.8,
    avgExecution: 0.608,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1209513563278634',
  },
  {
    gid: '1210921009975327',
    title: 'TD-MPC2: Scalable, Robust World Models for Continuous Control',
    score: 0.729,
    avgAxis: 0.825,
    avgExecution: 0.55,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1210921009975327',
  },
  {
    gid: '1209054170992938',
    title: 'AlphaStar: Grandmaster level in StarCraft II using multi-agent reinforcement learning',
    score: 0.728,
    avgAxis: 0.85,
    avgExecution: 0.5,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1209054170992938',
  },
  {
    gid: '1209592012031656',
    title: 'How To Scale Your (Transformer) Model',
    score: 0.723,
    avgAxis: 0.817,
    avgExecution: 0.55,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1209592012031656',
  },
  {
    gid: '1210972187414436',
    title: 'Podracer architectures for scalable Reinforcement Learning',
    score: 0.713,
    avgAxis: 0.783,
    avgExecution: 0.583,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1210972187414436',
  },
  {
    gid: '1210532704990699',
    title: 'Multi-Agent Reinforcement Learning: Foundations and Modern Approaches',
    score: 0.713,
    avgAxis: 0.8,
    avgExecution: 0.55,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1210532704990699',
  },
  {
    gid: '1209043561580286',
    title: 'Human-Timescale Adaptation in an Open-Ended Task Space (ADA)',
    score: 0.712,
    avgAxis: 0.817,
    avgExecution: 0.517,
    url: 'https://app.asana.com/1/1209016784099267/project/1209041170403476/task/1209043561580286',
  },
]

function asPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function TrainBoardSnapshot() {
  return (
    <main className="service-snapshot-shell">
      <section className="service-snapshot-card">
        <p className="service-snapshot-kicker">Train Board Snapshot</p>
        <h1 className="service-snapshot-title">Top Ranked Research Bets</h1>
        <p className="service-snapshot-subtitle">
          This host now serves baked-in Train Board data directly, without loading policy-dashboard APIs.
        </p>
        <p className="service-snapshot-meta">
          Generated from committed cache data at <code>{GENERATED_AT}</code>.
        </p>
      </section>

      <section className="service-snapshot-card service-snapshot-table-wrap">
        <table className="service-snapshot-table">
          <thead>
            <tr>
              <th>Task</th>
              <th>Blended</th>
              <th>Impact</th>
              <th>Execution</th>
            </tr>
          </thead>
          <tbody>
            {TOP_BETS.map((bet) => (
              <tr key={bet.gid}>
                <td>
                  <a href={bet.url} target="_blank" rel="noreferrer">
                    {bet.title}
                  </a>
                </td>
                <td>{asPercent(bet.score)}</td>
                <td>{asPercent(bet.avgAxis)}</td>
                <td>{asPercent(bet.avgExecution)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  )
}
