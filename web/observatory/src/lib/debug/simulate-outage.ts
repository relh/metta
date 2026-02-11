import { isDevMode } from '@/config'

export const OUTAGE_COOKIE_NAME = 'observatory-simulate-outage'

let _active = false

if (typeof window !== 'undefined' && isDevMode()) {
  _active = document.cookie.split('; ').some((c) => c.startsWith(`${OUTAGE_COOKIE_NAME}=`))
}

const listeners = new Set<() => void>()

function notify() {
  for (const listener of listeners) listener()
}

export function isOutageSimulated(): boolean {
  return _active
}

export function setOutageSimulated(value: boolean) {
  if (!isDevMode()) return
  _active = value
  if (typeof window !== 'undefined') {
    document.cookie = value
      ? `${OUTAGE_COOKIE_NAME}=1; path=/; max-age=86400`
      : `${OUTAGE_COOKIE_NAME}=; path=/; max-age=0`
  }
  notify()
}

export function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getSnapshot(): boolean {
  return _active
}

export function getServerSnapshot(): boolean {
  return false
}
