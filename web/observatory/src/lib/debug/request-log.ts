import type { RequestLogEntry } from '@/lib/repo'

export type { RequestLogEntry }

// Client-side store for request debug entries.
// Used with useSyncExternalStore for reactive updates.

let entries: RequestLogEntry[] = []
let snapshot: RequestLogEntry[] = entries
const seenIds = new Set<string>()
const listeners = new Set<() => void>()

function notify() {
  snapshot = [...entries]
  for (const listener of listeners) {
    listener()
  }
}

export function addEntries(newEntries: RequestLogEntry[]) {
  const unique = newEntries.filter((e) => !seenIds.has(e.id))
  if (unique.length === 0) return
  for (const e of unique) seenIds.add(e.id)
  entries = [...entries, ...unique]
  notify()
}

export function clearEntries() {
  entries = []
  seenIds.clear()
  notify()
}

export function getSnapshot(): RequestLogEntry[] {
  return snapshot
}

const emptyEntries: RequestLogEntry[] = []

export function getServerSnapshot(): RequestLogEntry[] {
  // Server-side: always return empty (entries only live on the client)
  return emptyEntries
}

export function subscribe(callback: () => void): () => void {
  listeners.add(callback)
  return () => listeners.delete(callback)
}
