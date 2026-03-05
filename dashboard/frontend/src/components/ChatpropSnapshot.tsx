const SNAPSHOT_ITEMS = [
  {
    title: 'Transcript Catalog',
    detail: 'Branch-linked transcript indexing and archived session lookup.',
  },
  {
    title: 'Branch Analysis',
    detail: 'Context assembly and proposal synthesis across selected branches.',
  },
  {
    title: 'Flowchart Export',
    detail: 'Mermaid + JSON workflow graph export from baked catalog metadata.',
  },
]

const OPERATIONS = [
  'Archive local transcripts into ~/.chatprop',
  'Find branch-specific transcript context',
  'Generate weighted skill-flow charts',
  'Prepare merged-PR context snapshots',
]

export function ChatpropSnapshot() {
  return (
    <main className="service-snapshot-shell">
      <section className="service-snapshot-card">
        <p className="service-snapshot-kicker">Chatprop Snapshot</p>
        <h1 className="service-snapshot-title">Local-First Chat Workflow Catalog</h1>
        <p className="service-snapshot-subtitle">
          This host now serves a baked Chatprop snapshot page instead of booting the policy dashboard client.
        </p>
      </section>

      <section className="service-snapshot-grid">
        {SNAPSHOT_ITEMS.map((item) => (
          <article key={item.title} className="service-snapshot-card">
            <h2>{item.title}</h2>
            <p>{item.detail}</p>
          </article>
        ))}
      </section>

      <section className="service-snapshot-card">
        <h2>Included Operations</h2>
        <ul className="service-snapshot-list">
          {OPERATIONS.map((operation) => (
            <li key={operation}>{operation}</li>
          ))}
        </ul>
      </section>
    </main>
  )
}
