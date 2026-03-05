import { describe, expect, it } from 'vitest'

import type { BardoPolicy } from './bardo-types'
import {
  BARDO_POLICY_SPRITES,
  BARDO_ROOM_SLOTS,
  BARDO_ROOM_UNIT_RECTS,
  OVERFLOW_ROOM_SLOT_ID,
  TOP_SUBMITTER_ROOM_LIMIT,
  buildSubmitterRoomPlan,
  portalForPolicy,
  spriteForPolicy,
} from './bardo-lobby-layout'

function makePolicy(policyId: string, userName: string): BardoPolicy {
  return {
    policyId,
    policyVersionId: `${policyId}-v1`,
    name: policyId,
    userId: userName,
    userName,
    createdAt: '2026-03-05T00:00:00Z',
    activeJobIds: [],
  }
}

describe('buildSubmitterRoomPlan', () => {
  it('assigns top submitters to dedicated rooms and groups the rest into overflow', () => {
    const policies = [
      makePolicy('relh-1', 'relh'),
      makePolicy('relh-2', 'relh'),
      makePolicy('relh-3', 'relh'),
      makePolicy('alice-1', 'alice'),
      makePolicy('alice-2', 'alice'),
      makePolicy('bob-1', 'bob'),
      makePolicy('bob-2', 'bob'),
      makePolicy('carol-1', 'carol'),
      makePolicy('carol-2', 'carol'),
      makePolicy('dave-1', 'dave'),
      makePolicy('eve-1', 'eve'),
      makePolicy('frank-1', 'frank'),
      makePolicy('grace-1', 'grace'),
      makePolicy('hank-1', 'hank'),
    ]

    const plan = buildSubmitterRoomPlan(policies)

    expect(plan.rooms.length).toBe(BARDO_ROOM_SLOTS.length)
    expect(TOP_SUBMITTER_ROOM_LIMIT).toBe(7)

    const dedicatedSubmitters = plan.rooms.slice(0, TOP_SUBMITTER_ROOM_LIMIT).map((room) => room.submitter)
    expect(dedicatedSubmitters).toEqual(['relh', 'alice', 'bob', 'carol', 'dave', 'eve', 'frank'])

    const overflow = plan.rooms.find((room) => room.slotId === OVERFLOW_ROOM_SLOT_ID)
    expect(overflow).toBeTruthy()
    expect(overflow?.policyCount).toBe(2)
    expect(overflow?.overflowSubmitters).toEqual(['grace', 'hank'])
    expect(plan.policyRoomById['grace-1']).toBe(OVERFLOW_ROOM_SLOT_ID)
    expect(plan.policyRoomById['hank-1']).toBe(OVERFLOW_ROOM_SLOT_ID)
  })

  it('keeps overflow room empty when there are not enough submitters', () => {
    const plan = buildSubmitterRoomPlan([
      makePolicy('relh-1', 'relh'),
      makePolicy('relh-2', 'relh'),
      makePolicy('alice-1', 'alice'),
    ])

    const overflow = plan.rooms.find((room) => room.slotId === OVERFLOW_ROOM_SLOT_ID)
    expect(overflow?.policyCount).toBe(0)
    expect(overflow?.overflowSubmitters).toEqual([])
  })
})

describe('bardo lobby helpers', () => {
  it('keeps unit-space room rectangles valid', () => {
    for (const slot of BARDO_ROOM_SLOTS) {
      const rect = BARDO_ROOM_UNIT_RECTS[slot.id]
      expect(rect.minX).toBeGreaterThanOrEqual(0)
      expect(rect.minY).toBeGreaterThanOrEqual(0)
      expect(rect.maxX).toBeLessThanOrEqual(1)
      expect(rect.maxY).toBeLessThanOrEqual(1)
      expect(rect.maxX).toBeGreaterThan(rect.minX)
      expect(rect.maxY).toBeGreaterThan(rect.minY)
    }
  })

  it('chooses deterministic policy sprites and portals', () => {
    const sprite = spriteForPolicy('policy-123')
    expect(BARDO_POLICY_SPRITES).toContain(sprite)
    expect(spriteForPolicy('policy-123')).toBe(sprite)

    const firstPortal = portalForPolicy('policy-123')
    const secondPortal = portalForPolicy('policy-123')
    expect(firstPortal.id).toBe(secondPortal.id)
  })
})
