'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'

import type { BardoPolicy, BardoWorldState } from '../lib/types'

const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME?.trim() || 'observatory_auth_token'
const BARDO_AUTH_TOKEN_SESSION_STORAGE_KEY = 'bardo-auth-token'
const WORLD_POLL_MS = 15_000
const WORLD_STEP_MS = 60

const PORTAL = { x: 0.9, y: 0.16 }

type ActorState = {
  x: number
  y: number
  targetX: number
  targetY: number
  cycle: number
  nextRetargetAtMs: number
  hidden: boolean
}

type RenderedPolicy = BardoPolicy & {
  x: number
  y: number
  hidden: boolean
  busy: boolean
  color: string
  initials: string
}

function clamp01(value: number): number {
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

function hashString(value: string): number {
  let hash = 2166136261
  for (let idx = 0; idx < value.length; idx += 1) {
    hash ^= value.charCodeAt(idx)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

function seededUnit(seed: string): number {
  return (hashString(seed) % 10_000) / 10_000
}

function distance(a: { x: number; y: number }, b: { x: number; y: number }): number {
  const dx = a.x - b.x
  const dy = a.y - b.y
  return Math.hypot(dx, dy)
}

function spawnPoint(policyId: string): { x: number; y: number } {
  return {
    x: 0.07 + 0.76 * seededUnit(`${policyId}:spawn:x`),
    y: 0.2 + 0.72 * seededUnit(`${policyId}:spawn:y`),
  }
}

function portalQueueTarget(policyId: string): { x: number; y: number } {
  return {
    x: PORTAL.x - 0.05 + 0.04 * seededUnit(`${policyId}:portal:x`),
    y: PORTAL.y + 0.03 + 0.08 * seededUnit(`${policyId}:portal:y`),
  }
}

function portalExitPoint(policyId: string): { x: number; y: number } {
  return {
    x: PORTAL.x - 0.06 + 0.03 * seededUnit(`${policyId}:exit:x`),
    y: PORTAL.y + 0.11 + 0.04 * seededUnit(`${policyId}:exit:y`),
  }
}

function nextWanderTarget(policyId: string, cycle: number): { x: number; y: number; lingerMs: number } {
  for (let attempt = 0; attempt < 6; attempt += 1) {
    const x = 0.06 + 0.85 * seededUnit(`${policyId}:wander:x:${cycle}:${attempt}`)
    const y = 0.18 + 0.77 * seededUnit(`${policyId}:wander:y:${cycle}:${attempt}`)
    const isPortalZone = x > 0.76 && y < 0.4
    if (isPortalZone) continue

    const lingerMs = 2200 + Math.floor(2200 * seededUnit(`${policyId}:linger:${cycle}:${attempt}`))
    return { x, y, lingerMs }
  }

  return {
    x: 0.5,
    y: 0.5,
    lingerMs: 2600,
  }
}

function colorForPolicy(policyId: string): string {
  const hue = Math.floor(seededUnit(`${policyId}:h`) * 360)
  const saturation = 62 + Math.floor(seededUnit(`${policyId}:s`) * 16)
  const lightness = 47 + Math.floor(seededUnit(`${policyId}:l`) * 10)
  return `hsl(${hue} ${saturation}% ${lightness}%)`
}

function policyInitials(name: string): string {
  const tokens = name
    .split(/[._-]+/)
    .map((token) => token.trim())
    .filter((token) => token.length > 0)

  if (tokens.length === 0) {
    return name.slice(0, 2).toUpperCase()
  }

  if (tokens.length === 1) {
    return tokens[0].slice(0, 2).toUpperCase()
  }

  return `${tokens[0][0]}${tokens[tokens.length - 1][0]}`.toUpperCase()
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function asPercent(value: number): string {
  return `${(clamp01(value) * 100).toFixed(3)}%`
}

function trimToNull(value: string | null | undefined): string | null {
  const trimmed = value?.trim()
  return trimmed ? trimmed : null
}

function readBardoAuthTokenFromUrlFragment(): string | null {
  if (typeof window === 'undefined') return null
  const currentUrl = new URL(window.location.href)
  const rawFragment = currentUrl.hash.startsWith('#') ? currentUrl.hash.slice(1) : currentUrl.hash
  if (!rawFragment) return null

  let decodedFragment = rawFragment
  try {
    decodedFragment = decodeURIComponent(rawFragment)
  } catch {
    return null
  }

  const token = trimToNull(decodedFragment)
  if (!token) return null

  window.sessionStorage.setItem(BARDO_AUTH_TOKEN_SESSION_STORAGE_KEY, token)
  window.history.replaceState({}, '', `${currentUrl.pathname}${currentUrl.search}`)
  return token
}

function readBardoAuthTokenFromCookie(): string | null {
  if (typeof document === 'undefined') return null
  const parts = document.cookie.split('; ')
  for (const part of parts) {
    if (!part.startsWith(`${AUTH_COOKIE_NAME}=`)) continue
    return trimToNull(part.slice(AUTH_COOKIE_NAME.length + 1))
  }
  return null
}

export function resolveBardoAuthToken(): string | null {
  if (typeof window === 'undefined') return null
  const hashToken = readBardoAuthTokenFromUrlFragment()
  if (hashToken) return hashToken

  const sessionToken = trimToNull(window.sessionStorage.getItem(BARDO_AUTH_TOKEN_SESSION_STORAGE_KEY))
  if (sessionToken) return sessionToken

  const cookieToken = readBardoAuthTokenFromCookie()
  if (cookieToken) return cookieToken

  return null
}

function ensureActorState(store: Map<string, ActorState>, policyId: string): ActorState {
  const existing = store.get(policyId)
  if (existing) return existing

  const initial = spawnPoint(policyId)
  const actorState: ActorState = {
    x: initial.x,
    y: initial.y,
    targetX: initial.x,
    targetY: initial.y,
    cycle: 0,
    nextRetargetAtMs: 0,
    hidden: false,
  }

  store.set(policyId, actorState)
  return actorState
}

export function BardoLobby() {
  const searchParams = useSearchParams()
  const nameFilter = searchParams.get('q')?.trim() || ''
  const requestedTheme = searchParams.get('theme')

  const [world, setWorld] = useState<BardoWorldState | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [renderedPolicies, setRenderedPolicies] = useState<RenderedPolicy[]>([])
  const [hoveredPolicyId, setHoveredPolicyId] = useState<string | null>(null)

  const actorsRef = useRef<Map<string, ActorState>>(new Map())

  useEffect(() => {
    if (requestedTheme !== 'dark' && requestedTheme !== 'light') {
      document.documentElement.removeAttribute('data-theme')
      return
    }
    document.documentElement.setAttribute('data-theme', requestedTheme)
  }, [requestedTheme])

  const loadWorldState = useCallback(async () => {
    const query = new URLSearchParams()
    if (nameFilter) query.set('q', nameFilter)
    const endpoint = query.size > 0 ? `/api/world-state?${query.toString()}` : '/api/world-state'

    const authToken = resolveBardoAuthToken()
    const headers = authToken ? { 'X-Auth-Token': authToken } : undefined
    const response = await fetch(endpoint, { cache: 'no-store', headers })

    if (!response.ok) {
      const payload = (await response.json().catch(() => ({ error: '' }))) as { error?: string }
      throw new Error(payload.error || `Bardo request failed (${response.status})`)
    }

    const payload = (await response.json()) as BardoWorldState
    setWorld(payload)
  }, [nameFilter])

  useEffect(() => {
    let cancelled = false

    const refresh = async () => {
      try {
        await loadWorldState()
        if (!cancelled) {
          setErrorMessage(null)
          setIsLoading(false)
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(toErrorMessage(error))
          setIsLoading(false)
        }
      }
    }

    void refresh()
    const interval = setInterval(() => {
      void refresh()
    }, WORLD_POLL_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [loadWorldState])

  useEffect(() => {
    if (!world) return

    const actorStore = actorsRef.current
    const activePolicyIds = new Set(world.policies.map((policy) => policy.policyId))

    for (const policyId of [...actorStore.keys()]) {
      if (!activePolicyIds.has(policyId)) {
        actorStore.delete(policyId)
      }
    }

    for (const policy of world.policies) {
      ensureActorState(actorStore, policy.policyId)
    }

    const tick = () => {
      const now = Date.now()
      const nextFrame: RenderedPolicy[] = []

      for (const policy of world.policies) {
        const actor = ensureActorState(actorStore, policy.policyId)
        const busy = policy.activeJobIds.length > 0

        if (busy) {
          const queueTarget = portalQueueTarget(policy.policyId)
          actor.targetX = queueTarget.x
          actor.targetY = queueTarget.y
        } else {
          if (actor.hidden) {
            const portalExit = portalExitPoint(policy.policyId)
            actor.hidden = false
            actor.x = portalExit.x
            actor.y = portalExit.y
            actor.targetX = portalExit.x
            actor.targetY = portalExit.y
            actor.nextRetargetAtMs = 0
          }

          const shouldRetarget =
            now >= actor.nextRetargetAtMs || distance(actor, { x: actor.targetX, y: actor.targetY }) < 0.02

          if (shouldRetarget) {
            actor.cycle += 1
            const nextTarget = nextWanderTarget(policy.policyId, actor.cycle)
            actor.targetX = nextTarget.x
            actor.targetY = nextTarget.y
            actor.nextRetargetAtMs = now + nextTarget.lingerMs
          }
        }

        const easing = busy ? 0.18 : 0.08
        actor.x += (actor.targetX - actor.x) * easing
        actor.y += (actor.targetY - actor.y) * easing

        if (busy && distance(actor, PORTAL) < 0.03) {
          actor.hidden = true
        }

        nextFrame.push({
          ...policy,
          x: actor.x,
          y: actor.y,
          hidden: busy && actor.hidden,
          busy,
          color: colorForPolicy(policy.policyId),
          initials: policyInitials(policy.name),
        })
      }

      setRenderedPolicies(nextFrame)
    }

    tick()
    const interval = setInterval(tick, WORLD_STEP_MS)
    return () => clearInterval(interval)
  }, [world])

  const visiblePolicies = useMemo(() => renderedPolicies.filter((policy) => !policy.hidden), [renderedPolicies])

  const hoveredPolicy = useMemo(
    () => visiblePolicies.find((policy) => policy.policyId === hoveredPolicyId) ?? null,
    [hoveredPolicyId, visiblePolicies]
  )

  const nearbyPolicies = useMemo(() => {
    if (!hoveredPolicy) return []

    return visiblePolicies
      .filter((policy) => policy.policyId !== hoveredPolicy.policyId)
      .map((policy) => ({
        policy,
        dist: distance(hoveredPolicy, policy),
      }))
      .filter((entry) => entry.dist < 0.15)
      .sort((left, right) => left.dist - right.dist)
      .slice(0, 6)
      .map((entry) => entry.policy)
  }, [hoveredPolicy, visiblePolicies])

  const inEpisodeCount = world?.policies.filter((policy) => policy.activeJobIds.length > 0).length ?? 0
  const lastUpdatedLabel = world
    ? new Date(world.generatedAt).toLocaleTimeString([], {
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
      })
    : '—'

  return (
    <main className="bardo-shell">
      <section className="bardo-card">
        <header className="bardo-header">
          <div>
            <p className="bardo-kicker">Between Episodes</p>
            <h1>Bardo Lobby</h1>
            <p className="bardo-subtitle">
              Latest policy versions wander here. Policies in pending or running episode jobs drift to the portal and
              phase out until they return.
            </p>
          </div>
          <div className="bardo-stats" role="status" aria-live="polite">
            <p>
              <span>Visible now</span>
              <strong>{visiblePolicies.length}</strong>
            </p>
            <p>
              <span>In episode</span>
              <strong>{inEpisodeCount}</strong>
            </p>
            <p>
              <span>Active jobs</span>
              <strong>{world?.activeJobs.length ?? 0}</strong>
            </p>
          </div>
        </header>

        {errorMessage ? <div className="bardo-alert">{errorMessage}</div> : null}

        <div className="bardo-world" role="img" aria-label="Bardo lobby world map">
          <div className="bardo-world-glow" />
          <div className="bardo-world-grid" />

          <div
            className="bardo-portal"
            style={{
              left: asPercent(PORTAL.x),
              top: asPercent(PORTAL.y),
            }}
          >
            <span>Episode Portal</span>
          </div>

          {visiblePolicies.map((policy) => (
            <button
              key={policy.policyId}
              type="button"
              className={`bardo-policy ${policy.busy ? 'busy' : ''}`}
              style={{
                left: asPercent(policy.x),
                top: asPercent(policy.y),
                backgroundColor: policy.color,
              }}
              title={`${policy.name} • ${policy.userName}`}
              onMouseEnter={() => setHoveredPolicyId(policy.policyId)}
              onMouseLeave={() => setHoveredPolicyId((current) => (current === policy.policyId ? null : current))}
            >
              <span>{policy.initials}</span>
            </button>
          ))}

          {hoveredPolicy ? (
            <div
              className="bardo-tooltip"
              style={{
                left: asPercent(hoveredPolicy.x),
                top: asPercent(hoveredPolicy.y),
              }}
            >
              <p className="bardo-tooltip-name">{hoveredPolicy.name}</p>
              <p className="bardo-tooltip-owner">by {hoveredPolicy.userName}</p>
              <p className="bardo-tooltip-meta">
                {hoveredPolicy.busy
                  ? `In episode job (${hoveredPolicy.activeJobIds.length})`
                  : `${nearbyPolicies.length} nearby policy${nearbyPolicies.length === 1 ? '' : 'ies'}`}
              </p>
              {nearbyPolicies.length > 0 ? (
                <div className="bardo-tooltip-neighbors">
                  {nearbyPolicies.map((neighbor) => (
                    <span key={neighbor.policyId}>{neighbor.name}</span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {isLoading ? (
            <div className="bardo-loading">
              <span>Loading policies into Bardo...</span>
            </div>
          ) : null}
        </div>

        <footer className="bardo-footer">
          <span>Updated {lastUpdatedLabel}</span>
          <span>Latest versions only</span>
          {nameFilter ? <span>Filter: “{nameFilter}”</span> : <span>All policies</span>}
        </footer>
      </section>
    </main>
  )
}
