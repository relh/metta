import { type ReactNode, useEffect, useMemo, useState } from 'react'

import { type DashboardEpisode, type DashboardResponse } from '../lib/api'

type EpisodeLookup = Map<string, DashboardEpisode>
type OpponentStats = DashboardResponse['derived']['opponent_metrics']

type AnalysisToken =
  | { kind: 'text'; value: string }
  | { kind: 'episode'; value: string; episodeId: string }
  | { kind: 'opponent'; value: string; opponentName: string }

type AnalysisBlock =
  | { kind: 'heading'; level: 2 | 3; text: string }
  | { kind: 'unordered-list'; items: string[] }
  | { kind: 'ordered-list'; items: string[] }
  | { kind: 'paragraph'; text: string }

const EPISODE_ID_RE = /\b([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|[0-9a-f]{8})\b/gi

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function buildEpisodeLookup(episodes: DashboardEpisode[]): EpisodeLookup {
  const lookup: EpisodeLookup = new Map()
  const prefixCounts = new Map<string, number>()
  for (const episode of episodes) {
    const id = String(episode.episode_id || '').toLowerCase()
    if (!id) continue
    lookup.set(id, episode)
    const prefix = id.slice(0, 8)
    prefixCounts.set(prefix, (prefixCounts.get(prefix) ?? 0) + 1)
  }

  for (const episode of episodes) {
    const id = String(episode.episode_id || '').toLowerCase()
    if (!id) continue
    const prefix = id.slice(0, 8)
    if ((prefixCounts.get(prefix) ?? 0) === 1) {
      lookup.set(prefix, episode)
    }
  }

  return lookup
}

function tokenizeEpisodeRefs(line: string, episodeLookup: EpisodeLookup): AnalysisToken[] {
  const tokens: AnalysisToken[] = []
  const regex = new RegExp(EPISODE_ID_RE.source, 'gi')
  let lastIndex = 0
  for (const match of line.matchAll(regex)) {
    const raw = match[0]
    const start = match.index ?? 0
    const end = start + raw.length
    const episode = episodeLookup.get(raw.toLowerCase())
    if (!episode) continue
    if (start > lastIndex) {
      tokens.push({ kind: 'text', value: line.slice(lastIndex, start) })
    }
    tokens.push({ kind: 'episode', value: raw, episodeId: episode.episode_id })
    lastIndex = end
  }
  if (lastIndex < line.length) {
    tokens.push({ kind: 'text', value: line.slice(lastIndex) })
  }
  if (tokens.length === 0) {
    return [{ kind: 'text', value: line }]
  }
  return tokens
}

function tokenizeOpponents(tokens: AnalysisToken[], opponentStats: OpponentStats): AnalysisToken[] {
  const names = Object.keys(opponentStats)
  if (names.length === 0) return tokens
  const nameLookup = new Map(names.map((name) => [name.toLowerCase(), name]))
  const pattern = names
    .sort((a, b) => b.length - a.length)
    .map(escapeRegex)
    .join('|')
  if (!pattern) return tokens
  const regex = new RegExp(`\\b(${pattern})\\b`, 'gi')

  const next: AnalysisToken[] = []
  for (const token of tokens) {
    if (token.kind !== 'text') {
      next.push(token)
      continue
    }
    const value = token.value
    let lastIndex = 0
    let matched = false
    for (const match of value.matchAll(regex)) {
      const raw = match[0]
      const start = match.index ?? 0
      const end = start + raw.length
      const opponentName = nameLookup.get(raw.toLowerCase())
      if (!opponentName) continue
      matched = true
      if (start > lastIndex) {
        next.push({ kind: 'text', value: value.slice(lastIndex, start) })
      }
      next.push({ kind: 'opponent', value: raw, opponentName })
      lastIndex = end
    }
    if (!matched) {
      next.push(token)
      continue
    }
    if (lastIndex < value.length) {
      next.push({ kind: 'text', value: value.slice(lastIndex) })
    }
  }
  return next
}

function parseBlocks(text: string): AnalysisBlock[] {
  const lines = text.split(/\r?\n/)
  const blocks: AnalysisBlock[] = []
  let paragraphLines: string[] = []
  let unorderedItems: string[] = []
  let orderedItems: string[] = []

  const flushParagraph = () => {
    if (paragraphLines.length === 0) return
    blocks.push({ kind: 'paragraph', text: paragraphLines.join(' ').trim() })
    paragraphLines = []
  }
  const flushUnordered = () => {
    if (unorderedItems.length === 0) return
    blocks.push({ kind: 'unordered-list', items: unorderedItems })
    unorderedItems = []
  }
  const flushOrdered = () => {
    if (orderedItems.length === 0) return
    blocks.push({ kind: 'ordered-list', items: orderedItems })
    orderedItems = []
  }
  const flushAll = () => {
    flushParagraph()
    flushUnordered()
    flushOrdered()
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) {
      flushAll()
      continue
    }

    const heading3 = line.match(/^###\s+(.+)$/)
    if (heading3) {
      flushAll()
      blocks.push({ kind: 'heading', level: 3, text: heading3[1] })
      continue
    }

    const heading2 = line.match(/^##?\s+(.+)$/)
    if (heading2) {
      flushAll()
      blocks.push({ kind: 'heading', level: 2, text: heading2[1] })
      continue
    }

    const unordered = line.match(/^[-*]\s+(.+)$/)
    if (unordered) {
      flushParagraph()
      flushOrdered()
      unorderedItems.push(unordered[1])
      continue
    }

    const ordered = line.match(/^\d+\.\s+(.+)$/)
    if (ordered) {
      flushParagraph()
      flushUnordered()
      orderedItems.push(ordered[1])
      continue
    }

    flushUnordered()
    flushOrdered()
    paragraphLines.push(line)
  }

  flushAll()
  return blocks
}

function formatNumber(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '-'
  return value.toFixed(digits)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function EpisodeChip({ value, episode }: { value: string; episode: DashboardEpisode }): ReactNode {
  const [expanded, setExpanded] = useState(false)
  const replayUrl = typeof episode.replay_url === 'string' && episode.replay_url.trim() ? episode.replay_url : null
  return (
    <span style={{ display: 'inline-block' }}>
      <button
        type="button"
        onClick={() => setExpanded((open) => !open)}
        style={{
          border: '1px solid var(--panel-soft-border)',
          borderRadius: 999,
          background: 'var(--panel-soft-bg-2)',
          padding: '1px 8px',
          fontSize: 12,
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          cursor: 'pointer',
          color: 'inherit',
        }}
      >
        {value}
      </button>
      {expanded && (
        <span
          style={{
            display: 'block',
            marginTop: 6,
            marginBottom: 8,
            marginLeft: 8,
            paddingLeft: 8,
            borderLeft: '2px solid var(--panel-soft-border)',
            fontSize: 12,
          }}
        >
          <span style={{ display: 'block' }}>
            with teammate <strong>{String(episode.opponent_name ?? '-')}</strong> (
            {String(episode.team_composition ?? '-')})
          </span>
          <span style={{ display: 'block' }}>
            reward {formatNumber(episode.reward, 3)} • steps {String(episode.steps ?? '-')} • created{' '}
            {formatDateTime(episode.created_at)}
          </span>
          {replayUrl ? (
            <a href={replayUrl} target="_blank" rel="noreferrer">
              Open replay
            </a>
          ) : (
            <span style={{ color: '#4b617f' }}>Replay unavailable</span>
          )}
        </span>
      )}
    </span>
  )
}

function OpponentChip({
  value,
  opponentName,
  opponentStats,
}: {
  value: string
  opponentName: string
  opponentStats: OpponentStats
}): ReactNode {
  const stats = opponentStats[opponentName]
  const title = stats
    ? `${opponentName} | games: ${String(stats.count)} | avg reward: ${formatNumber(stats.avg_reward, 2)}`
    : opponentName
  return (
    <span title={title} style={{ borderBottom: '1px dashed var(--panel-soft-border)' }}>
      {value}
    </span>
  )
}

function renderToken(
  token: AnalysisToken,
  index: number,
  episodeLookup: EpisodeLookup,
  opponentStats: OpponentStats,
  keyPrefix: string
): ReactNode {
  if (token.kind === 'text') return <span key={`${keyPrefix}-text-${index}`}>{token.value}</span>
  if (token.kind === 'episode') {
    const episode = episodeLookup.get(token.episodeId.toLowerCase())
    if (!episode) return <span key={`${keyPrefix}-episode-${index}`}>{token.value}</span>
    return (
      <span key={`${keyPrefix}-episode-${index}`}>
        <EpisodeChip value={token.value} episode={episode} />
      </span>
    )
  }
  return (
    <span key={`${keyPrefix}-opponent-${index}`}>
      <OpponentChip value={token.value} opponentName={token.opponentName} opponentStats={opponentStats} />
    </span>
  )
}

function renderInlineTokens(
  text: string,
  keyPrefix: string,
  episodeLookup: EpisodeLookup,
  opponentStats: OpponentStats
): ReactNode {
  const tokens = tokenizeOpponents(tokenizeEpisodeRefs(text, episodeLookup), opponentStats)
  return tokens.map((token, tokenIndex) => renderToken(token, tokenIndex, episodeLookup, opponentStats, keyPrefix))
}

type QuipTemplate = (context: { policy: string; best: string; worst: string; rival: string }) => string

const QUIP_TEMPLATES: QuipTemplate[] = [
  ({ policy, best }) => `${policy} requested analysis. Starting with its strongest teammate pairing: ${best}.`,
  ({ rival, worst }) => `Comparing teammate profiles ${rival} and ${worst} to explain coordination gaps.`,
  ({ policy }) => `Collecting signals, replay references, and failure traces for ${policy}.`,
  ({ best, rival }) => `Checking whether gains with ${best} still hold when paired with ${rival}.`,
  () => 'Parsing diagnostics and writing links you can actually click.',
]

function loadingContext(
  policyName: string,
  opponentStats: OpponentStats
): {
  policy: string
  best: string
  worst: string
  rival: string
} {
  const rows = Object.entries(opponentStats)
    .map(([name, stats]) => ({ name, reward: stats.avg_reward }))
    .filter((row) => Number.isFinite(row.reward))
    .sort((a, b) => b.reward - a.reward)

  return {
    policy: policyName || 'policy',
    best: rows[0]?.name ?? 'top-teammate',
    worst: rows[rows.length - 1]?.name ?? 'lowest-reward-teammate',
    rival: rows[1]?.name ?? rows[0]?.name ?? 'benchmark-teammate',
  }
}

export function AnalysisLoadingQuips({
  policyName,
  opponentStats,
}: {
  policyName: string
  opponentStats: OpponentStats
}): ReactNode {
  const context = useMemo(() => loadingContext(policyName, opponentStats), [policyName, opponentStats])
  const [index, setIndex] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % QUIP_TEMPLATES.length)
    }, 2200)
    return () => window.clearInterval(timer)
  }, [])

  return <p style={{ margin: 0, color: '#4b617f' }}>{QUIP_TEMPLATES[index](context)}</p>
}

