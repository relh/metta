'use client'

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useSearchParams } from 'next/navigation'

import type { BardoPolicy, BardoWorldState } from '../lib/bardo-types'
import {
  BARDO_ATLAS_SIZE,
  BARDO_LOBBY_DECORATIONS,
  BARDO_PORTALS,
  BARDO_ROOM_UNIT_RECTS,
  BARDO_SPRITE_FRAMES,
  OVERFLOW_ROOM_SLOT_ID,
  accentForSubmitter,
  buildSubmitterRoomPlan,
  pointInRect,
  portalForPolicy,
  spriteForPolicy,
  type BardoPortal,
  type BardoRoomSlotId,
  type BardoSpriteId,
} from '../lib/bardo-lobby-layout'

const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME?.trim() || 'observatory_auth_token'
const BARDO_AUTH_TOKEN_SESSION_STORAGE_KEY = 'bardo-auth-token'
const WORLD_POLL_MS = 15_000
const WORLD_STEP_MS = 70
const PORTAL_CAPTURE_DISTANCE = 0.028

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
  roomId: BardoRoomSlotId
  roomLabel: string
  spriteId: BardoSpriteId
  accentColor: string
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

function asPercent(value: number): string {
  return `${(clamp01(value) * 100).toFixed(3)}%`
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function portalQueueTarget(policyId: string, portal: BardoPortal): { x: number; y: number } {
  return {
    x: clamp01(portal.x - 0.03 + 0.06 * seededUnit(`${policyId}:${portal.id}:x`)),
    y: clamp01(portal.y + 0.028 + 0.065 * seededUnit(`${policyId}:${portal.id}:y`)),
  }
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

function roomSpawnPoint(policyId: string, roomId: BardoRoomSlotId): { x: number; y: number } {
  return pointInRect(`${policyId}:${roomId}:spawn`, BARDO_ROOM_UNIT_RECTS[roomId], 0)
}

function atlasSpriteStyle(spriteId: BardoSpriteId, size: number): CSSProperties {
  const frame = BARDO_SPRITE_FRAMES[spriteId]
  const scale = size / frame.width

  return {
    width: `${size}px`,
    height: `${size}px`,
    backgroundImage: "url('/assets/mettagrid/atlas_mini.png')",
    backgroundSize: `${BARDO_ATLAS_SIZE * scale}px ${BARDO_ATLAS_SIZE * scale}px`,
    backgroundPosition: `-${frame.x * scale}px -${frame.y * scale}px`,
    imageRendering: 'pixelated',
    backgroundRepeat: 'no-repeat',
  }
}

function ensureActorState(store: Map<string, ActorState>, policyId: string, roomId: BardoRoomSlotId): ActorState {
  const existing = store.get(policyId)
  if (existing) return existing

  const spawn = roomSpawnPoint(policyId, roomId)
  const actorState: ActorState = {
    x: spawn.x,
    y: spawn.y,
    targetX: spawn.x,
    targetY: spawn.y,
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
    const endpoint = query.size > 0 ? `/api/bardo/world-state?${query.toString()}` : '/api/bardo/world-state'

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

  const roomPlan = useMemo(() => buildSubmitterRoomPlan(world?.policies ?? []), [world])

  const roomById = useMemo(
    () =>
      roomPlan.rooms.reduce(
        (acc, room) => {
          acc[room.slotId] = room
          return acc
        },
        {} as Record<BardoRoomSlotId, (typeof roomPlan.rooms)[number]>
      ),
    [roomPlan]
  )

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
      const roomId = roomPlan.policyRoomById[policy.policyId] ?? OVERFLOW_ROOM_SLOT_ID
      ensureActorState(actorStore, policy.policyId, roomId)
    }

    const tick = () => {
      const now = Date.now()
      const nextFrame: RenderedPolicy[] = []

      for (const policy of world.policies) {
        const roomId = roomPlan.policyRoomById[policy.policyId] ?? OVERFLOW_ROOM_SLOT_ID
        const room = roomById[roomId]
        const roomRect = BARDO_ROOM_UNIT_RECTS[roomId]
        const actor = ensureActorState(actorStore, policy.policyId, roomId)
        const busy = policy.activeJobIds.length > 0

        if (busy) {
          const portal = portalForPolicy(policy.policyId)
          const queueTarget = portalQueueTarget(policy.policyId, portal)
          actor.targetX = queueTarget.x
          actor.targetY = queueTarget.y

          if (distance(actor, portal) < PORTAL_CAPTURE_DISTANCE) {
            actor.hidden = true
          }
        } else {
          if (actor.hidden) {
            const roomEntry = roomSpawnPoint(policy.policyId, roomId)
            actor.hidden = false
            actor.x = roomEntry.x
            actor.y = roomEntry.y
            actor.targetX = roomEntry.x
            actor.targetY = roomEntry.y
            actor.nextRetargetAtMs = 0
          }

          const shouldRetarget =
            now >= actor.nextRetargetAtMs || distance(actor, { x: actor.targetX, y: actor.targetY }) < 0.018

          if (shouldRetarget) {
            actor.cycle += 1
            const nextTarget = pointInRect(`${policy.policyId}:${roomId}:wander`, roomRect, actor.cycle)
            actor.targetX = nextTarget.x
            actor.targetY = nextTarget.y
            actor.nextRetargetAtMs = now + nextTarget.lingerMs
          }
        }

        const easing = busy ? 0.18 : 0.11
        actor.x += (actor.targetX - actor.x) * easing
        actor.y += (actor.targetY - actor.y) * easing
        actor.x = clamp01(actor.x)
        actor.y = clamp01(actor.y)

        nextFrame.push({
          ...policy,
          x: actor.x,
          y: actor.y,
          hidden: busy && actor.hidden,
          busy,
          roomId,
          roomLabel: room?.label ?? 'Overflow Annex',
          spriteId: spriteForPolicy(policy.policyId),
          accentColor: accentForSubmitter(policy.userName || policy.userId),
        })
      }

      nextFrame.sort((left, right) => left.y - right.y || left.policyId.localeCompare(right.policyId))
      setRenderedPolicies(nextFrame)
    }

    tick()
    const interval = setInterval(tick, WORLD_STEP_MS)
    return () => clearInterval(interval)
  }, [roomById, roomPlan.policyRoomById, world])

  const visiblePolicies = useMemo(() => renderedPolicies.filter((policy) => !policy.hidden), [renderedPolicies])

  const hoveredPolicy = useMemo(
    () => visiblePolicies.find((policy) => policy.policyId === hoveredPolicyId) ?? null,
    [hoveredPolicyId, visiblePolicies]
  )

  const inEpisodeCount = world?.policies.filter((policy) => policy.activeJobIds.length > 0).length ?? 0
  const occupiedRoomsCount = roomPlan.rooms.filter((room) => room.policyCount > 0).length
  const totalPolicies = world?.policies.length ?? 0
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
            <p className="bardo-kicker">Gathering Grid</p>
            <h1>Bardo Lobby</h1>
            <p className="bardo-subtitle">
              Submitter rooms ring the map while episode portals line the north gate. Top submitters each get a room,
              and overflow submitters share the annex.
            </p>
          </div>
          <div className="bardo-stats" role="status" aria-live="polite">
            <p>
              <span>Policies</span>
              <strong>{totalPolicies}</strong>
            </p>
            <p>
              <span>Rooms active</span>
              <strong>
                {occupiedRoomsCount}/{roomPlan.rooms.length}
              </strong>
            </p>
            <p>
              <span>Portaling</span>
              <strong>{inEpisodeCount}</strong>
            </p>
          </div>
        </header>

        {errorMessage ? <div className="bardo-alert">{errorMessage}</div> : null}

        <div className="bardo-world" role="img" aria-label="Bardo lobby room grid">
          <div className="bardo-world-grid" />
          <div className="bardo-lobby-zone">
            <span>Commons Lobby</span>
          </div>

          {roomPlan.rooms.map((room) => {
            const rect = BARDO_ROOM_UNIT_RECTS[room.slotId]
            const width = rect.maxX - rect.minX
            const height = rect.maxY - rect.minY
            return (
              <div
                key={room.slotId}
                className={`bardo-room bardo-room-${room.edge} ${room.policyCount > 0 ? 'occupied' : ''}`}
                style={{
                  left: asPercent(rect.minX),
                  top: asPercent(rect.minY),
                  width: asPercent(width),
                  height: asPercent(height),
                }}
              >
                <p className="bardo-room-label">{room.label}</p>
                <p className="bardo-room-meta">
                  {room.policyCount} policy{room.policyCount === 1 ? '' : 'ies'}
                </p>
                {room.overflowSubmitters.length > 0 ? (
                  <p className="bardo-room-overflow" title={room.overflowSubmitters.join(', ')}>
                    {room.overflowSubmitters.join(', ')}
                  </p>
                ) : null}
              </div>
            )
          })}

          {BARDO_PORTALS.map((portal) => (
            <div
              key={portal.id}
              className="bardo-portal"
              style={{
                left: asPercent(portal.x),
                top: asPercent(portal.y),
              }}
            >
              <span>{portal.label}</span>
            </div>
          ))}

          {BARDO_LOBBY_DECORATIONS.map((decoration) => (
            <div
              key={decoration.id}
              className="bardo-decoration"
              style={{
                left: asPercent(decoration.x),
                top: asPercent(decoration.y),
              }}
              title={decoration.label}
            >
              <span className="bardo-sprite" style={atlasSpriteStyle(decoration.spriteId, 24)} />
            </div>
          ))}

          {visiblePolicies.map((policy) => (
            <button
              key={policy.policyId}
              type="button"
              className={`bardo-policy ${policy.busy ? 'busy' : ''}`}
              style={{
                left: asPercent(policy.x),
                top: asPercent(policy.y),
                borderColor: policy.accentColor,
                boxShadow: `0 0 0 2px color-mix(in srgb, ${policy.accentColor} 38%, transparent)`,
                zIndex: `${20 + Math.floor(policy.y * 120)}`,
              }}
              title={`${policy.name} • ${policy.userName}`}
              onMouseEnter={() => setHoveredPolicyId(policy.policyId)}
              onMouseLeave={() => setHoveredPolicyId((current) => (current === policy.policyId ? null : current))}
            >
              <span className="bardo-policy-sprite" style={atlasSpriteStyle(policy.spriteId, 30)} />
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
              <p className="bardo-tooltip-meta">Room: {hoveredPolicy.roomLabel}</p>
              <p className="bardo-tooltip-meta">
                {hoveredPolicy.busy
                  ? `Routing to ${portalForPolicy(hoveredPolicy.policyId).label}`
                  : `Waiting in ${hoveredPolicy.roomLabel}`}
              </p>
            </div>
          ) : null}

          {isLoading ? (
            <div className="bardo-loading">
              <span>Syncing lobby roster...</span>
            </div>
          ) : null}
        </div>

        <footer className="bardo-footer">
          <span>Updated {lastUpdatedLabel}</span>
          <span>Top submitters get dedicated rooms</span>
          <span>{world?.activeJobs.length ?? 0} active jobs</span>
          {nameFilter ? <span>Filter: “{nameFilter}”</span> : <span>All policies</span>}
        </footer>
      </section>
    </main>
  )
}
