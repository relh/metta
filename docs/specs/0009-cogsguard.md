# CogsGuard

**Status:** Approved **Author:** Alex Smith **Created:** 2025-01-13

---

## Summary

CogsGuard is a redesigned game intended to replace the current Cogs vs Clips. It adds explicit area control, role
specialization, and shared resources. It increases the need for agents to coordinate, severely reducing the ability for
agents to succeed by playing "solitaire". It also reduces confusing vibe-based mechanics. Agents are rewarded for
controlling territory over time, making progress visible.

---

## Problem

The original Cogs vs Clips game has several issues impacting its effectiveness as a training environment, and how fun it
is to play and watch:

1. **Sparse, delayed rewards**: Agents only receive reward when depositing hearts. This makes credit assignment
   difficult and slows learning.

2. **Confusing vibe mechanics**: Vibe-based actions for using chests and building hearts is confusing.

3. **Single-player mode**: Our best performing (scripted) agent plays CvC in isolation. CvC rewards coordination, and we
   could update configuration to make it worthwhile, but the cooperative aspects of CvC feel like an afterthought.

4. **Unclear Clips role**: Clips mechanics were designed, but never became a meaningful part of the game.

---

## Solution

CogsGuard restructures the game around territory control and role-based cooperation:

- **Area control as primary objective**: Both Cogs and Clips compete to control territory in the form of junctions.
  Agents receive reward every tick proportional to controlled territory, providing dense feedback. This doesn't remove
  the credit assignment problem.

- **Visible progress**: Territory control creates a natural visualization—you can see who's winning by looking at the
  map.

- **Roles**: Four distinct gear types (Aligner, Scrambler, Miner, Scout) give agents specialized capabilities. Roles are
  mutually dependent: Miners gather efficiently but can't hold territory; Aligners and Scramblers work together to
  capture territory, but need resources.

- **Meaningful adversarial dynamics**: Rather than abstract threats.

---

## Goals

What must be true for this to be considered complete?

- There's an area control system. Teams can gain / lose territory based on the actions of agents. Agents are impacted by
  the ownership of the territory they're in (e.g., if they're in their own team's territory they regenerate energy
  faster).

- Agents can take different roles. Roles have different advantages / abilities. No single role type can achieve success
  alone. Cooperation is effectively required.

- Clips can capture territory to provide PVE.

---

## Nice to have

- Vibe actions are eliminated from core mechanics. Agents can succeed via movement alone.

---

## Non-Goals

What's explicitly out of scope?

- Preserving backward compatibility with CvC training runs or policies.
- Scripted team mates. This is part of a later "batteries included".
- Reward shaping. This is part of a later "batteries included".

---

## Design

### Area Control

- **Capture**: Aligners must have 1 influence and spend 1 heart to capture a neutral junction
- **Disrupt**: Scramblers spend 1 heart to make an enemy junction neutral
- Each junction is either held by a team or neutral

Facilities (Hub, Junction) project AOE effects in a radius (default 10 cells):

- Aligned agents receive: influence / energy / hp fully restored
- Enemy agents receive: -1 hp, influence fully drained

Since enemy AOE drains influence, Aligners cannot capture junctions within enemy territory. Scramblers must first
neutralize nearby enemy junctions to stop the influence drain before Aligners can advance.

**Reward per tick** = (junctions_held / total_junctions) / max_steps

---

### Role System

| Role      | Specialization                                                                                   | Dependency                           |
| --------- | ------------------------------------------------------------------------------------------------ | ------------------------------------ |
| Miner     | +40 cargo, fast resource gathering. AOE that increases the mining capabilities of nearby miners. | Needs Aligners to capture extractors |
| Aligner   | +20 influence capacity, captures territory                                                       | Needs Miners for resources           |
| Scrambler | +200 HP, disrupts enemy control                                                                  | Needs team presence to be effective  |
| Scout     | +100 energy, +400 HP, mobile                                                                     | Needs team to hold what they find    |

Roles are acquired at Gear Stations by spending resources. Agents can switch roles but lose current gear.

---

### Damage

Agents have a limited number of hitpoints. Agents heal ~instantly within their territory. Agents are slowly damaged
outside of their territory, and more quickly inside enemy controlled territory. When an agent's hitpoints reach zero,
the agent's current gear and hearts are destroyed, requiring them to return to base.

---

### Collective Inventory

Teams share a collective inventory that agents deposit to and withdraw from:

- Agents deposit mined resources at aligned junctions and hubs
- Agents withdraw hearts from collective chests
- Hearts are required for capturing and disrupting junctions

This creates interdependence: Miners gather resources for the team, while Aligners and Scramblers consume hearts to
control territory.

---

### Clips

Clips are automated opponents without agents. They automatically expand territory at a configurable rate:

- Neutralize enemy junctions adjacent to Clips territory
- Capture neutral junctions adjacent to Clips territory

This creates PvE pressure that forces Cogs to defend territory while expanding.

---

## Future ideas

### Collective mining

Resources (maybe just one resource) need to be pushed around like blocks in order to be harvested. These come in NxN
blocks which require N cogs to push.
