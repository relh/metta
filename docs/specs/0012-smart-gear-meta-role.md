# Cogsguard Smart Gear Role

> **Status:** Draft **Author:** Richard Higgins **Created:** 2026-01-22

## Summary

Replace the current random "gear" vibe with a smart gear role that dynamically assigns agents to
miner/scout/aligner/scrambler based on team needs. The system borrows the tribal-village pattern of prioritized,
interruptible options to make each role more structured and explainable, while preserving current scripted behaviors.

## Problem

- The current gear vibe randomly picks a role, which is brittle in early-game and fails to adapt to resource, heart, or
  charger alignment shortages.
- Static role counts in policy URIs cannot respond to changes in game state (missing stations, low hearts, or many enemy
  chargers).
- Role logic is difficult to debug and reason about because it intermixes target selection, movement, and fallback
  behaviors without a consistent priority framework.

## Solution

Introduce a smart gear role that:

- Aggregates shared signals (resource availability, discovered structures, charger alignment).
- Computes a role "need" score and assigns a role to gear agents with hysteresis and cooldowns.
- Runs role behaviors via ordered, interruptible option lists similar to tribal-village's gatherer/builder/fighter
  system.

## Goals

- [ ] Gear agents adaptively select miner/scout/aligner/scrambler based on observable game state.
- [ ] Role switching avoids thrashing (cooldown, stickiness, and pending-action guardrails).
- [ ] Each role behavior is expressed as a priority-ordered option list with clear preemption rules.
- [ ] Rollout tooling verifies that each role performs its core actions (mine+deposit, align, scramble, explore).
- [ ] Existing fixed-role URIs remain supported.

## Non-Goals

- Evolutionary role recombination (future phase).
- Perfect optimal policies or training-level performance.
- Replacing all existing scripted logic in one step (we will wrap existing logic into options).

## Design

### 1) Signals (shared coordinator)

Maintain a lightweight `SmartRoleCoordinator` in the multi-agent policy layer that aggregates:

- Station discovery: `assembler`, `chest`, and gear stations known.
- Charger alignment counts: `cogs`, `clips`, `neutral`, `unknown`.
- Extractor discovery: total count and per-resource availability if known.
- Gear possession counts by role.
- Map coverage proxy: `len(structures)` and/or unique positions seen.
- Hearts + influence availability estimates (via inventory, chest observations, or action history).

### 2) Role scoring

Compute per-role scores each tick:

- **Scout**: high if key stations or extractors are missing; decays as coverage increases.
- **Miner**: high if hearts/influence are low or resource throughput is insufficient.
- **Scrambler**: high if clips-aligned chargers dominate and hearts are available.
- **Aligner**: high if neutral chargers exist and hearts+influence are available.

Role selection uses:

- Quotas (minimum miners always; minimum scout until stations discovered).
- Cooldown (`role_lock_until_step`) to avoid rapid switching.
- Guardrails: do not switch while an agent has a pending action (align/scramble/mine retry).

### 3) Role option lists (behavior priority)

Each role is expressed as a list of interruptible options (tribal-village style):

- **Miner**: heal/recharge -> deposit -> mine -> explore.
- **Scout**: discover stations -> discover extractors -> discover chargers -> explore.
- **Aligner**: get gear -> get hearts/influence -> align nearest non-cogs charger -> explore.
- **Scrambler**: get gear -> get hearts -> scramble nearest clips charger -> explore.

Options are evaluated in priority order; higher-priority options can preempt active ones when interruptible.

### 4) Integration points

- `CogsguardPolicy` owns the shared coordinator and exposes it to agent policies.
- `CogsguardAgentState` adds:
  - `last_role_switch_step`
  - `role_lock_until_step`
  - optional per-agent exploration counters.
- `CogsguardMultiRoleImpl` handles gear-role switching by issuing `change_vibe_*` actions.

### 5) Rollout validation

Extend `packages/cogames-agents/scripts/run_cogsguard_rollout.py` to assert:

- Each role is selected at least once when gear agents are enabled.
- Miners attempt mining and deposit near aligned depots.
- Aligners and scramblers target the correct charger alignment.
- Scouts increase map coverage/structures discovered beyond a threshold.

## Phased Delivery

1. Scaffolding + coordinator (no behavior change).
2. Signal aggregation and logging.
3. Smart gear role selection (gear vibe).
4. Option lists for roles (behavior refactor).
5. Rollout checks + documentation.

## Open Questions

1. Which signals are reliable enough to drive role selection (hearts/influence via inventory vs. proxy counters)?
2. Should role selection be centralized (global quotas) or per-agent independent scoring?
