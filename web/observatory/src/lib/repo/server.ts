import 'server-only'

import { cookies } from 'next/headers'
import { cache } from 'react'

import { getAuthToken } from '@/auth/server'
import { config, isDevMode } from '@/config'
import { OUTAGE_COOKIE_NAME, setOutageSimulated } from '@/lib/debug/simulate-outage'

import { Repo, RequestLogEntry } from './'

const getServerRequestLog = cache((): RequestLogEntry[] => [])

export async function getRepo(): Promise<Repo> {
  const token = await getAuthToken()
  if (isDevMode()) {
    const cookieStore = await cookies()
    setOutageSimulated(cookieStore.has(OUTAGE_COOKIE_NAME))
  }
  const log = getServerRequestLog()
  return new Repo(config.apiBaseUrl, token, (entry) => log.push(entry))
}

/**
 * Drain accumulated server-side request log entries.
 * Returns and clears entries that have accumulated since the last drain.
 */
export function drainServerRequests(): RequestLogEntry[] {
  const log = getServerRequestLog()
  if (log.length === 0) return []
  const entries = [...log]
  log.length = 0
  return entries
}
