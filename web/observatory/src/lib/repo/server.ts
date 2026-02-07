import 'server-only'

import { cache } from 'react'

import { getAuthToken } from '@/auth/server'
import { config } from '@/config'

import { Repo, RequestLogEntry } from './'

const getServerRequestLog = cache((): RequestLogEntry[] => [])

export async function getRepo(): Promise<Repo> {
  const token = await getAuthToken()
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
