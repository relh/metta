# CogsGuard Strategy Overview

**CogsGuard** is a territory control game where your team (Cogs) competes against an AI opponent (Clips) to control
**junctions** on the map.

## Game Mechanics

### Junction States

Junctions (junctions on the map) have three states:

- **Neutral** (unaligned)
- **Cogs-aligned** (your team controls)
- **Clips-aligned** (enemy controls)

### Junction AOE Effects (10 tile radius)

- Friendly junctions give you **+10 influence, +100 energy, +100 HP** per tick
- Enemy junctions **attack you**: -1 HP, -100 influence per tick

### Clips Behavior (AI opponent)

- At timestep 10, Clips claims one initial junction
- Every ~100 steps, Clips **scrambles** a nearby Cogs junction to neutral
- Every ~100 steps, Clips **aligns** a nearby neutral junction to Clips
- Clips expands outward from their controlled junctions (25 tile radius)

### Reward

Points based on how many junctions Cogs controls over time (scaled: 100 / max_steps per junction held).

## Role System

| Role             | Gear Cost       | Purpose                                                      |
| ---------------- | --------------- | ------------------------------------------------------------ |
| **Miner** ⛏️     | C1 O1 **G3** S1 | Extract resources faster (+40 cargo), deposits to collective |
| **Scout** 🔭     | C1 O1 G1 **S3** | Explore map (+100 energy, +400 HP)                           |
| **Aligner** 🔗   | **C3** O1 G1 S1 | Convert neutral junctions to Cogs (+20 influence)            |
| **Scrambler** 🌀 | C1 **O3** G1 S1 | Convert Clips junctions to neutral (+200 HP)                 |

### Critical Costs

- **Heart** (required for align/scramble): 1 of each element from collective
- **Align**: 1 heart + 1 influence + aligner gear
- **Scramble**: 1 heart + scrambler gear

## The Strategic Loop

```
Resources (extractors) → Collective → Hearts (chest) → Junction control
```

1. **Miners** gather resources from extractors → deposit at Hub/Junction → funds collective
2. **Collective** resources can buy hearts at chest (1 of each element)
3. **Aligners** spend hearts to convert neutral junctions
4. **Scramblers** spend hearts to break enemy junctions

## Key Strategic Considerations

### Economy Priority

You need a steady stream of hearts. Without miners depositing resources, aligners/scramblers can't act.

### Territory Expansion

Clips expands from existing junctions. The optimal counter is:

- **Scramble** enemy junctions to break their expansion radius
- **Align** neutral junctions **outside** enemy AOE (the aligner goal already checks this)

### Junction Targeting

Current scrambler logic prioritizes junctions that block the most neutral junctions from being captured.

### Role Balance

Default is `stem=10` which lets agents dynamically choose roles based on game state. Only use explicit role counts when
testing specific role behaviors.

## Improvement Areas

### Early Game Economy

- Bootstrap resource gathering before combat roles become effective
- Consider dynamic role allocation based on collective resources

### Smarter Role Transitions (Stem Agents)

- Stem agents can auto-select roles based on game state
- Could be improved to respond to economy/territory balance

### Better Junction Targeting Heuristics

- Prioritize junctions that would give strategic map control
- Consider path distances and clustering

### Coordination Between Roles

- Scramblers and aligners could coordinate to chain-capture junctions
- Miners could prioritize resources needed for hearts vs gear
