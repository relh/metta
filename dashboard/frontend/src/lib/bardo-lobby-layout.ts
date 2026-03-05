import type { BardoPolicy } from './bardo-types'

export type BardoGridRect = {
  col: number
  row: number
  width: number
  height: number
}

export type BardoUnitRect = {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export type BardoRoomEdge = 'west' | 'south' | 'east'
export type BardoRoomSlotId = 'west-a' | 'west-b' | 'south-a' | 'south-b' | 'south-c' | 'south-d' | 'east-a' | 'east-b'

export const BARDO_GRID_COLS = 48
export const BARDO_GRID_ROWS = 30

export const BARDO_ROOM_SLOTS: ReadonlyArray<{
  id: BardoRoomSlotId
  edge: BardoRoomEdge
  defaultLabel: string
  gridRect: BardoGridRect
}> = [
  {
    id: 'west-a',
    edge: 'west',
    defaultLabel: 'West Wing A',
    gridRect: { col: 1, row: 5, width: 8, height: 7 },
  },
  {
    id: 'west-b',
    edge: 'west',
    defaultLabel: 'West Wing B',
    gridRect: { col: 1, row: 13, width: 8, height: 7 },
  },
  {
    id: 'south-a',
    edge: 'south',
    defaultLabel: 'South Hall A',
    gridRect: { col: 9, row: 22, width: 8, height: 7 },
  },
  {
    id: 'south-b',
    edge: 'south',
    defaultLabel: 'South Hall B',
    gridRect: { col: 17, row: 22, width: 8, height: 7 },
  },
  {
    id: 'south-c',
    edge: 'south',
    defaultLabel: 'South Hall C',
    gridRect: { col: 25, row: 22, width: 8, height: 7 },
  },
  {
    id: 'south-d',
    edge: 'south',
    defaultLabel: 'South Hall D',
    gridRect: { col: 33, row: 22, width: 8, height: 7 },
  },
  {
    id: 'east-a',
    edge: 'east',
    defaultLabel: 'East Wing A',
    gridRect: { col: 39, row: 5, width: 8, height: 7 },
  },
  {
    id: 'east-b',
    edge: 'east',
    defaultLabel: 'Overflow Annex',
    gridRect: { col: 39, row: 13, width: 8, height: 7 },
  },
]

export const TOP_SUBMITTER_ROOM_LIMIT = BARDO_ROOM_SLOTS.length - 1
export const OVERFLOW_ROOM_SLOT_ID: BardoRoomSlotId = 'east-b'

export const BARDO_LOBBY_GRID_RECT: BardoGridRect = {
  col: 10,
  row: 5,
  width: 28,
  height: 16,
}

export type BardoPortal = {
  id: string
  label: string
  col: number
  row: number
  x: number
  y: number
}

function clamp01(value: number): number {
  if (value < 0) return 0
  if (value > 1) return 1
  return value
}

function toUnit(value: number, maxValue: number): number {
  return clamp01(value / maxValue)
}

export function gridRectToUnitRect(rect: BardoGridRect, paddingCells = 0.55): BardoUnitRect {
  return {
    minX: toUnit(rect.col + paddingCells, BARDO_GRID_COLS),
    minY: toUnit(rect.row + paddingCells, BARDO_GRID_ROWS),
    maxX: toUnit(rect.col + rect.width - paddingCells, BARDO_GRID_COLS),
    maxY: toUnit(rect.row + rect.height - paddingCells, BARDO_GRID_ROWS),
  }
}

function centerOfCell(col: number, row: number): { x: number; y: number } {
  return {
    x: toUnit(col + 0.5, BARDO_GRID_COLS),
    y: toUnit(row + 0.5, BARDO_GRID_ROWS),
  }
}

export const BARDO_ROOM_UNIT_RECTS: Record<BardoRoomSlotId, BardoUnitRect> = BARDO_ROOM_SLOTS.reduce(
  (acc, slot) => {
    acc[slot.id] = gridRectToUnitRect(slot.gridRect)
    return acc
  },
  {} as Record<BardoRoomSlotId, BardoUnitRect>
)

export const BARDO_LOBBY_UNIT_RECT = gridRectToUnitRect(BARDO_LOBBY_GRID_RECT, 0.2)

export const BARDO_PORTALS: ReadonlyArray<BardoPortal> = [18, 22, 26, 30].map((col, idx) => {
  const { x, y } = centerOfCell(col, 2)
  return {
    id: `portal-${idx + 1}`,
    label: `Episode Portal ${idx + 1}`,
    col,
    row: 2,
    x,
    y,
  }
})

export type BardoSubmitterRoom = {
  slotId: BardoRoomSlotId
  edge: BardoRoomEdge
  submitter: string | null
  label: string
  policyCount: number
  overflowSubmitters: string[]
}

export type BardoRoomPlan = {
  rooms: BardoSubmitterRoom[]
  policyRoomById: Record<string, BardoRoomSlotId>
  submitterCounts: Array<{ submitter: string; count: number }>
}

function canonicalSubmitter(policy: BardoPolicy): string {
  const userName = policy.userName.trim()
  if (userName.length > 0) return userName
  const userId = policy.userId.trim()
  if (userId.length > 0) return userId
  return 'Unknown submitter'
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

export function buildSubmitterRoomPlan(policies: BardoPolicy[]): BardoRoomPlan {
  const grouped = new Map<string, BardoPolicy[]>()

  for (const policy of policies) {
    const submitter = canonicalSubmitter(policy)
    const current = grouped.get(submitter)
    if (current) {
      current.push(policy)
      continue
    }
    grouped.set(submitter, [policy])
  }

  const submitterCounts = [...grouped.entries()]
    .map(([submitter, submitterPolicies]) => ({
      submitter,
      count: submitterPolicies.length,
    }))
    .sort((left, right) => right.count - left.count || left.submitter.localeCompare(right.submitter))

  const dedicatedSubmitters = submitterCounts.slice(0, TOP_SUBMITTER_ROOM_LIMIT)
  const overflowSubmitters = submitterCounts.slice(TOP_SUBMITTER_ROOM_LIMIT)

  const policyRoomById: Record<string, BardoRoomSlotId> = {}

  const rooms = BARDO_ROOM_SLOTS.map((slot, roomIndex) => {
    if (slot.id === OVERFLOW_ROOM_SLOT_ID) {
      const overflowPolicyCount = overflowSubmitters.reduce((sum, entry) => sum + entry.count, 0)
      for (const entry of overflowSubmitters) {
        const submitterPolicies = grouped.get(entry.submitter) ?? []
        for (const policy of submitterPolicies) {
          policyRoomById[policy.policyId] = slot.id
        }
      }

      return {
        slotId: slot.id,
        edge: slot.edge,
        submitter: overflowSubmitters.length > 0 ? 'Overflow' : null,
        label: overflowSubmitters.length > 0 ? `Overflow (${overflowSubmitters.length})` : slot.defaultLabel,
        policyCount: overflowPolicyCount,
        overflowSubmitters: overflowSubmitters.map((entry) => entry.submitter),
      }
    }

    const dedicated = dedicatedSubmitters[roomIndex]
    if (!dedicated) {
      return {
        slotId: slot.id,
        edge: slot.edge,
        submitter: null,
        label: slot.defaultLabel,
        policyCount: 0,
        overflowSubmitters: [],
      }
    }

    const submitterPolicies = grouped.get(dedicated.submitter) ?? []
    for (const policy of submitterPolicies) {
      policyRoomById[policy.policyId] = slot.id
    }

    return {
      slotId: slot.id,
      edge: slot.edge,
      submitter: dedicated.submitter,
      label: dedicated.submitter,
      policyCount: dedicated.count,
      overflowSubmitters: [],
    }
  })

  return {
    rooms,
    policyRoomById,
    submitterCounts,
  }
}

export type BardoSpriteId = 'miner' | 'scout' | 'aligner' | 'scrambler' | 'hub' | 'junction' | 'charger' | 'chest'

export type BardoSpriteFrame = {
  x: number
  y: number
  width: number
  height: number
}

export const BARDO_ATLAS_SIZE = 256

export const BARDO_SPRITE_FRAMES: Record<BardoSpriteId, BardoSpriteFrame> = {
  miner: { x: 167, y: 4, width: 33, height: 33 },
  scout: { x: 4, y: 103, width: 33, height: 33 },
  aligner: { x: 144, y: 86, width: 33, height: 33 },
  scrambler: { x: 208, y: 25, width: 33, height: 33 },
  hub: { x: 45, y: 4, width: 33, height: 33 },
  junction: { x: 45, y: 127, width: 33, height: 33 },
  charger: { x: 103, y: 86, width: 33, height: 33 },
  chest: { x: 103, y: 45, width: 33, height: 33 },
}

export const BARDO_POLICY_SPRITES: ReadonlyArray<BardoSpriteId> = ['miner', 'scout', 'aligner', 'scrambler']

export function spriteForPolicy(policyId: string): BardoSpriteId {
  return BARDO_POLICY_SPRITES[hashString(policyId) % BARDO_POLICY_SPRITES.length]
}

export function portalForPolicy(policyId: string): BardoPortal {
  return BARDO_PORTALS[hashString(`${policyId}:portal`) % BARDO_PORTALS.length]
}

export function accentForSubmitter(submitter: string): string {
  const hue = Math.floor(seededUnit(`${submitter}:h`) * 360)
  const saturation = 58 + Math.floor(seededUnit(`${submitter}:s`) * 22)
  const lightness = 46 + Math.floor(seededUnit(`${submitter}:l`) * 12)
  return `hsl(${hue} ${saturation}% ${lightness}%)`
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
    lingerMs: 1700 + Math.floor(2300 * seededUnit(`${seedKey}:linger:${cycle}`)),
  }
}

export type BardoLobbyDecoration = {
  id: string
  label: string
  spriteId: BardoSpriteId
  x: number
  y: number
}

export const BARDO_LOBBY_DECORATIONS: ReadonlyArray<BardoLobbyDecoration> = [
  { id: 'hub-core', label: 'Hub', spriteId: 'hub', x: 0.5, y: 0.46 },
  { id: 'junction-west', label: 'Junction', spriteId: 'junction', x: 0.38, y: 0.46 },
  { id: 'junction-east', label: 'Junction', spriteId: 'junction', x: 0.62, y: 0.46 },
  { id: 'charger-north', label: 'Charger', spriteId: 'charger', x: 0.44, y: 0.34 },
  { id: 'charger-east', label: 'Charger', spriteId: 'charger', x: 0.56, y: 0.34 },
  { id: 'chest-center', label: 'Chest', spriteId: 'chest', x: 0.5, y: 0.6 },
]
