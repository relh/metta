'use client'

import { FC, ReactNode, useMemo, useState } from 'react'
import Markdown, { Components } from 'react-markdown'
import { flip, Placement, useFloating, useHover, useInteractions } from '@floating-ui/react'
import { normalizeVibescopeUrl } from '@/components/ReplayViewer'
import type { DashboardResponse, DashboardEpisode } from '@/lib/repo'

// Inline-safe tooltip using only <span> elements (no <div>/<p>) to avoid
// invalid DOM nesting when rendered inside markdown <p> tags.
const InlineTooltip: FC<{
  children: ReactNode
  placement?: Placement
  render: () => ReactNode
}> = ({ children, placement = 'top-start', render }) => {
  const [isOpen, setIsOpen] = useState(false)
  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    placement,
    middleware: [flip()],
  })
  const hover = useHover(context)
  const { getReferenceProps, getFloatingProps } = useInteractions([hover])
  return (
    <>
      <span ref={refs.setReference} {...getReferenceProps()}>
        {children}
      </span>
      {isOpen && (
        <span
          ref={refs.setFloating}
          {...getFloatingProps({
            style: floatingStyles,
            className:
              'z-50 rounded-lg border border-border-strong bg-surface px-3 py-1.5 text-sm shadow-xl text-foreground',
          })}
        >
          {render()}
        </span>
      )}
    </>
  )
}

// === Types ===

type EpisodeSnap = DashboardEpisode & { _prefix: string }

type EpisodeMap = Map<string, EpisodeSnap>

// === Episode Map Builder ===

function buildEpisodeMap(episodes: DashboardEpisode[]): EpisodeMap {
  const map: EpisodeMap = new Map()
  for (const ep of episodes) {
    const prefix = ep.episode_id.slice(0, 8)
    const snap: EpisodeSnap = { ...ep, _prefix: prefix }
    map.set(ep.episode_id, snap)
    // Only set prefix key if unambiguous
    if (!map.has(prefix)) {
      map.set(prefix, snap)
    }
  }
  return map
}

// === Markdown Enrichment ===

