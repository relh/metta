'use client'

import { FC, useEffect } from 'react'

import type { RequestLogEntry } from '@/lib/debug/request-log'
import { addEntries } from '@/lib/debug/request-log'

/**
 * Client component that bridges server-side request log entries into the client store.
 * Rendered by ServerDebugDrain with serialized entries from the server.
 * Renders nothing visible.
 */
export const DebugRequestBridge: FC<{ entries: RequestLogEntry[] }> = ({ entries }) => {
  useEffect(() => {
    if (entries.length > 0) {
      addEntries(entries)
    }
  }, [entries])

  return null
}
