'use client'

import clsx from 'clsx'
import { FC, use, useCallback, useState, useSyncExternalStore } from 'react'

import { AppContext } from '@/app/(main)/AppContext'
import { Dropdown, DropdownMenu, DropdownMenuItem } from '@/components/Dropdown'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import type { RequestLogEntry } from '@/lib/debug/request-log'
import { clearEntries, getServerSnapshot, getSnapshot, subscribe } from '@/lib/debug/request-log'

function formatTime(timestamp: number): string {
  return new Date(timestamp).toLocaleTimeString('en-US', {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const StatusBadge: FC<{ status: number }> = ({ status }) => {
  const color =
    status === 0
      ? 'bg-red-200 text-red-800'
      : status < 300
        ? 'bg-green-200 text-green-800'
        : status < 400
          ? 'bg-yellow-200 text-yellow-800'
          : 'bg-red-200 text-red-800'

  return <span className={clsx('px-1.5 py-0.5 rounded text-xs font-mono', color)}>{status || 'ERR'}</span>
}

const SourceBadge: FC<{ source: 'server' | 'client' }> = ({ source }) => {
  const color = source === 'server' ? 'bg-blue-200 text-blue-800' : 'bg-purple-200 text-purple-800'
  return <span className={clsx('px-1.5 py-0.5 rounded text-xs', color)}>{source}</span>
}

const EndpointCell: FC<{ entry: RequestLogEntry }> = ({ entry }) => {
  const { token, apiBaseUrl } = use(AppContext)

  const copyCurl = useCallback(() => {
    const parts = ['curl']
    if (entry.method !== 'GET') {
      parts.push(`-X ${entry.method}`)
    }
    if (token) {
      parts.push(`-H "X-Auth-Token: ${token}"`)
    }
    parts.push(`"${apiBaseUrl}${entry.endpoint}"`)
    navigator.clipboard.writeText(parts.join(' '))
  }, [entry, token, apiBaseUrl])

  return (
    <Dropdown
      render={({ close }) => (
        <DropdownMenu>
          <DropdownMenuItem
            title="Copy as curl"
            onClick={() => {
              copyCurl()
              close()
            }}
          />
        </DropdownMenu>
      )}
    >
      <span className="font-mono text-gray-800 max-w-md truncate cursor-pointer hover:text-blue-600">
        {entry.endpoint}
      </span>
    </Dropdown>
  )
}

const RequestRow: FC<{ entry: RequestLogEntry }> = ({ entry }) => {
  return (
    <TR key={entry.id}>
      <TD className="text-gray-500 font-mono">{formatTime(entry.timestamp)}</TD>
      <TD>
        <SourceBadge source={entry.source} />
      </TD>
      <TD className="font-mono text-gray-600">{entry.method}</TD>
      <TD>
        <EndpointCell entry={entry} />
      </TD>
      <TD>
        <StatusBadge status={entry.status} />
      </TD>
      <TD className="text-right font-mono text-gray-500">{entry.durationMs}ms</TD>
      {entry.error && (
        <TD className="text-red-600 truncate max-w-xs" title={entry.error}>
          {entry.error}
        </TD>
      )}
    </TR>
  )
}

export const RequestDebugPanel: FC = () => {
  const entries = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
  const [expanded, setExpanded] = useState(false)

  const toggle = useCallback(() => setExpanded((e) => !e), [])

  if (entries.length === 0 && !expanded) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-300 shadow-lg">
      {/* Header bar */}
      <div
        className="flex items-center justify-between px-3 py-1.5 bg-gray-100 cursor-pointer select-none"
        onClick={toggle}
      >
        <div className="flex items-center gap-2 text-xs text-gray-600">
          <span className="font-semibold">API Requests</span>
          <span className="bg-gray-300 text-gray-700 px-1.5 py-0.5 rounded-full text-xs font-mono">
            {entries.length}
          </span>
          {!expanded && entries.length > 0 && (
            <span className="text-gray-400 ml-1">
              last: {entries[entries.length - 1].method} {entries[entries.length - 1].endpoint}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {entries.length > 0 && (
            <button
              className="text-xs text-gray-500 hover:text-gray-700 px-1"
              onClick={(e) => {
                e.stopPropagation()
                clearEntries()
              }}
            >
              Clear
            </button>
          )}
          <span className="text-gray-400 text-xs">{expanded ? '▼' : '▲'}</span>
        </div>
      </div>

      {/* Expanded table */}
      {expanded && (
        <div className="max-h-64 overflow-y-auto">
          {entries.length === 0 ? (
            <div className="text-xs text-gray-400 px-3 py-4 text-center">No requests captured yet</div>
          ) : (
            <Table theme="inner">
              <TableHeader>
                <TH>Time</TH>
                <TH>Source</TH>
                <TH>Method</TH>
                <TH>Endpoint</TH>
                <TH>Status</TH>
                <TH className="text-right">Duration</TH>
              </TableHeader>
              <TableBody>
                {entries.map((entry) => (
                  <RequestRow key={entry.id} entry={entry} />
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}
    </div>
  )
}