const UUID_RE = /\b([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\b/gi
function enrichMarkdown(text: string, episodeMap: EpisodeMap, opponentNames: string[]): string {
  // Strip backticks around UUIDs so they become linkable (AI often wraps IDs in code spans)
  let enriched = text.replace(/`([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})`/gi, '$1')
  enriched = enriched.replace(/`([0-9a-f]{8})`/g, (match, id) => {
    return episodeMap.has(id.toLowerCase()) ? id : match
  })

  // Replace full UUIDs first
  enriched = enriched.replace(UUID_RE, (match) => {
    const ep = episodeMap.get(match.toLowerCase())
    if (ep) return `[${match.slice(0, 8)}](#episode:${ep.episode_id})`
    return match
  })

  // Replace 8-char hex IDs (skip those already inside markdown links)
  enriched = enriched.replace(/(?<!\[)(?<!\(#episode:)\b([0-9a-f]{8})\b(?!\))/g, (match) => {
    const ep = episodeMap.get(match.toLowerCase())
    if (ep) return `[${match}](#episode:${ep.episode_id})`
    return match
  })

  // Replace opponent names — sort longest-first to avoid partial matches
  const sorted = [...opponentNames].sort((a, b) => b.length - a.length)
  for (const name of sorted) {
    // Strip backticks around opponent names so they become linkable
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    enriched = enriched.replace(new RegExp('`(' + escaped + ')`', 'g'), '$1')
    // Match whole-word occurrences not already inside markdown links
    const re = new RegExp(`(?<!\\[)\\b(${escaped})\\b(?!\\])`, 'g')
    enriched = enriched.replace(re, `[$1](#opponent:$1)`)
  }

  return enriched
}

// === Inline Components ===

const EpisodeChip: FC<{
  episodeId: string
  episodeMap: EpisodeMap
  children: ReactNode
}> = ({ episodeId, episodeMap, children }) => {
  const [expanded, setExpanded] = useState(false)
  const ep = episodeMap.get(episodeId)
  if (!ep) return <span className="font-mono text-xs">{children}</span>

  const replayUrl = normalizeVibescopeUrl(ep.replay_url)
  const rewardColor = ep.reward < 0.5 ? 'text-red-500' : ep.reward > 2.0 ? 'text-green-500' : 'text-foreground'

  return (
    <span className="inline">
      <button
        onClick={() => setExpanded(!expanded)}
        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-surface border border-border text-xs font-mono cursor-pointer hover:bg-surface-alt transition-colors"
      >
        {children}
        <span className="text-[10px] ml-0.5">{expanded ? '\u25B2' : '\u25BC'}</span>
      </button>
      {expanded && (
        <span className="block mt-1 mb-2 ml-2 pl-3 border-l-2 border-border text-xs space-y-0.5">
          <span className="block">
            <span className="text-foreground-muted">vs</span>{' '}
            <span className="font-medium text-foreground">{ep.opponent_name}</span>
            <span className="text-foreground-muted ml-2">comp: {ep.team_composition}</span>
          </span>
          <span className="block">
            <span className="text-foreground-muted">reward:</span>{' '}
            <span className={`font-mono font-medium ${rewardColor}`}>{ep.reward.toFixed(2)}</span>
            <span className="text-foreground-muted ml-2">steps: {ep.steps}</span>
          </span>
          <span className="block text-foreground-muted">
            move: {Math.round(ep.metrics['action.move.success'] ?? 0)}s /
            {Math.round(ep.metrics['action.move.failed'] ?? 0)}f{' \u00B7 '}frozen:{' '}
            {Math.round(ep.metrics['status.frozen.ticks'] ?? 0)}
            {' \u00B7 '}junc: {Math.round(ep.metrics['junction.aligned_by_agent'] ?? 0)}
          </span>
          {replayUrl && (
            <span className="block">
              <a
                href={replayUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 text-xs font-medium hover:bg-green-200 dark:hover:bg-green-900/50 no-underline"
              >
                \u25B6 Watch Replay
              </a>
            </span>
          )}
        </span>
      )}
    </span>
  )
}

const OpponentChip: FC<{
  name: string
  opponentMetrics: DashboardResponse['derived']['opponent_metrics']
  children: ReactNode
}> = ({ name, opponentMetrics, children }) => {
  const stats = opponentMetrics[name]

  const chip = (
    <span className="border-b border-dashed border-foreground-muted text-foreground cursor-default">{children}</span>
  )

  if (!stats) return chip

  return (
    <InlineTooltip
      placement="top"
      render={() => (
        <>
          <span className="font-medium">{name}</span>
          {' · '}Games: {stats.count}
          {' · '}Avg reward: {stats.avg_reward.toFixed(2)}
        </>
      )}
    >
      {chip}
    </InlineTooltip>
  )
}

// === Main Component ===

export const AnalysisMarkdown: FC<{
  text: string
  data: DashboardResponse
}> = ({ text, data }) => {
  const episodeMap = useMemo(() => buildEpisodeMap(data.episodes), [data.episodes])
  const opponentNames = useMemo(() => Object.keys(data.derived.opponent_metrics), [data.derived.opponent_metrics])

  const enriched = useMemo(() => enrichMarkdown(text, episodeMap, opponentNames), [text, episodeMap, opponentNames])

  const components: Components = useMemo(
    () => ({
      a: ({ href, children }) => {
        if (href?.startsWith('#episode:')) {
          const id = href.slice('#episode:'.length)
          return (
            <EpisodeChip episodeId={id} episodeMap={episodeMap}>
              {children}
            </EpisodeChip>
          )
        }
        if (href?.startsWith('#opponent:')) {
          const name = href.slice('#opponent:'.length)
          return (
            <OpponentChip name={name} opponentMetrics={data.derived.opponent_metrics}>
              {children}
            </OpponentChip>
          )
        }
        return (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        )
      },
    }),
    [episodeMap, data.derived.opponent_metrics]
  )

  return <Markdown components={components}>{enriched}</Markdown>
}
