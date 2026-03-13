'use client'

import {
  startTransition,
  type CSSProperties,
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import Image from 'next/image'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'

import {
  BARDO_PORTALS,
  buildBuildingPortals,
  buildSeasonBuildingPlan,
  pointInRect,
  pointOutsideBuildings,
  portalForPolicy,
  type BardoBuildingPortal,
  type BardoSeasonBuilding,
} from '../lib/bardo-lobby-layout'
import type { BardoPolicy, BardoWorldState } from '../lib/types'

const AUTH_COOKIE_NAME = process.env.NEXT_PUBLIC_OBSERVATORY_AUTH_COOKIE_NAME?.trim() || 'observatory_auth_token'
const BARDO_BASE_PATH = (process.env.NEXT_PUBLIC_BARDO_BASE_PATH?.trim() || '').replace(/\/$/, '')
const BARDO_AUTH_TOKEN_SESSION_STORAGE_KEY = 'bardo-auth-token'
const WORLD_POLL_MS = 5_000
const WORLD_STEP_MS = 70
const PORTAL_CAPTURE_DISTANCE = 0.03
const LIVE_STALE_MS = WORLD_POLL_MS * 3

export function prefixBardoPath(basePath: string, path: string): string {
  const normalizedBasePath = basePath.trim().replace(/\/$/, '')
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  return `${normalizedBasePath}${normalizedPath}`
}

const WORLD_STATE_ENDPOINT = prefixBardoPath(BARDO_BASE_PATH, '/api/world-state')
const METTASCOPE_BUILDING_SPRITES = [
  '/assets/mettascope/objects/hub.png',
  '/assets/mettascope/objects/hub.working.png',
  '/assets/mettascope/objects/hub.ready.png',
  '/assets/mettascope/objects/factory.png',
  '/assets/mettascope/objects/lab.png',
  '/assets/mettascope/objects/temple.png',
  '/assets/mettascope/objects/armory.png',
  '/assets/mettascope/objects/converter.png',
].map((path) => prefixBardoPath(BARDO_BASE_PATH, path))
const METTASCOPE_PORTAL_SPRITES = [
  '/assets/mettascope/objects/junction.png',
  '/assets/mettascope/objects/junction.working.png',
  '/assets/mettascope/objects/generator_blue.png',
  '/assets/mettascope/objects/charger.png',
].map((path) => prefixBardoPath(BARDO_BASE_PATH, path))
const METTASCOPE_POLICY_SPRITES = [
  '/assets/mettascope/objects/aligner.png',
  '/assets/mettascope/objects/miner.png',
  '/assets/mettascope/objects/scout.png',
  '/assets/mettascope/objects/scrambler.png',
].map((path) => prefixBardoPath(BARDO_BASE_PATH, path))
const METTASCOPE_CARRIER_SPRITE = prefixBardoPath(BARDO_BASE_PATH, '/assets/mettascope/objects/ship.png')
const BARDO_WALL_ATLAS = prefixBardoPath(BARDO_BASE_PATH, '/assets/mettascope/wall_atlas.png')

type ActorState = {
  x: number
  y: number
  targetX: number
  targetY: number
  cycle: number
  nextRetargetAtMs: number
  hidden: boolean
  homeKey: string
}

type RenderedPolicy = BardoPolicy & {
  x: number
  y: number
  hidden: boolean
  busy: boolean
  color: string
  initials: string
  seasonId: string | null
  seasonLabel: string
  submittedSeasonCount: number
  activePortalLabel: string
  motionPhaseMs: number
  sprite: string
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

function colorForPolicy(policyId: string): string {
  const hue = Math.floor(seededUnit(`${policyId}:h`) * 360)
  const saturation = 62 + Math.floor(seededUnit(`${policyId}:s`) * 16)
  const lightness = 46 + Math.floor(seededUnit(`${policyId}:l`) * 12)
  return `hsl(${hue} ${saturation}% ${lightness}%)`
}

function spriteFromSeed(seed: string, sprites: readonly string[]): string {
  return sprites[hashString(seed) % sprites.length]
}

function policyInitials(name: string): string {
  const tokens = name
    .split(/[._-]+/)
    .map((token) => token.trim())
    .filter((token) => token.length > 0)

  if (tokens.length === 0) return name.slice(0, 2).toUpperCase()
  if (tokens.length === 1) return tokens[0].slice(0, 2).toUpperCase()
  return `${tokens[0][0]}${tokens[tokens.length - 1][0]}`.toUpperCase()
}

function toErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function isAbortError(error: unknown): boolean {
  if (error instanceof DOMException) return error.name === 'AbortError'
  return error instanceof Error && error.name === 'AbortError'
}

function asPercent(value: number): string {
  return `${(clamp01(value) * 100).toFixed(3)}%`
}

function secondsSince(fromMs: number, toMs: number): number {
  return Math.max(0, Math.floor((toMs - fromMs) / 1000))
}

function freshnessLabel(lastRefreshAtMs: number | null, nowMs: number): string {
  if (!lastRefreshAtMs) return '—'
  const ageSeconds = secondsSince(lastRefreshAtMs, nowMs)
  if (ageSeconds < 60) return `${ageSeconds}s ago`
  const minutes = Math.floor(ageSeconds / 60)
  return `${minutes}m ago`
}

function portalQueueTarget(
  policyId: string,
  portal: BardoBuildingPortal | { id: string; x: number; y: number }
): {
  x: number
  y: number
} {
  return {
    x: clamp01(portal.x - 0.03 + 0.06 * seededUnit(`${policyId}:${portal.id}:x`)),
    y: clamp01(portal.y + 0.03 + 0.07 * seededUnit(`${policyId}:${portal.id}:y`)),
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

function ensureActorState(
  store: Map<string, ActorState>,
  policyId: string,
  spawn: { x: number; y: number },
  homeKey: string
): ActorState {
  const existing = store.get(policyId)
  if (existing) {
    if (existing.homeKey === homeKey) return existing

    existing.homeKey = homeKey
    existing.hidden = false
    existing.x = spawn.x
    existing.y = spawn.y
    existing.targetX = spawn.x
    existing.targetY = spawn.y
    existing.cycle = 0
    existing.nextRetargetAtMs = 0
    return existing
  }

  const actorState: ActorState = {
    x: spawn.x,
    y: spawn.y,
    targetX: spawn.x,
    targetY: spawn.y,
    cycle: 0,
    nextRetargetAtMs: 0,
    hidden: false,
    homeKey,
  }

  store.set(policyId, actorState)
  return actorState
}

function homeSpawnPoint(
  policyId: string,
  seasonId: string | null,
  buildingBySeasonId: Record<string, BardoSeasonBuilding>,
  buildings: ReadonlyArray<BardoSeasonBuilding>
): { x: number; y: number } {
  if (!seasonId) {
    return pointOutsideBuildings(`${policyId}:outside:spawn`, buildings, 0)
  }

  const building = buildingBySeasonId[seasonId]
  if (!building) {
    return pointOutsideBuildings(`${policyId}:outside:spawn`, buildings, 0)
  }

  return pointInRect(`${policyId}:${seasonId}:spawn`, building.rect, 0)
}

function actorHomeKey(
  seasonId: string | null,
  building: BardoSeasonBuilding | undefined,
  buildingCount: number
): string {
  if (!seasonId || !building) return `outside:${buildingCount}`
  const { minX, minY, maxX, maxY } = building.rect
  return `season:${seasonId}:${minX.toFixed(3)}:${minY.toFixed(3)}:${maxX.toFixed(3)}:${maxY.toFixed(3)}`
}

export function BardoLobby() {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const nameFilter = searchParams.get('q')?.trim() || ''
  const requestedTheme = searchParams.get('theme')

  const [world, setWorld] = useState<BardoWorldState | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [renderedPolicies, setRenderedPolicies] = useState<RenderedPolicy[]>([])
  const [hoveredPolicyId, setHoveredPolicyId] = useState<string | null>(null)
  const [lastRefreshAtMs, setLastRefreshAtMs] = useState<number | null>(null)
  const [nowMs, setNowMs] = useState<number>(() => Date.now())
  const [draftNameFilter, setDraftNameFilter] = useState(nameFilter)

  const actorsRef = useRef<Map<string, ActorState>>(new Map())
  const worldStateEtagRef = useRef<string | null>(null)
  const worldStateAbortRef = useRef<AbortController | null>(null)
  const bardoStyleVariables = useMemo(
    () =>
      ({
        '--bardo-wall-atlas': `url('${BARDO_WALL_ATLAS}')`,
      }) as CSSProperties,
    []
  )

  useEffect(() => {
    if (requestedTheme !== 'dark' && requestedTheme !== 'light') {
      document.documentElement.removeAttribute('data-theme')
      return
    }
    document.documentElement.setAttribute('data-theme', requestedTheme)
  }, [requestedTheme])

  useEffect(() => {
    worldStateEtagRef.current = null
  }, [nameFilter])

  useEffect(() => {
    setDraftNameFilter(nameFilter)
  }, [nameFilter])

  const replaceFilterUrl = useCallback(
    (nextFilter: string) => {
      const params = new URLSearchParams(searchParams.toString())
      if (nextFilter) {
        params.set('q', nextFilter)
      } else {
        params.delete('q')
      }
      const query = params.toString()
      const href = query ? `${pathname}?${query}` : pathname
      startTransition(() => {
        router.replace(href)
      })
    },
    [pathname, router, searchParams]
  )

  const submitFilter = useCallback(
    (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      replaceFilterUrl(draftNameFilter.trim())
    },
    [draftNameFilter, replaceFilterUrl]
  )

  const clearFilter = useCallback(() => {
    setDraftNameFilter('')
    replaceFilterUrl('')
  }, [replaceFilterUrl])

  const loadWorldState = useCallback(
    async (signal: AbortSignal) => {
      const query = new URLSearchParams()
      if (nameFilter) query.set('q', nameFilter)
      const endpoint = query.size > 0 ? `${WORLD_STATE_ENDPOINT}?${query.toString()}` : WORLD_STATE_ENDPOINT

      const authToken = resolveBardoAuthToken()
      const headers: Record<string, string> = {}
      if (authToken) headers['X-Auth-Token'] = authToken
      if (worldStateEtagRef.current) headers['If-None-Match'] = worldStateEtagRef.current

      const response = await fetch(endpoint, {
        cache: 'no-store',
        headers: Object.keys(headers).length > 0 ? headers : undefined,
        signal,
      })

      if (response.status === 304) {
        setLastRefreshAtMs(Date.now())
        return
      }

      if (!response.ok) {
        const payload = (await response.json().catch(() => ({ error: '' }))) as { error?: string }
        throw new Error(payload.error || `Bardo request failed (${response.status})`)
      }

      const etag = response.headers.get('etag')?.trim()
      if (etag) {
        worldStateEtagRef.current = etag
      }

      const payload = (await response.json()) as BardoWorldState
      setWorld(payload)
      setLastRefreshAtMs(Date.now())
    },
    [nameFilter]
  )

  useEffect(() => {
    const interval = setInterval(() => {
      setNowMs(Date.now())
    }, 1_000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    let cancelled = false
    let inFlight = false

    const refresh = async () => {
      if (inFlight) return
      inFlight = true
      const controller = new AbortController()
      worldStateAbortRef.current = controller
      try {
        await loadWorldState(controller.signal)
        if (!cancelled) {
          setErrorMessage(null)
          setIsLoading(false)
        }
      } catch (error) {
        if (isAbortError(error)) return
        if (!cancelled) {
          setErrorMessage(toErrorMessage(error))
          setIsLoading(false)
        }
      } finally {
        if (worldStateAbortRef.current === controller) {
          worldStateAbortRef.current = null
        }
        inFlight = false
      }
    }

    void refresh()
    const interval = setInterval(() => {
      void refresh()
    }, WORLD_POLL_MS)

    return () => {
      cancelled = true
      worldStateAbortRef.current?.abort()
      worldStateAbortRef.current = null
      clearInterval(interval)
    }
  }, [loadWorldState])

  const seasonPlan = useMemo(() => buildSeasonBuildingPlan(world?.policies ?? [], world?.seasons ?? []), [world])
  const buildingPortals = useMemo(() => buildBuildingPortals(seasonPlan.buildings), [seasonPlan.buildings])

  const buildingBySeasonId = useMemo(
    () =>
      seasonPlan.buildings.reduce(
        (acc, building) => {
          acc[building.seasonId] = building
          return acc
        },
        {} as Record<string, BardoSeasonBuilding>
      ),
    [seasonPlan.buildings]
  )
  const buildingPortalBySeasonId = useMemo(
    () =>
      buildingPortals.reduce(
        (acc, portal) => {
          acc[portal.seasonId] = portal
          return acc
        },
        {} as Record<string, BardoBuildingPortal>
      ),
    [buildingPortals]
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
      const seasonId = seasonPlan.policySeasonById[policy.policyId] ?? null
      const building = seasonId ? buildingBySeasonId[seasonId] : undefined
      const spawn = homeSpawnPoint(policy.policyId, seasonId, buildingBySeasonId, seasonPlan.buildings)
      const homeKey = actorHomeKey(seasonId, building, seasonPlan.buildings.length)
      ensureActorState(actorStore, policy.policyId, spawn, homeKey)
    }

    const tick = () => {
      const now = Date.now()
      const nextFrame: RenderedPolicy[] = []

      for (const policy of world.policies) {
        const seasonId = seasonPlan.policySeasonById[policy.policyId] ?? null
        const building = seasonId ? buildingBySeasonId[seasonId] : undefined
        const buildingPortal = seasonId ? buildingPortalBySeasonId[seasonId] : undefined
        const activePortal = buildingPortal ?? portalForPolicy(policy.policyId)
        const spawn = homeSpawnPoint(policy.policyId, seasonId, buildingBySeasonId, seasonPlan.buildings)
        const homeKey = actorHomeKey(seasonId, building, seasonPlan.buildings.length)
        const actor = ensureActorState(actorStore, policy.policyId, spawn, homeKey)
        const busy = policy.activeJobIds.length > 0

        if (busy) {
          const queueTarget = portalQueueTarget(policy.policyId, activePortal)
          actor.targetX = queueTarget.x
          actor.targetY = queueTarget.y

          if (distance(actor, activePortal) < PORTAL_CAPTURE_DISTANCE) {
            actor.hidden = true
          }
        } else {
          if (actor.hidden) {
            actor.hidden = false
            actor.x = spawn.x
            actor.y = spawn.y
            actor.targetX = spawn.x
            actor.targetY = spawn.y
            actor.nextRetargetAtMs = 0
          }

          const shouldRetarget =
            now >= actor.nextRetargetAtMs || distance(actor, { x: actor.targetX, y: actor.targetY }) < 0.018

          if (shouldRetarget) {
            actor.cycle += 1
            const nextTarget = building
              ? pointInRect(`${policy.policyId}:${seasonId}:wander`, building.rect, actor.cycle)
              : pointOutsideBuildings(`${policy.policyId}:outside:wander`, seasonPlan.buildings, actor.cycle)
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
          color: colorForPolicy(policy.policyId),
          initials: policyInitials(policy.name),
          seasonId,
          seasonLabel: building?.label ?? 'Outside Commons',
          submittedSeasonCount: policy.seasonIds.length,
          activePortalLabel: activePortal.label,
          motionPhaseMs: Math.floor(seededUnit(`${policy.policyId}:motion`) * 2_400),
          sprite: spriteFromSeed(`${policy.policyId}:role`, METTASCOPE_POLICY_SPRITES),
        })
      }

      nextFrame.sort((left, right) => left.y - right.y || left.policyId.localeCompare(right.policyId))
      setRenderedPolicies(nextFrame)
    }

    tick()
    const interval = setInterval(tick, WORLD_STEP_MS)
    return () => clearInterval(interval)
  }, [buildingBySeasonId, buildingPortalBySeasonId, seasonPlan.buildings, seasonPlan.policySeasonById, world])

  const visiblePolicies = useMemo(() => renderedPolicies.filter((policy) => !policy.hidden), [renderedPolicies])

  const hoveredPolicy = useMemo(
    () => visiblePolicies.find((policy) => policy.policyId === hoveredPolicyId) ?? null,
    [hoveredPolicyId, visiblePolicies]
  )

  const shownPolicyCount = world?.policies.length ?? 0
  const totalPolicies = world?.totalPolicies ?? shownPolicyCount
  const isSampledView = shownPolicyCount < totalPolicies
  const submittedCount = world?.policies.filter((policy) => policy.seasonIds.length > 0).length ?? 0
  const outsideCount = shownPolicyCount - submittedCount
  const inEpisodeCount = world?.policies.filter((policy) => policy.activeJobIds.length > 0).length ?? 0
  const busyCountBySeasonId = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const policy of renderedPolicies) {
      if (!policy.busy || !policy.seasonId) continue
      counts[policy.seasonId] = (counts[policy.seasonId] ?? 0) + 1
    }
    return counts
  }, [renderedPolicies])
  const freshness = freshnessLabel(lastRefreshAtMs, nowMs)
  const isLive = lastRefreshAtMs !== null && nowMs - lastRefreshAtMs <= LIVE_STALE_MS
  const lastUpdatedLabel = world
    ? new Date(world.generatedAt).toLocaleTimeString([], {
        hour: 'numeric',
        minute: '2-digit',
        second: '2-digit',
      })
    : '—'
  const filterSummary = nameFilter
    ? `Filter: "${nameFilter}"`
    : isSampledView
      ? `Showing ${shownPolicyCount} of ${totalPolicies} policies`
      : `Showing all ${shownPolicyCount} policies`
  const filterDetail = nameFilter
    ? 'Matching policy and owner names across the district.'
    : 'Search by policy name or owner to jump to a slice of the district.'

  return (
    <main className="bardo-shell" style={bardoStyleVariables}>
      <section className="bardo-card">
        <header className="bardo-header">
          <div>
            <p className="bardo-kicker">Tournament District</p>
            <h1>Bardo Lobby</h1>
            <p className="bardo-subtitle">
              Aboard the station, each tournament season has its own habitat tower. Submitted policies drift inside
              those towers, while unsubmitted policies roam the outer concourse.
            </p>
          </div>
          <div className="bardo-stats" role="status" aria-live="polite">
            <p>
              <span>{isSampledView ? 'Shown' : 'Policies'}</span>
              <strong>{shownPolicyCount}</strong>
            </p>
            <p>
              <span>{isSampledView ? 'Total policies' : 'Buildings'}</span>
              <strong>{isSampledView ? totalPolicies : seasonPlan.buildings.length}</strong>
            </p>
            <p>
              <span>{isSampledView ? 'Buildings' : 'In episode'}</span>
              <strong>{isSampledView ? seasonPlan.buildings.length : inEpisodeCount}</strong>
            </p>
            <p>
              <span>Active jobs</span>
              <strong>{world?.activeJobs.length ?? 0}</strong>
            </p>
          </div>
        </header>

        <section className="bardo-controls">
          <form className="bardo-filter-form" role="search" onSubmit={submitFilter}>
            <label className="bardo-filter-label" htmlFor="bardo-policy-filter">
              Filter policies
            </label>
            <div className="bardo-filter-row">
              <input
                id="bardo-policy-filter"
                className="bardo-filter-input"
                type="search"
                value={draftNameFilter}
                placeholder="Search by policy or owner"
                onChange={(event) => setDraftNameFilter(event.target.value)}
              />
              <button className="bardo-filter-button" type="submit">
                Apply
              </button>
              {nameFilter ? (
                <button
                  className="bardo-filter-button bardo-filter-button-secondary"
                  type="button"
                  onClick={clearFilter}
                >
                  Clear
                </button>
              ) : null}
            </div>
          </form>
          <p className="bardo-filter-summary">{filterDetail}</p>
        </section>

        {errorMessage ? <div className="bardo-alert">{errorMessage}</div> : null}

        <div className="bardo-world" role="img" aria-label="Bardo station with tournament towers and roaming policies">
          <div className="bardo-spacefield" />
          <div className="bardo-hull-shadow" />
          <div className="bardo-mettascope-overlay" />
          <div className="bardo-world-glow" />
          <div className="bardo-world-grid" />
          <div className="bardo-station-ring" />
          <div className="bardo-observation-deck" />
          <div className="bardo-carrier">
            <Image
              className="bardo-carrier-sprite"
              src={METTASCOPE_CARRIER_SPRITE}
              alt=""
              aria-hidden="true"
              width={512}
              height={512}
              unoptimized
            />
          </div>
          <div className="bardo-commons-label">
            <span>Outside Commons</span>
          </div>

          {seasonPlan.buildings.map((building) => (
            <div
              key={building.seasonId}
              className={`bardo-building ${building.policyCount > 0 ? 'occupied' : ''}`}
              style={{
                left: asPercent(building.rect.minX),
                top: asPercent(building.rect.minY),
                width: asPercent(building.rect.maxX - building.rect.minX),
                height: asPercent(building.rect.maxY - building.rect.minY),
              }}
            >
              <Image
                className="bardo-building-sprite"
                src={spriteFromSeed(`building:${building.seasonId}`, METTASCOPE_BUILDING_SPRITES)}
                alt=""
                aria-hidden="true"
                width={256}
                height={256}
                unoptimized
              />
              <p className="bardo-building-name">{building.label}</p>
              <div className="bardo-building-signals">
                {[0, 1, 2].map((idx) => (
                  <span
                    key={`${building.seasonId}:signal:${idx}`}
                    className={idx < Math.min(3, busyCountBySeasonId[building.seasonId] ?? 0) ? 'active' : ''}
                  />
                ))}
              </div>
              <p className="bardo-building-meta">
                {building.policyCount} visible · {building.activeEntrantCount}/{building.entrantCount} active
              </p>
              <p className="bardo-building-meta">
                Compat {building.compatVersion ?? 'n/a'} · {building.stageCount} stage
                {building.stageCount === 1 ? '' : 's'}
              </p>
              <div className="bardo-building-door" />
            </div>
          ))}

          {buildingPortals.map((portal) => (
            <div
              key={portal.id}
              className={`bardo-building-portal bardo-building-portal-${portal.dockSide} ${
                (busyCountBySeasonId[portal.seasonId] ?? 0) > 0 ? 'active' : ''
              }`}
              style={{
                left: asPercent(portal.x),
                top: asPercent(portal.y),
              }}
            >
              <Image
                className="bardo-portal-sprite"
                src={spriteFromSeed(`portal:${portal.seasonId}`, METTASCOPE_PORTAL_SPRITES)}
                alt=""
                aria-hidden="true"
                width={256}
                height={256}
                unoptimized
              />
              <span>{portal.label}</span>
            </div>
          ))}
          {BARDO_PORTALS.map((portal) => (
            <div
              key={portal.id}
              className="bardo-portal bardo-commons-portal"
              style={{
                left: asPercent(portal.x),
                top: asPercent(portal.y),
              }}
              title={portal.label}
            />
          ))}

          {visiblePolicies.map((policy) => (
            <button
              key={policy.policyId}
              type="button"
              className={`bardo-policy ${policy.busy ? 'busy' : ''} ${policy.seasonId ? 'inside' : 'outside'}`}
              style={{
                left: asPercent(policy.x),
                top: asPercent(policy.y),
                backgroundColor: policy.color,
                animationDelay: `${policy.motionPhaseMs}ms`,
              }}
              title={`${policy.name} • ${policy.userName} • ${policy.seasonLabel}`}
              onMouseEnter={() => setHoveredPolicyId(policy.policyId)}
              onMouseLeave={() => setHoveredPolicyId((current) => (current === policy.policyId ? null : current))}
            >
              <Image
                className="bardo-policy-sprite"
                src={policy.sprite}
                alt=""
                aria-hidden="true"
                width={192}
                height={192}
                unoptimized
              />
              <span className="bardo-policy-initials">{policy.initials}</span>
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
              <p className="bardo-tooltip-meta">Location: {hoveredPolicy.seasonLabel}</p>
              {hoveredPolicy.submittedSeasonCount > 1 ? (
                <p className="bardo-tooltip-meta">Submitted to {hoveredPolicy.submittedSeasonCount} seasons</p>
              ) : null}
              <p className="bardo-tooltip-meta">
                {hoveredPolicy.busy
                  ? `Routing to ${hoveredPolicy.activePortalLabel}`
                  : hoveredPolicy.seasonId
                    ? `Inside ${hoveredPolicy.seasonLabel}`
                    : 'Wandering outside all season buildings'}
              </p>
            </div>
          ) : null}

          {isLoading ? (
            <div className="bardo-loading">
              <span>Loading tournament district...</span>
            </div>
          ) : null}
        </div>

        <footer className="bardo-footer">
          <span className={`bardo-footer-live ${isLive ? 'is-live' : 'is-stale'}`}>
            {isLive ? 'Live' : 'Stale'} · {freshness}
          </span>
          <span>Auto refresh {WORLD_POLL_MS / 1_000}s</span>
          <span>Updated {lastUpdatedLabel}</span>
          <span>{outsideCount} outside buildings in view</span>
          <span>{filterSummary}</span>
        </footer>
      </section>
    </main>
  )
}
