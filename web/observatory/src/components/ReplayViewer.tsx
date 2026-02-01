'use client'

import { FC, useState } from 'react'

import { METTASCOPE_REPLAY_URL_PREFIX, VIBESCOPE_REPLAY_URL_PREFIX } from '../constants'
import { A } from './A'
import { Button } from './Button'
import { SmallHeader } from './SmallHeader'

export function normalizeReplayUrl(replayUrl: string | null | undefined): string | null {
  if (!replayUrl) return null
  if (replayUrl.startsWith(METTASCOPE_REPLAY_URL_PREFIX)) {
    return replayUrl
  }
  return `${METTASCOPE_REPLAY_URL_PREFIX}${replayUrl}`
}

export function normalizeVibescopeUrl(replayUrl: string | null | undefined): string | null {
  if (!replayUrl) return null
  if (replayUrl.startsWith(VIBESCOPE_REPLAY_URL_PREFIX)) {
    return replayUrl
  }
  const raw = replayUrl.startsWith(METTASCOPE_REPLAY_URL_PREFIX)
    ? replayUrl.slice(METTASCOPE_REPLAY_URL_PREFIX.length)
    : replayUrl
  return `${VIBESCOPE_REPLAY_URL_PREFIX}${raw}`
}

type ReplayScope = 'mettascope' | 'vibescope'

type ReplayViewerProps = {
  replayUrl: string | null | undefined
  label?: string
  height?: number
  showExternalLink?: boolean
}

export const ReplayViewer: FC<ReplayViewerProps> = ({ replayUrl, label, height = 480, showExternalLink = true }) => {
  const [scope, setScope] = useState<ReplayScope>('vibescope')
  const [copied, setCopied] = useState(false)

  const msUrl = normalizeReplayUrl(replayUrl)
  const vsUrl = normalizeVibescopeUrl(replayUrl)
  const normalized = scope === 'vibescope' ? vsUrl : msUrl

  if (!normalized) {
    return <div className="text-gray-500 text-sm">No replay available.</div>
  }

  const handleCopyUrl = () => {
    if (normalized) {
      navigator.clipboard.writeText(normalized)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="space-y-2">
      {label ? (
        <div className="flex items-center gap-2">
          <SmallHeader>{label}</SmallHeader>
          <Button size="sm" onClick={() => setScope('mettascope')} disabled={scope === 'mettascope'}>
            MS
          </Button>
          <Button size="sm" onClick={() => setScope('vibescope')} disabled={scope === 'vibescope'}>
            VS
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm">
          <Button size="sm" onClick={() => setScope('mettascope')} disabled={scope === 'mettascope'}>
            MS
          </Button>
          <Button size="sm" onClick={() => setScope('vibescope')} disabled={scope === 'vibescope'}>
            VS
          </Button>
        </div>
      )}
      <div
        className="w-full border border-gray-200 rounded overflow-hidden bg-black"
        style={{ minHeight: '360px', height }}
      >
        <iframe src={normalized} title={label ?? 'Episode replay'} className="w-full h-full" allowFullScreen />
      </div>
      {showExternalLink ? (
        <div className="flex items-center gap-3 text-sm">
          {msUrl ? (
            <A href={msUrl} target="_blank" rel="noopener noreferrer">
              Open in MettaScope
            </A>
          ) : null}
          {vsUrl ? (
            <A href={vsUrl} target="_blank" rel="noopener noreferrer">
              Open in VibeScope
            </A>
          ) : null}
          <button onClick={handleCopyUrl} className="text-blue-600 hover:text-blue-800 hover:underline cursor-pointer">
            {copied ? 'Copied!' : 'Copy Url'}
          </button>
        </div>
      ) : null}
    </div>
  )
}
