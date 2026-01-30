"""
Cogas goals -- phase-aware goal factories and cogas-specific goals.

Reuses planky's goal implementations where possible, adding:
- RechargeEnergyGoal: energy-aware detour to junction
- CoordinatedAlignGoal: junction priority queue with team coordination
- CoordinatedScrambleGoal: disruption scoring with team coordination
- PatrolJunctionsGoal: sentinel mode for SUSTAIN phase
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.goals.gear import GetGearGoal
from cogames_agents.policy.scripted_agent.planky.goals.miner import (
    DepositCargoGoal,
)
from cogames_agents.policy.scripted_agent.planky.goals.scout import ExploreGoal, GetScoutGearGoal
from cogames_agents.policy.scripted_agent.planky.goals.survive import SurviveGoal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext

    from .cogas_policy import Coordinator, Phase

# Energy thresholds — threshold=20 traps agents in a recharge death spiral
# (6/10 agents stuck in RechargeEnergy at step 100). Lowering to 5 lets
# agents work until nearly depleted; the move gate in cogas_policy.py
# noops when energy < 3 to allow auto-regen.
ENERGY_RECHARGE_THRESHOLD = 5
ENERGY_PER_MOVE = 3


# ---------------------------------------------------------------------------
# Coordinated heart pickup goal (replaces naive GetHeartsGoal)
# ---------------------------------------------------------------------------


class CoordinatedGetHeartsGoal(Goal):
    """Heart pickup with team coordination.

    Improvements over base GetHeartsGoal:
    1. Reserves a pickup slot via Coordinator to prevent contention
    2. Releases reservation once hearts acquired
    3. Falls back to exploration if no reservation available (another role
       may need hearts more urgently)
    """

    name = "CoordinatedGetHearts"

    def __init__(self, coordinator: "Coordinator", agent_id: int, min_hearts: int = 1) -> None:
        self._coordinator = coordinator
        self._agent_id = agent_id
        self._min_hearts = min_hearts

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        if ctx.state.heart >= self._min_hearts:
            self._coordinator.release_heart(self._agent_id)
            return True
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Try to reserve a heart pickup slot
        if not self._coordinator.reserve_heart(self._agent_id):
            # Slot denied — do something useful while waiting (explore)
            return None  # Fall through to next goal (align/scramble without hearts)

        # Find chest
        result = ctx.map.find_nearest(ctx.state.position, type="chest")
        if result is None:
            # Try hub as fallback
            result = ctx.map.find_nearest(ctx.state.position, type="hub")
        if result is None:
            return ctx.navigator.explore(ctx.state.position, ctx.map)

        chest_pos, _ = result
        if ctx.trace:
            ctx.trace.nav_target = chest_pos

        dist = _manhattan(ctx.state.position, chest_pos)
        if dist <= 1:
            return _move_toward(ctx.state.position, chest_pos)
        return ctx.navigator.get_action(ctx.state.position, chest_pos, ctx.map, reach_adjacent=True)


# ---------------------------------------------------------------------------
# Shared-discovery gear goal (uses Coordinator to share station locations)
# ---------------------------------------------------------------------------


class SharedDiscoveryGearGoal(GetGearGoal):
    """Gear goal that shares discovered station locations with the team.

    When one agent discovers a station, all agents can immediately navigate
    to it instead of independently exploring. Cuts early-game gear acquisition
    time significantly when scouts/miners discover stations first.

    Also uses a shorter retry interval in early game since gear is critical.
    """

    EARLY_RETRY_INTERVAL = 40  # Faster retry in early game vs base 100

    def __init__(self, gear_attr: str, station_type: str, goal_name: str) -> None:
        super().__init__(gear_attr, station_type, goal_name)

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        if getattr(ctx.state, self._gear_attr, False):
            ctx.blackboard[self._bb_attempts_key] = 0
            return True
        # Use shorter retry interval in early game (steps < 200)
        giveup_step = ctx.blackboard.get(self._bb_giveup_step_key, -9999)
        retry_interval = self.EARLY_RETRY_INTERVAL if ctx.step < 200 else self.RETRY_INTERVAL
        if ctx.step - giveup_step < retry_interval:
            return True
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        attempts = ctx.blackboard.get(self._bb_attempts_key, 0) + 1
        ctx.blackboard[self._bb_attempts_key] = attempts

        if attempts > self.MAX_TOTAL_ATTEMPTS:
            ctx.blackboard[self._bb_giveup_step_key] = ctx.step
            ctx.blackboard[self._bb_attempts_key] = 0
            if ctx.trace:
                ctx.trace.activate(self.name, "giving up after max attempts")
            return None

        # Check shared station location from coordinator first
        coordinator = ctx.blackboard.get("_coordinator")
        shared_pos = coordinator.get_shared_station(self._station_type) if coordinator else None

        # Then check own entity map
        result = ctx.map.find_nearest(ctx.state.position, type=self._station_type)

        station_pos = None
        if result is not None:
            station_pos = result[0]
            # Share discovery with team
            if coordinator is not None:
                coordinator.share_station(self._station_type, station_pos)
        elif shared_pos is not None:
            # Use teammate's discovery
            station_pos = shared_pos

        if station_pos is None:
            if ctx.trace:
                ctx.trace.activate(self.name, f"exploring for {self._station_type}")
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias="south",  # Stations typically south of hub
            )

        if ctx.trace:
            ctx.trace.nav_target = station_pos

        dist = _manhattan(ctx.state.position, station_pos)
        if dist <= 1:
            if ctx.trace:
                ctx.trace.activate(self.name, f"bump {attempts}/{self.MAX_TOTAL_ATTEMPTS}")
            return _move_toward(ctx.state.position, station_pos)

        return ctx.navigator.get_action(ctx.state.position, station_pos, ctx.map, reach_adjacent=True)


# ---------------------------------------------------------------------------
# Gear goals (thin wrappers)
# ---------------------------------------------------------------------------


class GetMinerGearGoal(SharedDiscoveryGearGoal):
    def __init__(self) -> None:
        super().__init__(gear_attr="miner_gear", station_type="miner_station", goal_name="GetMinerGear")


class GetAlignerGearGoal(SharedDiscoveryGearGoal):
    def __init__(self) -> None:
        super().__init__(gear_attr="aligner_gear", station_type="aligner_station", goal_name="GetAlignerGear")


class GetScramblerGearGoal(SharedDiscoveryGearGoal):
    def __init__(self) -> None:
        super().__init__(gear_attr="scrambler_gear", station_type="scrambler_station", goal_name="GetScramblerGear")


# ---------------------------------------------------------------------------
# Energy-aware recharge goal
# ---------------------------------------------------------------------------


class RechargeEnergyGoal(Goal):
    """Detour to nearest junction when energy is low.

    Energy-aware pathing: checks path cost against remaining energy
    and forces a junction detour if the agent would stall mid-path.
    """

    name = "RechargeEnergy"

    def __init__(self, threshold: int = ENERGY_RECHARGE_THRESHOLD) -> None:
        self._threshold = threshold

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return ctx.state.energy >= self._threshold

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Find nearest junction (prefer cogs-aligned for AOE bonus)
        junction = _find_nearest_junction(ctx)
        if junction is None:
            return ctx.navigator.explore(ctx.state.position, ctx.map)

        if ctx.trace:
            ctx.trace.nav_target = junction

        dist = _manhattan(ctx.state.position, junction)
        if dist <= 1:
            return _move_toward(ctx.state.position, junction)
        return ctx.navigator.get_action(ctx.state.position, junction, ctx.map, reach_adjacent=True)


def _find_nearest_junction(ctx: PlankyContext) -> Optional[tuple[int, int]]:
    """Find nearest junction, preferring cogs-aligned ones."""
    pos = ctx.state.position
    candidates: list[tuple[int, tuple[int, int]]] = []

    # Prefer cogs-aligned junctions (AOE energy bonus)
    for cpos, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
        candidates.append((_manhattan(pos, cpos), cpos))

    # Then any neutral junction
    for cpos, e in ctx.map.find(type_contains="junction"):
        alignment = e.properties.get("alignment")
        if alignment is None:
            candidates.append((_manhattan(pos, cpos) + 5, cpos))  # Slight penalty for neutral

    # Hub also provides energy
    for apos, _ in ctx.map.find(type="hub"):
        candidates.append((_manhattan(pos, apos) + 3, apos))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Coordinated align goal (team-aware junction targeting)
# ---------------------------------------------------------------------------


class CoordinatedAlignGoal(Goal):
    """Align neutral junctions with team coordination and chain routing.

    Micro-optimizations for junction capture speed:
    1. Optimal targeting: value-weighted scoring (not pure nearest-first)
    2. Pre-positioning: navigate toward next chain target while adjacent
    3. Influence gating: skip alignment attempts without sufficient hearts
    4. Exponential backoff on failed alignment attempts
    5. Chain alignment: greedy TSP route through multiple junctions
    6. Enemy avoidance: deprioritize junctions near enemy scramblers
    """

    name = "CoordinatedAlign"
    MAX_ATTEMPTS_PER_TARGET = 5
    BASE_COOLDOWN_STEPS = 15  # v3: halved from 30 for faster retry
    MAX_COOLDOWN_STEPS = 100  # v3: halved from 200 to reduce dead time
    ENEMY_PROXIMITY_RANGE = 8
    CHAIN_LOOKAHEAD = 5  # v3: increased from 3 for deeper pipeline

    def __init__(self, coordinator: "Coordinator", agent_id: int) -> None:
        self._coordinator = coordinator
        self._agent_id = agent_id

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return False  # Always try to align more

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Influence gating: don't pursue junctions without hearts
        if ctx.state.heart < 1:
            # No heart — skip alignment, let CoordinatedGetHeartsGoal handle it
            return None

        # Build or refresh the alignment chain route
        chain = self._get_or_build_chain(ctx)
        target = chain[0] if chain else None

        if target is None:
            self._coordinator.release_junction(self._agent_id)
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
            )

        # Claim this junction
        self._coordinator.claim_junction(self._agent_id, target)

        if ctx.trace:
            ctx.trace.nav_target = target

        dist = _manhattan(ctx.state.position, target)
        if dist <= 1:
            attempts_key = f"align_attempts_{target}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1
            ctx.blackboard[attempts_key] = attempts

            if attempts > self.MAX_ATTEMPTS_PER_TARGET:
                # Exponential backoff: cooldown doubles each consecutive failure
                fail_count = ctx.blackboard.get(f"align_fail_count_{target}", 0) + 1
                ctx.blackboard[f"align_fail_count_{target}"] = fail_count
                cooldown = min(
                    self.BASE_COOLDOWN_STEPS * (2 ** (fail_count - 1)),
                    self.MAX_COOLDOWN_STEPS,
                )
                ctx.blackboard[f"align_failed_{target}"] = ctx.step
                ctx.blackboard[f"align_cooldown_{target}"] = cooldown
                ctx.blackboard[attempts_key] = 0
                self._coordinator.release_junction(self._agent_id)
                # Pop failed target from chain and advance
                self._pop_chain_head(ctx)
                return ctx.navigator.explore(
                    ctx.state.position,
                    ctx.map,
                    direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                )

            return _move_toward(ctx.state.position, target)

        # Pre-positioning: if we just finished a junction (it's now cogs-aligned),
        # advance the chain and start moving to the next target immediately
        prev_target = ctx.blackboard.get(f"_align_prev_target_{self._agent_id}")
        if prev_target is not None:
            prev_entities = ctx.map.find(type_contains="junction")
            prev_entities.extend(ctx.map.find(type_contains="junction"))
            for ep, e in prev_entities:
                if ep == prev_target and e.properties.get("alignment") == "cogs":
                    # Previous target aligned — clear failure tracking and advance
                    ctx.blackboard.pop(f"align_fail_count_{prev_target}", None)
                    self._pop_chain_head(ctx)
                    chain = ctx.blackboard.get(f"_align_chain_{self._agent_id}", [])
                    if chain:
                        target = chain[0]
                        self._coordinator.claim_junction(self._agent_id, target)
                    break

        ctx.blackboard[f"_align_prev_target_{self._agent_id}"] = target
        ctx.blackboard[f"align_attempts_{target}"] = 0
        return ctx.navigator.get_action(ctx.state.position, target, ctx.map, reach_adjacent=True)

    def _get_or_build_chain(self, ctx: PlankyContext) -> list[tuple[int, int]]:
        """Get cached chain or build a new greedy-TSP route through junctions."""
        chain_key = f"_align_chain_{self._agent_id}"
        chain: list[tuple[int, int]] = ctx.blackboard.get(chain_key, [])

        # Rebuild chain if empty or every 12 steps (v3: faster adaptation)
        rebuild_key = f"_align_chain_step_{self._agent_id}"
        last_build = ctx.blackboard.get(rebuild_key, -999)
        if not chain or ctx.step - last_build >= 12:
            chain = self._build_chain(ctx)
            ctx.blackboard[chain_key] = chain
            ctx.blackboard[rebuild_key] = ctx.step

        # Prune stale entries: skip targets that are now cogs-aligned or recently failed
        while chain:
            head = chain[0]
            if self._is_target_stale(ctx, head):
                chain.pop(0)
                self._coordinator.release_junction(self._agent_id)
            else:
                break

        ctx.blackboard[chain_key] = chain
        return chain

    def _build_chain(self, ctx: PlankyContext) -> list[tuple[int, int]]:
        """Build a greedy nearest-neighbor chain through top-scoring junctions."""
        pos = ctx.state.position
        scored = self._score_all_candidates(ctx)
        if not scored:
            return []

        # Pick top candidates by value (up to CHAIN_LOOKAHEAD)
        scored.sort()
        top = scored[: max(self.CHAIN_LOOKAHEAD * 2, 6)]

        # Greedy nearest-neighbor ordering starting from current position
        chain: list[tuple[int, int]] = []
        remaining = [jpos for _, jpos in top]
        current = pos
        while remaining and len(chain) < self.CHAIN_LOOKAHEAD:
            nearest_idx = min(range(len(remaining)), key=lambda i: _manhattan(current, remaining[i]))
            nxt = remaining.pop(nearest_idx)
            chain.append(nxt)
            current = nxt

        return chain

    def _score_all_candidates(self, ctx: PlankyContext) -> list[tuple[float, tuple[int, int]]]:
        """Score all available junction candidates."""
        pos = ctx.state.position
        claimed = self._coordinator.claimed_junctions()
        candidates: list[tuple[float, tuple[int, int]]] = []

        for jpos, e in ctx.map.find(type_contains="junction"):
            if e.properties.get("alignment") is not None:
                continue
            if self._recently_failed(ctx, jpos):
                continue
            if jpos in claimed and not self._coordinator.claim_junction(self._agent_id, jpos):
                continue
            score = self._score_junction(ctx, pos, jpos)
            candidates.append((score, jpos))

        for cpos, e in ctx.map.find(type_contains="junction"):
            if e.properties.get("alignment") is not None:
                continue
            if self._recently_failed(ctx, cpos):
                continue
            if cpos in claimed and not self._coordinator.claim_junction(self._agent_id, cpos):
                continue
            score = self._score_junction(ctx, pos, cpos)
            candidates.append((score - 5.0, cpos))

        return candidates

    def _recently_failed(self, ctx: PlankyContext, p: tuple[int, int]) -> bool:
        failed_step = ctx.blackboard.get(f"align_failed_{p}", -9999)
        cooldown = ctx.blackboard.get(f"align_cooldown_{p}", self.BASE_COOLDOWN_STEPS)
        return ctx.step - failed_step < cooldown

    def _is_target_stale(self, ctx: PlankyContext, p: tuple[int, int]) -> bool:
        """Check if a chain target is no longer valid."""
        if self._recently_failed(ctx, p):
            return True
        # Check if already aligned
        for jp, e in ctx.map.find(type_contains="junction"):
            if jp == p and e.properties.get("alignment") == "cogs":
                return True
        for cp, e in ctx.map.find(type_contains="junction"):
            if cp == p and e.properties.get("alignment") == "cogs":
                return True
        return False

    def _pop_chain_head(self, ctx: PlankyContext) -> None:
        chain_key = f"_align_chain_{self._agent_id}"
        chain: list[tuple[int, int]] = ctx.blackboard.get(chain_key, [])
        if chain:
            chain.pop(0)
        ctx.blackboard[chain_key] = chain

    def _score_junction(self, ctx: PlankyContext, pos: tuple[int, int], jpos: tuple[int, int]) -> float:
        """Score junction by distance + strategic value (lower is better).

        Key insight: influence comes from AOE of aligned buildings (hub,
        hub, already-aligned junctions). First junction should be
        near AOE sources to ensure the agent has influence when it arrives.
        """
        dist = float(_manhattan(pos, jpos))

        # AOE source proximity bonus — agent needs influence (from hub/
        # aligned junctions AOE) to align. Junctions near AOE sources are easier
        # to align because the agent won't run out of influence walking there.
        aoe_bonus = 0.0
        for hpos, _ in ctx.map.find(type="hub"):
            if _manhattan(jpos, hpos) <= 10:
                aoe_bonus -= 8.0
            break
        for apos, _ in ctx.map.find(type="hub"):
            if _manhattan(jpos, apos) <= 10:
                aoe_bonus -= 5.0
            break

        # Cluster bonus: nearby cogs junctions mean AOE overlap (good)
        cogs_nearby = sum(
            1
            for jp, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"})
            if _manhattan(jpos, jp) <= 10
        )
        cluster_bonus = -3.0 * cogs_nearby

        # Contest penalty: nearby enemy-aligned junctions
        clips_penalty = 0.0
        for jp, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"}):
            if _manhattan(jpos, jp) <= 10:
                clips_penalty += 3.0

        # Enemy scrambler avoidance: penalize junctions near enemy agents
        enemy_nearby = 0
        for ep, e in ctx.map.find(type_contains="agent"):
            if e.properties.get("team") == "clips" and _manhattan(jpos, ep) <= self.ENEMY_PROXIMITY_RANGE:
                enemy_nearby += 1
        scramble_risk = 8.0 * enemy_nearby

        return dist + aoe_bonus + cluster_bonus + clips_penalty + scramble_risk


# ---------------------------------------------------------------------------
# Coordinated scramble goal (team-aware enemy targeting)
# ---------------------------------------------------------------------------


class CoordinatedScrambleGoal(Goal):
    """Scramble enemy junctions with team coordination.

    Agents claim different enemy junctions. Targets scored by disruption value.
    """

    name = "CoordinatedScramble"
    MAX_ATTEMPTS_PER_TARGET = 5
    COOLDOWN_STEPS = 30  # v3: reduced from 50 for faster retry
    AOE_RANGE = 10

    def __init__(self, coordinator: "Coordinator", agent_id: int) -> None:
        self._coordinator = coordinator
        self._agent_id = agent_id

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Heart gating: don't pursue targets without hearts (same as aligners)
        if ctx.state.heart < 1:
            return None

        target = self._find_best_target(ctx)
        if target is None:
            self._coordinator.release_scramble(self._agent_id)
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
            )

        self._coordinator.claim_scramble(self._agent_id, target)

        if ctx.trace:
            ctx.trace.nav_target = target

        dist = _manhattan(ctx.state.position, target)
        if dist <= 1:
            attempts_key = f"scramble_attempts_{target}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1
            ctx.blackboard[attempts_key] = attempts

            if attempts > self.MAX_ATTEMPTS_PER_TARGET:
                ctx.blackboard[f"scramble_failed_{target}"] = ctx.step
                ctx.blackboard[attempts_key] = 0
                self._coordinator.release_scramble(self._agent_id)
                return ctx.navigator.explore(
                    ctx.state.position,
                    ctx.map,
                    direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                )

            return _move_toward(ctx.state.position, target)

        ctx.blackboard[f"scramble_attempts_{target}"] = 0
        return ctx.navigator.get_action(ctx.state.position, target, ctx.map, reach_adjacent=True)

    def _find_best_target(self, ctx: PlankyContext) -> Optional[tuple[int, int]]:
        """Find best enemy junction to scramble."""
        pos = ctx.state.position
        claimed = self._coordinator.claimed_scrambles()

        def recently_failed(p: tuple[int, int]) -> bool:
            failed_step = ctx.blackboard.get(f"scramble_failed_{p}", -9999)
            return ctx.step - failed_step < self.COOLDOWN_STEPS

        # Enemy junctions and junctions
        candidates: list[tuple[float, tuple[int, int]]] = []

        for jpos, _e in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"}):
            if recently_failed(jpos):
                continue
            if jpos in claimed and not self._coordinator.claim_scramble(self._agent_id, jpos):
                continue
            score = self._score_target(ctx, pos, jpos)
            candidates.append((score, jpos))

        for cpos, _e in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"}):
            if recently_failed(cpos):
                continue
            if cpos in claimed and not self._coordinator.claim_scramble(self._agent_id, cpos):
                continue
            score = self._score_target(ctx, pos, cpos)
            candidates.append((score, cpos))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    def _score_target(self, ctx: PlankyContext, pos: tuple[int, int], epos: tuple[int, int]) -> float:
        """Score enemy junction for disruption (lower = better target).

        Adaptive targeting: in late game, heavily weight clustered high-value
        enemy junctions to maximize disruption per scramble action.
        """
        dist = float(_manhattan(pos, epos))

        # Determine phase aggression multiplier
        coordinator = ctx.blackboard.get("_coordinator")
        is_late_losing = False
        if coordinator is not None:
            is_late_losing = ctx.step > 600 and coordinator.is_losing

        # Cluster bonus: enemy cluster is higher-value target
        clips_nearby = sum(
            1
            for jp, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"})
            if _manhattan(epos, jp) <= self.AOE_RANGE and jp != epos
        )
        # Double cluster weight in late game when losing
        cluster_weight = -8.0 if is_late_losing else -4.0
        cluster_bonus = cluster_weight * clips_nearby

        # Also count enemy junctions as high-value (deny energy)
        clips_junctions_nearby = sum(
            1
            for cp, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "clips"})
            if _manhattan(epos, cp) <= self.AOE_RANGE and cp != epos
        )
        junction_bonus = -6.0 * clips_junctions_nearby

        # Bonus for targets near our neutral junctions (opens them for aligners)
        neutral_nearby = sum(
            1
            for jp, e in ctx.map.find(type_contains="junction")
            if e.properties.get("alignment") is None and _manhattan(epos, jp) <= self.AOE_RANGE
        )
        opener_bonus = -2.0 * neutral_nearby

        # Late-game losing: reduce distance penalty to encourage long-range attacks
        if is_late_losing:
            dist *= 0.5

        return dist + cluster_bonus + junction_bonus + opener_bonus


# ---------------------------------------------------------------------------
# Patrol goal for sentinel mode (SUSTAIN phase)
# ---------------------------------------------------------------------------


class PatrolJunctionsGoal(Goal):
    """Patrol cogs-aligned junctions and re-align scrambled ones.

    Used in SUSTAIN phase. Cycles through known cogs junctions,
    checking for and re-aligning any that lost alignment.
    """

    name = "PatrolJunctions"

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return False  # Patrol indefinitely

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Check for scrambled junctions that were previously cogs-aligned
        # (tracked via blackboard)
        target = self._find_patrol_target(ctx)
        if target is None:
            # No junctions to patrol — explore
            return ctx.navigator.explore(ctx.state.position, ctx.map)

        if ctx.trace:
            ctx.trace.nav_target = target

        dist = _manhattan(ctx.state.position, target)
        if dist <= 1:
            return _move_toward(ctx.state.position, target)
        return ctx.navigator.get_action(ctx.state.position, target, ctx.map, reach_adjacent=True)

    def _find_patrol_target(self, ctx: PlankyContext) -> Optional[tuple[int, int]]:
        """Find next junction to patrol."""
        pos = ctx.state.position

        # Priority 1: neutral junctions (may have been scrambled)
        neutral: list[tuple[int, tuple[int, int]]] = []
        for jpos, e in ctx.map.find(type_contains="junction"):
            if e.properties.get("alignment") is None:
                neutral.append((_manhattan(pos, jpos), jpos))
        for cpos, e in ctx.map.find(type_contains="junction"):
            if e.properties.get("alignment") is None:
                neutral.append((_manhattan(pos, cpos), cpos))

        if neutral:
            neutral.sort()
            return neutral[0][1]

        # Priority 2: cycle through cogs junctions
        cogs: list[tuple[int, tuple[int, int]]] = []
        for jpos, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
            cogs.append((_manhattan(pos, jpos), jpos))
        for cpos, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
            cogs.append((_manhattan(pos, cpos), cpos))

        if not cogs:
            return None

        # Visit the farthest cogs junction (spread patrol coverage)
        patrol_idx = ctx.blackboard.get("_patrol_idx", 0)
        cogs.sort(key=lambda x: x[0])
        # Rotate through junctions
        target_idx = patrol_idx % len(cogs)
        ctx.blackboard["_patrol_idx"] = patrol_idx + 1
        return cogs[target_idx][1]


# ---------------------------------------------------------------------------
# Goal list factories per role and phase
# ---------------------------------------------------------------------------


class ResourceManagedMineGoal(Goal):
    """Mining goal that uses ResourceManager for smarter target selection.

    Replaces the naive PickResource + MineResource chain with coordinated
    mining that balances team resource needs and prevents extractor contention.
    """

    name = "ResourceManagedMine"
    MAX_ATTEMPTS_PER_EXTRACTOR = 5

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return False  # Always mine

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Get shared resource manager from coordinator
        coordinator = ctx.blackboard.get("_coordinator")
        if coordinator is None:
            return None
        resource_mgr = coordinator._resource_manager

        # Update manager with current observations
        resource_mgr.update_from_context(ctx)

        # Check if we should deposit first
        if resource_mgr.should_deposit(ctx):
            depot_pos = resource_mgr.find_best_depot(ctx)
            if depot_pos is not None:
                if ctx.trace:
                    ctx.trace.nav_target = depot_pos
                dist = _manhattan(ctx.state.position, depot_pos)
                if dist <= 1:
                    return _move_toward(ctx.state.position, depot_pos)
                return ctx.navigator.get_action(ctx.state.position, depot_pos, ctx.map, reach_adjacent=True)

        # Select best mining target using team-aware scoring
        target_pos = resource_mgr.select_mining_target(ctx)
        if target_pos is None:
            # Fallback to exploration
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
            )

        if ctx.trace:
            ctx.trace.nav_target = target_pos

        # Track cargo to detect successful mining
        prev_cargo = ctx.blackboard.get("prev_cargo", 0)
        current_cargo = ctx.state.cargo_total
        ctx.blackboard["prev_cargo"] = current_cargo

        dist = _manhattan(ctx.state.position, target_pos)
        if dist <= 1:
            attempts_key = f"mine_attempts_{target_pos}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1

            if current_cargo > prev_cargo:
                ctx.blackboard[attempts_key] = 0
            else:
                ctx.blackboard[attempts_key] = attempts
                if attempts > self.MAX_ATTEMPTS_PER_EXTRACTOR:
                    resource_mgr.mark_extractor_failed(ctx.agent_id, target_pos, ctx.step)
                    ctx.blackboard[attempts_key] = 0
                    return ctx.navigator.explore(
                        ctx.state.position,
                        ctx.map,
                        direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                    )

            return _move_toward(ctx.state.position, target_pos)

        ctx.blackboard[f"mine_attempts_{target_pos}"] = 0
        return ctx.navigator.get_action(ctx.state.position, target_pos, ctx.map, reach_adjacent=True)


def make_miner_goals(phase: "Phase") -> list[Goal]:
    """Miner goals vary by phase.

    EARLY: standard mining loop (gear -> mine -> deposit)
    MID:   same but with more aggressive recharge threshold
    LATE:  reduced mining, focus shifts to support

    Uses ResourceManagedMineGoal for coordinated team-aware mining
    that balances resource types and prevents extractor contention.
    """
    from .cogas_policy import Phase

    goals: list[Goal] = [
        SurviveGoal(hp_threshold=15),
        RechargeEnergyGoal(threshold=ENERGY_RECHARGE_THRESHOLD),
        GetMinerGearGoal(),
        DepositCargoGoal(),
        ResourceManagedMineGoal(),
    ]
    if phase == Phase.EARLY:
        # Early: also explore to reveal map for team
        goals.append(ExploreGoal())
    return goals


def make_scout_goals(phase: "Phase") -> list[Goal]:
    """Scout goals vary by phase.

    EARLY: aggressive exploration to reveal map
    MID:   continue exploration, reveal enemy positions
    LATE:  exploration with focus on finding unaligned junctions
    """
    goals: list[Goal] = [
        SurviveGoal(hp_threshold=50),
        RechargeEnergyGoal(threshold=ENERGY_RECHARGE_THRESHOLD),
        GetScoutGearGoal(),
        ExploreGoal(),
    ]
    return goals


def make_aligner_goals(phase: "Phase", coordinator: "Coordinator", agent_id: int, winning: bool = False) -> list[Goal]:
    """Aligner goals vary by phase.

    EARLY: get gear + hearts, start aligning nearby junctions
    MID:   aggressive coordinated junction capture
    LATE winning: patrol and defend aligned junctions
    LATE losing:  keep aggressively aligning
    """
    from .cogas_policy import Phase

    goals: list[Goal] = [
        SurviveGoal(hp_threshold=30),  # v3: lowered from 50 so aligners stay active longer
        RechargeEnergyGoal(threshold=ENERGY_RECHARGE_THRESHOLD),
        GetAlignerGearGoal(),
        CoordinatedGetHeartsGoal(coordinator, agent_id),
    ]

    if phase == Phase.LATE and winning:
        # Winning late game: defensive patrol of aligned junctions
        goals.append(PatrolJunctionsGoal())
    else:
        # EARLY, MID, or losing LATE: aggressively align
        goals.append(CoordinatedAlignGoal(coordinator, agent_id))

    return goals


def make_scrambler_goals(phase: "Phase", coordinator: "Coordinator", agent_id: int, losing: bool = False) -> list[Goal]:
    """Scrambler goals vary by phase.

    EARLY: get gear + hearts, opportunistic scrambles
    MID:   heavy coordinated scrambling
    LATE losing: all-out scramble attack on high-value enemy junctions
    LATE winning: selective scrambling of enemy clusters
    """
    goals: list[Goal] = [
        SurviveGoal(hp_threshold=30 if not losing else 15),  # More reckless when losing
        RechargeEnergyGoal(threshold=ENERGY_RECHARGE_THRESHOLD if not losing else 10),
        GetScramblerGearGoal(),
        CoordinatedGetHeartsGoal(coordinator, agent_id),
        CoordinatedScrambleGoal(coordinator, agent_id),
    ]
    return goals


def make_defensive_goals(
    phase: "Phase",
    coordinator: "Coordinator",
    agent_id: int,
) -> list[Goal]:
    """Defensive goals: survive, recharge, patrol aligned junctions to re-align scrambled ones."""
    goals: list[Goal] = [
        SurviveGoal(hp_threshold=60),
        RechargeEnergyGoal(threshold=ENERGY_RECHARGE_THRESHOLD),
        GetAlignerGearGoal(),
        CoordinatedGetHeartsGoal(coordinator, agent_id),
        PatrolJunctionsGoal(),
    ]
    return goals


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _move_toward(current: tuple[int, int], target: tuple[int, int]) -> Action:
    dr = target[0] - current[0]
    dc = target[1] - current[1]
    if abs(dr) >= abs(dc):
        if dr > 0:
            return Action(name="move_south")
        elif dr < 0:
            return Action(name="move_north")
    if dc > 0:
        return Action(name="move_east")
    elif dc < 0:
        return Action(name="move_west")
    return Action(name="move_north")
