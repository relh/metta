import { describe, expect, it } from 'vitest'

import type { BardoPolicy, BardoSeason } from './types'
import {
  BARDO_PORTALS,
  buildBuildingPortals,
  buildSeasonBuildingPlan,
  pointOutsideBuildings,
  portalForPolicy,
} from './bardo-lobby-layout'

function makePolicy(policyId: string, seasonIds: string[]): BardoPolicy {
  return {
    policyId,
    policyVersionId: `${policyId}-v1`,
    name: policyId,
    userId: `${policyId}-user`,
    userName: `${policyId}-user`,
    createdAt: '2026-03-05T00:00:00Z',
    activeJobIds: [],
    seasonIds,
  }
}

function makeSeason(seasonId: string, seasonName: string, version: number): BardoSeason {
  return {
    seasonId,
    name: seasonName,
    version,
    compatVersion: '0.17',
    createdAt: '2026-03-05T00:00:00Z',
    stageCount: 2,
    entrantCount: 10,
    activeEntrantCount: 8,
  }
}

describe('buildSeasonBuildingPlan', () => {
  it('maps submitted policies to season buildings and leaves others outside', () => {
    const seasons = [makeSeason('beta-cvc', 'Beta CvC', 3), makeSeason('beta-cg', 'Beta CogsGuard', 2)]
    const policies = [
      makePolicy('slanky-v92', ['beta-cvc']),
      makePolicy('dinky-v24', ['beta-cvc', 'beta-cg']),
      makePolicy('mossy-v4', ['beta-cg']),
      makePolicy('free-agent-v1', []),
    ]

    const plan = buildSeasonBuildingPlan(policies, seasons)

    expect(plan.buildings).toHaveLength(2)
    expect(plan.policySeasonById['slanky-v92']).toBe('beta-cvc')
    expect(plan.policySeasonById['dinky-v24']).toBe('beta-cvc')
    expect(plan.policySeasonById['mossy-v4']).toBe('beta-cg')
    expect(plan.policySeasonById['free-agent-v1']).toBeUndefined()
    expect(plan.buildings.map((building) => [building.seasonId, building.policyCount])).toEqual([
      ['beta-cvc', 2],
      ['beta-cg', 1],
    ])
  })

  it('keeps building rectangles inside normalized bounds', () => {
    const seasons = [
      makeSeason('s1', 'S1', 1),
      makeSeason('s2', 'S2', 1),
      makeSeason('s3', 'S3', 1),
      makeSeason('s4', 'S4', 1),
      makeSeason('s5', 'S5', 1),
    ]
    const plan = buildSeasonBuildingPlan([], seasons)

    for (const building of plan.buildings) {
      expect(building.rect.minX).toBeGreaterThanOrEqual(0)
      expect(building.rect.minY).toBeGreaterThanOrEqual(0)
      expect(building.rect.maxX).toBeLessThanOrEqual(1)
      expect(building.rect.maxY).toBeLessThanOrEqual(1)
      expect(building.rect.maxX).toBeGreaterThan(building.rect.minX)
      expect(building.rect.maxY).toBeGreaterThan(building.rect.minY)
    }
  })
})

describe('bardo season layout helpers', () => {
  it('selects deterministic portals for policies', () => {
    const portal = portalForPolicy('policy-123')
    expect(BARDO_PORTALS).toContainEqual(portal)
    expect(portalForPolicy('policy-123')).toEqual(portal)
  })

  it('attaches a portal to each building', () => {
    const plan = buildSeasonBuildingPlan(
      [],
      [makeSeason('beta-cvc', 'Beta CvC', 3), makeSeason('beta-cogsguard', 'Beta CogsGuard', 2)]
    )
    const portals = buildBuildingPortals(plan.buildings)
    expect(portals).toHaveLength(2)
    expect(portals.map((portal) => portal.seasonId)).toEqual(['beta-cvc', 'beta-cogsguard'])
    for (const portal of portals) {
      expect(portal.x).toBeGreaterThanOrEqual(0)
      expect(portal.x).toBeLessThanOrEqual(1)
      expect(portal.y).toBeGreaterThanOrEqual(0)
      expect(portal.y).toBeLessThanOrEqual(1)
    }
  })

  it('finds outside points that avoid buildings', () => {
    const plan = buildSeasonBuildingPlan([], [makeSeason('beta-cvc', 'Beta CvC', 3)])
    const point = pointOutsideBuildings('policy-outside', plan.buildings, 0)
    const building = plan.buildings[0]
    const insideBuilding =
      point.x >= building.rect.minX &&
      point.x <= building.rect.maxX &&
      point.y >= building.rect.minY &&
      point.y <= building.rect.maxY
    expect(insideBuilding).toBe(false)
  })
})