export function AnalysisRichText({
  text,
  episodes,
  opponentStats,
}: {
  text: string
  episodes: DashboardEpisode[]
  opponentStats: OpponentStats
}): ReactNode {
  const episodeLookup = useMemo(() => buildEpisodeLookup(episodes), [episodes])
  const blocks = useMemo(() => parseBlocks(text), [text])

  return (
    <div
      style={{
        border: '1px solid var(--panel-soft-border)',
        borderRadius: 10,
        padding: 12,
        background: 'var(--panel-soft-bg-1)',
        display: 'grid',
        gap: 6,
      }}
    >
      {blocks.map((block, blockIndex) => {
        const key = `block-${blockIndex}`
        if (block.kind === 'heading') {
          if (block.level === 2) {
            return (
              <h3 key={key} style={{ margin: '6px 0 2px', fontSize: 16 }}>
                {renderInlineTokens(block.text, key, episodeLookup, opponentStats)}
              </h3>
            )
          }
          return (
            <h4 key={key} style={{ margin: '6px 0 2px', fontSize: 14 }}>
              {renderInlineTokens(block.text, key, episodeLookup, opponentStats)}
            </h4>
          )
        }

        if (block.kind === 'unordered-list') {
          return (
            <ul key={key} style={{ margin: '0 0 4px 20px', padding: 0 }}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-li-${itemIndex}`} style={{ lineHeight: 1.45, overflowWrap: 'anywhere' }}>
                  {renderInlineTokens(item, `${key}-li-${itemIndex}`, episodeLookup, opponentStats)}
                </li>
              ))}
            </ul>
          )
        }

        if (block.kind === 'ordered-list') {
          return (
            <ol key={key} style={{ margin: '0 0 4px 20px', padding: 0 }}>
              {block.items.map((item, itemIndex) => (
                <li key={`${key}-li-${itemIndex}`} style={{ lineHeight: 1.45, overflowWrap: 'anywhere' }}>
                  {renderInlineTokens(item, `${key}-li-${itemIndex}`, episodeLookup, opponentStats)}
                </li>
              ))}
            </ol>
          )
        }

        return (
          <p key={key} style={{ margin: 0, lineHeight: 1.45, overflowWrap: 'anywhere' }}>
            {renderInlineTokens(block.text, key, episodeLookup, opponentStats)}
          </p>
        )
      })}
    </div>
  )
}
