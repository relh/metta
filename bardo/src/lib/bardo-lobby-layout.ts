import type { BardoPolicy, BardoSeason } from './types'

export type BardoUnitRect = {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export type BardoSeasonBuilding = {
  seasonId: string
  seasonName: string
  version: number
  compatVersion: string | null
  createdAt: string
  stageCount: number
  entrantCount: number
  activeEntrantCount: number
  label: string
  policyCount: number
  rect: BardoUnitRect
}

export type BardoSeasonPlan = {
  buildings: BardoSeasonBuilding[]
  policySeasonById: Record<string, string>
}

export type BardoPortal = {
  id: string
  label: string
  x: number
  y: number
}

export type BardoBuildingPortal = BardoPortal & {
  seasonId: string
  dockSide: 'left' | 'right'
}

const BUILDING_ZONE: BardoUnitRect = {
  minX: 0.13,
  minY: 0.25,
  maxX: 0.87,
  maxY: 0.78,
}

const OUTSIDE_ZONE: BardoUnitRect = {
  minX: 0.04,
  minY: 0.14,
  maxX: 0.96,
  maxY: 0.95,
}

const MIN_BUILDING_INSET_X = 0.012
const MIN_BUILDING_INSET_Y = 0.012
const MAX_BUILDING_COLUMNS = 4

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

function canonicalSeasonLabel(name: string): string {
  const trimmed = name.trim()
  if (!trimmed) return 'Unknown Season'
  return trimmed.replace(/[_-]+/g, ' ')
}

function buildingColumns(buildingCount: number): number {
  if (buildingCount <= 1) return 1
  if (buildingCount <= 4) return 2
  if (buildingCount <= 9) return 3
  return MAX_BUILDING_COLUMNS
}

function seasonOrderById(seasons: BardoSeason[]): Record<string, number> {
  return seasons.reduce(
    (acc, season, idx) => {
      acc[season.seasonId] = idx
      return acc
    },
    {} as Record<string, number>
  )
}

function policyPrimarySeasonId(policy: BardoPolicy, seasonOrder: Record<string, number>): string | null {
  if (policy.seasonIds.length === 0) return null
  const sorted = [...policy.seasonIds].sort((left, right) => {
    const leftOrder = seasonOrder[left] ?? Number.MAX_SAFE_INTEGER
    const rightOrder = seasonOrder[right] ?? Number.MAX_SAFE_INTEGER
    if (leftOrder !== rightOrder) return leftOrder - rightOrder
    return left.localeCompare(right)
  })
  return sorted[0] ?? null
}

export function buildSeasonBuildingPlan(policies: BardoPolicy[], seasons: BardoSeason[]): BardoSeasonPlan {
  if (seasons.length === 0) {
    return { buildings: [], policySeasonById: {} }
  }

  const seasonOrder = seasonOrderById(seasons)
  const policySeasonById: Record<string, string> = {}
  const policyCountBySeasonId: Record<string, number> = {}

  for (const season of seasons) {
    policyCountBySeasonId[season.seasonId] = 0
  }

  for (const policy of policies) {
    const seasonId = policyPrimarySeasonId(policy, seasonOrder)
    if (!seasonId) continue
    if (!(seasonId in policyCountBySeasonId)) continue
    policySeasonById[policy.policyId] = seasonId
    policyCountBySeasonId[seasonId] += 1
  }

  const columns = buildingColumns(seasons.length)
  const rows = Math.ceil(seasons.length / columns)
  const zoneWidth = BUILDING_ZONE.maxX - BUILDING_ZONE.minX
  const zoneHeight = BUILDING_ZONE.maxY - BUILDING_ZONE.minY
  const cellWidth = zoneWidth / columns
  const cellHeight = zoneHeight / rows
  const insetX = Math.max(MIN_BUILDING_INSET_X, cellWidth * 0.09)
  const insetY = Math.max(MIN_BUILDING_INSET_Y, cellHeight * 0.12)

  const buildings = seasons.map((season, idx) => {
    const col = idx % columns
    const row = Math.floor(idx / columns)
    const cellMinX = BUILDING_ZONE.minX + col * cellWidth
    const cellMinY = BUILDING_ZONE.minY + row * cellHeight
    const rect: BardoUnitRect = {
      minX: clamp01(cellMinX + insetX),
      minY: clamp01(cellMinY + insetY),
      maxX: clamp01(cellMinX + cellWidth - insetX),
      maxY: clamp01(cellMinY + cellHeight - insetY),
    }

    return {
      seasonId: season.seasonId,
      seasonName: season.name,
      version: season.version,
      compatVersion: season.compatVersion,
      createdAt: season.createdAt,
      stageCount: season.stageCount,
      entrantCount: season.entrantCount,
      activeEntrantCount: season.activeEntrantCount,
      label: `${canonicalSeasonLabel(season.name)} v${season.version}`,
      policyCount: policyCountBySeasonId[season.seasonId] ?? 0,
      rect,
    }
  })

  return {
    buildings,
    policySeasonById,
  }
}

export const BARDO_PORTALS: ReadonlyArray<BardoPortal> = [0.33, 0.44, 0.55, 0.66].map((x, idx) => ({
  id: `portal-${idx + 1}`,
  label: `Commons Portal ${idx + 1}`,
  x,
  y: 0.105,
}))

export function portalForPolicy(policyId: string): BardoPortal {
  return BARDO_PORTALS[hashString(`${policyId}:portal`) % BARDO_PORTALS.length]
}

export function buildBuildingPortals(buildings: ReadonlyArray<BardoSeasonBuilding>): BardoBuildingPortal[] {
  return buildings.map((building, idx) => {
    const dockSide: 'left' | 'right' = idx % 2 === 0 ? 'right' : 'left'
    const anchorX = dockSide === 'right' ? building.rect.maxX + 0.012 : building.rect.minX - 0.012
    const anchorY = building.rect.minY + (building.rect.maxY - building.rect.minY) * 0.33

    return {
      id: `building-portal:${building.seasonId}`,
      seasonId: building.seasonId,
      label: `${canonicalSeasonLabel(building.seasonName)} Episode Portal`,
      dockSide,
      x: clamp01(anchorX),
      y: clamp01(anchorY),
    }
  })
}

export function pointInRect(
  seedKey: string,
  rect: BardoUnitRect,
  cycle: number
): {
  x: number
  y: number
  lingerMs: number
} {
  const width = rect.maxX - rect.minX
  const height = rect.maxY - rect.minY
  return {
    x: rect.minX + width * seededUnit(`${seedKey}:x:${cycle}`),
    y: rect.minY + height * seededUnit(`${seedKey}:y:${cycle}`),
    lingerMs: 1600 + Math.floor(2300 * seededUnit(`${seedKey}:linger:${cycle}`)),
  }
}

function isInsideRect(point: { x: number; y: number }, rect: BardoUnitRect, margin = 0): boolean {
  return (
    point.x >= rect.minX - margin &&
    point.x <= rect.maxX + margin &&
    point.y >= rect.minY - margin &&
    point.y <= rect.maxY + margin
  )
}

export function pointOutsideBuildings(
  seedKey: string,
  buildings: ReadonlyArray<BardoSeasonBuilding>,
  cycle: number
): {
  x: number
  y: number
  lingerMs: number
} {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const point = {
      x: OUTSIDE_ZONE.minX + (OUTSIDE_ZONE.maxX - OUTSIDE_ZONE.minX) * seededUnit(`${seedKey}:x:${cycle}:${attempt}`),
      y: OUTSIDE_ZONE.minY + (OUTSIDE_ZONE.maxY - OUTSIDE_ZONE.minY) * seededUnit(`${seedKey}:y:${cycle}:${attempt}`),
    }

    const inPortalQueueBand = point.y < 0.2 && point.x > 0.24 && point.x < 0.76
    if (inPortalQueueBand) continue

    const collidesWithBuilding = buildings.some((building) => isInsideRect(point, building.rect, 0.018))
    if (collidesWithBuilding) continue

    return {
      x: point.x,
      y: point.y,
      lingerMs: 1700 + Math.floor(2400 * seededUnit(`${seedKey}:linger:${cycle}:${attempt}`)),
    }
  }

  return {
    x: 0.08 + 0.84 * seededUnit(`${seedKey}:fallback:x:${cycle}`),
    y: 0.84 + 0.1 * seededUnit(`${seedKey}:fallback:y:${cycle}`),
    lingerMs: 2200,
  }
}
