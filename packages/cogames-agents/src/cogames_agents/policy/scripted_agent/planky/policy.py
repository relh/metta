"""
Planky Policy — goal-tree scripted agent.

PlankyBrain coordinates per-agent state and goal evaluation.
PlankyPolicy is the multi-agent wrapper with URI-based role distribution.
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from mettagrid.mettagrid_c import dtype_actions
from mettagrid.policy.policy import MultiAgentPolicy, StatefulAgentPolicy, StatefulPolicyImpl
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Action, ObservationToken
from mettagrid.simulator.interface import AgentObservation

from .context import PlankyContext, StateSnapshot
from .entity_map import EntityMap
from .goal import Goal, evaluate_goals
from .goals.aligner import AlignJunctionGoal, GetAlignerGearGoal
from .goals.miner import DepositCargoGoal, ExploreHubGoal, GetMinerGearGoal, MineResourceGoal, PickResourceGoal
from .goals.scout import ExploreGoal, GetScoutGearGoal
from .goals.scrambler import GetScramblerGearGoal, ScrambleJunctionGoal
from .goals.shared import EmergencyMineGoal, FallbackMineGoal, GetHeartsGoal
from .goals.stem import SelectRoleGoal
from .goals.survive import SurviveGoal
from .navigator import Navigator
from .obs_parser import ObsParser
from .trace import TraceLog


@dataclass
class TimelineEvent:
    """A single event in an agent's timeline."""

    step: int
    event_type: str  # "role_change", "got_gear", "lost_gear", "deposit", "aligned", "scrambled"
    description: str


@dataclass
class AgentTickStats:
    """Per-agent tick statistics tracked throughout the episode."""

    # Per-role tick counts
    ticks_by_role: dict[str, int] = field(default_factory=dict)

    # Per-role: ticks with gear equipped
    ticks_with_gear_by_role: dict[str, int] = field(default_factory=dict)

    # Per-role: ticks spent moving (action was move_*)
    ticks_moving_by_role: dict[str, int] = field(default_factory=dict)

    # Per-role: ticks spent still (position didn't change)
    ticks_still_by_role: dict[str, int] = field(default_factory=dict)

    # Miner-specific: mining actions (move_*) with vs without gear
    mining_actions_with_gear: int = 0
    mining_actions_without_gear: int = 0

    # Timeline of key events
    timeline: list[TimelineEvent] = field(default_factory=list)

    # Initial role (set once at creation)
    initial_role: str = ""

    # Role change count
    role_changes: int = 0

    # Cumulative deposit tracking - aggregated into single summary at end
    _total_deposits: dict[str, int] = field(default_factory=dict)

    # Junction action tracking - aggregated into summary events at end
    _junctions_aligned: int = 0
    _junctions_scrambled: int = 0

    def record_tick(self, role: str, has_gear: bool, action_name: str, moved: bool) -> None:
        """Record stats for a single tick."""
        self.ticks_by_role[role] = self.ticks_by_role.get(role, 0) + 1
        if has_gear:
            self.ticks_with_gear_by_role[role] = self.ticks_with_gear_by_role.get(role, 0) + 1
        if action_name.startswith("move_"):
            self.ticks_moving_by_role[role] = self.ticks_moving_by_role.get(role, 0) + 1
        if not moved:
            self.ticks_still_by_role[role] = self.ticks_still_by_role.get(role, 0) + 1

        # Track mining actions with/without gear (move actions while in miner role)
        if role == "miner" and action_name.startswith("move_"):
            if has_gear:
                self.mining_actions_with_gear += 1
            else:
                self.mining_actions_without_gear += 1

    def add_event(self, step: int, event_type: str, description: str) -> None:
        """Add a timeline event."""
        self.timeline.append(TimelineEvent(step=step, event_type=event_type, description=description))

    def record_deposit(self, step: int, resource: str, amount: int) -> None:
        """Record a deposit - all deposits aggregated into single summary at end."""
        self._total_deposits[resource] = self._total_deposits.get(resource, 0) + amount

    def record_junction_action(self, role: str) -> None:
        """Record a junction align/scramble action based on current role."""
        if role == "aligner":
            self._junctions_aligned += 1
        elif role == "scrambler":
            self._junctions_scrambled += 1

    def finalize(self) -> None:
        """Finalize stats at end of episode (add summaries, sort timeline)."""
        # Add junction action summaries
        if self._junctions_aligned > 0:
            self.add_event(999998, "aligned", f"aligned {self._junctions_aligned} junctions")
        if self._junctions_scrambled > 0:
            self.add_event(999998, "scrambled", f"scrambled {self._junctions_scrambled} junctions")
        # Add single summary line for all deposits
        if self._total_deposits:
            parts = [f"{amt} {res[0].upper()}" for res, amt in sorted(self._total_deposits.items()) if amt > 0]
            if parts:
                desc = "total deposited: " + ", ".join(parts)
                self.add_event(999999, "deposit_summary", desc)  # High step to sort last
        # Sort timeline by step
        self.timeline.sort(key=lambda e: e.step)


# Global registry of policies for atexit stats dumping (strong references to prevent GC)
_policy_registry: set["PlankyPolicy"] = set()


def _atexit_dump_all_stats() -> None:
    """Dump unified stats for all policies on program exit."""
    policies = list(_policy_registry)
    if not policies:
        return

    # Check if any policy has stats or trace enabled (for stats output)
    show_stats = any(getattr(p, "_stats_enabled", False) or getattr(p, "_trace_enabled", False) for p in policies)
    # Check if any policy has trace or bio enabled (for agent timelines)
    show_timelines = any(getattr(p, "_trace_enabled", False) or getattr(p, "_bio_enabled", False) for p in policies)

    # Mark all policies as dumped to prevent individual dumps
    for policy in policies:
        policy._stats_dumped = True

    # Skip stats output if not enabled
    if not show_stats:
        return

    # Collect stats from all policies into one unified view
    all_agent_stats: list[tuple[int, str, int | None, AgentTickStats]] = []
    for policy in policies:
        for agent_id, agent_policy in policy._agent_policies.items():
            if agent_policy._state is None:
                continue
            state = agent_policy._state
            if not state.stats.ticks_by_role:
                continue
            # Finalize stats (flush pending deposits)
            state.stats.finalize()
            all_agent_stats.append(
                (
                    agent_id,
                    state.role,
                    state.my_collective_id,
                    state.stats,
                )
            )

    if not all_agent_stats:
        return

    # Print unified header
    print("\n" + "=" * 100)
    print("PLANKY EPISODE STATS")
    print("=" * 100)

    # Per-agent table
    print("\n--- Per Agent ---")
    print(
        f"{'Agent':>6} {'Role':>10} {'Team':>6} {'Ticks':>8} {'w/Gear':>8} "
        f"{'Moving':>8} {'Still':>8} {'Aligned':>8} {'Scrambled':>9}"
    )
    print("-" * 90)
    for agent_id, role, collective_id, stats in sorted(all_agent_stats, key=lambda x: (x[0], x[1], x[2] or 0)):
        total_ticks = sum(stats.ticks_by_role.values())
        total_gear = sum(stats.ticks_with_gear_by_role.values())
        total_moving = sum(stats.ticks_moving_by_role.values())
        total_still = sum(stats.ticks_still_by_role.values())
        team = "cogs" if collective_id == 1 else "clips" if collective_id == 0 else "?"
        aligned = stats._junctions_aligned
        scrambled = stats._junctions_scrambled
        print(
            f"{agent_id:>6} {role:>10} {team:>6} {total_ticks:>8} {total_gear:>8} "
            f"{total_moving:>8} {total_still:>8} {aligned:>8} {scrambled:>9}"
        )

    # Per-role aggregate
    print("\n--- Per Role ---")
    hdr = f"{'Role':>12} {'Ticks':>8} {'w/Gear':>8} {'Moving':>8} {'Still':>8}"
    print(f"{hdr} {'%Gear':>8} {'%Moving':>8} {'%Still':>8}")
    print("-" * 90)
    role_totals: dict[str, dict[str, int]] = {}
    for _, _, _, stats in all_agent_stats:
        for role in stats.ticks_by_role:
            if role not in role_totals:
                role_totals[role] = {"ticks": 0, "gear": 0, "moving": 0, "still": 0}
            role_totals[role]["ticks"] += stats.ticks_by_role.get(role, 0)
            role_totals[role]["gear"] += stats.ticks_with_gear_by_role.get(role, 0)
            role_totals[role]["moving"] += stats.ticks_moving_by_role.get(role, 0)
            role_totals[role]["still"] += stats.ticks_still_by_role.get(role, 0)

    for role in sorted(role_totals.keys()):
        t = role_totals[role]
        ticks = t["ticks"]
        pct_gear = (t["gear"] / ticks * 100) if ticks > 0 else 0
        pct_moving = (t["moving"] / ticks * 100) if ticks > 0 else 0
        pct_still = (t["still"] / ticks * 100) if ticks > 0 else 0
        print(
            f"{role:>12} {ticks:>8} {t['gear']:>8} {t['moving']:>8} {t['still']:>8} "
            f"{pct_gear:>7.1f}% {pct_moving:>7.1f}% {pct_still:>7.1f}%"
        )

    # Per-team aggregate
    print("\n--- Per Team ---")
    hdr = f"{'Team':>12} {'Ticks':>8} {'w/Gear':>8} {'Moving':>8} {'Still':>8}"
    print(f"{hdr} {'%Gear':>8} {'%Moving':>8} {'%Still':>8}")
    print("-" * 90)
    zero_stats = {"ticks": 0, "gear": 0, "moving": 0, "still": 0}
    team_totals: dict[str, dict[str, int]] = {
        "c": dict(zero_stats),
        "clips": dict(zero_stats),
    }
    for _, _, collective_id, stats in all_agent_stats:
        team = "cogs" if collective_id == 1 else "clips" if collective_id == 0 else None
        if team is None:
            continue
        team_totals[team]["ticks"] += sum(stats.ticks_by_role.values())
        team_totals[team]["gear"] += sum(stats.ticks_with_gear_by_role.values())
        team_totals[team]["moving"] += sum(stats.ticks_moving_by_role.values())
        team_totals[team]["still"] += sum(stats.ticks_still_by_role.values())

    for team in ["c", "clips"]:
        t = team_totals[team]
        ticks = t["ticks"]
        if ticks == 0:
            continue
        pct_gear = (t["gear"] / ticks * 100) if ticks > 0 else 0
        pct_moving = (t["moving"] / ticks * 100) if ticks > 0 else 0
        pct_still = (t["still"] / ticks * 100) if ticks > 0 else 0
        print(
            f"{team:>12} {ticks:>8} {t['gear']:>8} {t['moving']:>8} {t['still']:>8} "
            f"{pct_gear:>7.1f}% {pct_moving:>7.1f}% {pct_still:>7.1f}%"
        )

    # Miner-specific: mining actions with/without gear
    total_mining_with_gear = sum(s.mining_actions_with_gear for _, _, _, s in all_agent_stats)
    total_mining_without_gear = sum(s.mining_actions_without_gear for _, _, _, s in all_agent_stats)
    total_mining = total_mining_with_gear + total_mining_without_gear
    if total_mining > 0:
        print("\n--- Miner Gear Efficiency ---")
        pct_with = (total_mining_with_gear / total_mining * 100) if total_mining > 0 else 0
        print(f"Mining actions with gear:    {total_mining_with_gear:>6} ({pct_with:>5.1f}%)")
        print(f"Mining actions without gear: {total_mining_without_gear:>6} ({100 - pct_with:>5.1f}%)")

    # Agent timelines (only if trace or bio enabled)
    if show_timelines:
        print("\n--- Agent Timelines ---")
        for agent_id, role, collective_id, stats in sorted(all_agent_stats, key=lambda x: (x[0], x[1], x[2] or 0)):
            team = "cogs" if collective_id == 1 else "clips" if collective_id == 0 else "?"
            initial = stats.initial_role or "?"
            changes = stats.role_changes
            print(f"\nAgent {agent_id} ({team}, initial role: {initial}, role changes: {changes}, final role: {role}):")
            if not stats.timeline:
                print("  (no events)")
            for event in stats.timeline:
                # Summary events (high step numbers) show as "end"
                if event.step >= 999000:
                    print(f"    end: {event.description}")
                else:
                    print(f"  {event.step:>5}: {event.description}")

    print("=" * 100 + "\n")


atexit.register(_atexit_dump_all_stats)


# Role vibes that map to roles
VIBE_TO_ROLE = {"miner", "scout", "aligner", "scrambler"}

# Default spawn position (center of 200x200 grid)
SPAWN_POS = (100, 100)


def _make_goal_list(role: str) -> list[Goal]:
    """Create goal list for a role."""
    if role == "miner":
        return [
            SurviveGoal(hp_threshold=15),
            EmergencyMineGoal(),
            GetMinerGearGoal(),
            ExploreHubGoal(),
            PickResourceGoal(),
            DepositCargoGoal(),
            MineResourceGoal(),
        ]
    elif role == "scout":
        return [
            SurviveGoal(hp_threshold=50),
            EmergencyMineGoal(),
            GetScoutGearGoal(),
            ExploreGoal(),
        ]
    elif role == "aligner":
        # Aligners NEED gear + heart to align junctions.
        # Hearts require gear first — don't waste resources on hearts without gear.
        # EmergencyMine: all cogs mine when any resource < 10 (unless they have hearts).
        # FallbackMine at end: mine resources when can't get gear/hearts.
        return [
            SurviveGoal(hp_threshold=50),
            EmergencyMineGoal(),
            GetAlignerGearGoal(),
            GetHeartsGoal(),
            AlignJunctionGoal(),
            FallbackMineGoal(),
        ]
    elif role == "scrambler":
        # Scramblers NEED gear + heart to scramble junctions.
        # EmergencyMine: all cogs mine when any resource < 10 (unless they have hearts).
        # FallbackMine at end: mine resources when can't get gear/hearts.
        return [
            SurviveGoal(hp_threshold=30),
            EmergencyMineGoal(),
            GetScramblerGearGoal(),
            GetHeartsGoal(),
            ScrambleJunctionGoal(),
            FallbackMineGoal(),
        ]
    elif role == "stem":
        return [
            SurviveGoal(hp_threshold=20),
            EmergencyMineGoal(),
            SelectRoleGoal(),
        ]
    else:
        # Default/inactive
        return []


class PlankyAgentState:
    """Persistent state for a Planky agent across ticks."""

    def __init__(self, agent_id: int, role: str, goals: list[Goal]) -> None:
        self.agent_id = agent_id
        self.role = role
        self.goals = goals
        self.entity_map = EntityMap()
        self.navigator = Navigator()
        self.blackboard: dict[str, Any] = {}
        self.step = 0
        self.my_collective_id: int | None = None
        self.stats = AgentTickStats()


class PlankyBrain(StatefulPolicyImpl[PlankyAgentState]):
    """Per-agent coordinator that owns state and evaluates the goal tree."""

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        agent_id: int,
        role: str,
        trace_enabled: bool = False,
        trace_level: int = 1,
        trace_agent: int = -1,
        convert_to_scrambler_at_step: int | None = None,
    ) -> None:
        self._agent_id = agent_id
        self._policy_env_info = policy_env_info
        self._role = role
        self._obs_parser = ObsParser(policy_env_info)
        self._action_names = policy_env_info.action_names

        # Tracing
        self._trace_enabled = trace_enabled
        self._trace_level = trace_level
        self._trace_agent = trace_agent  # -1 = trace all

        # Role conversion: if set, this aligner becomes a scrambler at the specified step
        self._convert_to_scrambler_at_step = convert_to_scrambler_at_step

    def initial_agent_state(self) -> PlankyAgentState:
        goals = _make_goal_list(self._role)
        state = PlankyAgentState(
            agent_id=self._agent_id,
            role=self._role,
            goals=goals,
        )
        # Record initial role
        state.stats.initial_role = self._role
        return state

    def step_with_state(self, obs: AgentObservation, agent_state: PlankyAgentState) -> tuple[Action, PlankyAgentState]:
        agent_state.step += 1

        # Parse observation
        state, visible_entities = self._obs_parser.parse(obs, agent_state.step, SPAWN_POS)

        # Update entity map
        agent_state.entity_map.update_from_observation(
            agent_pos=state.position,
            obs_half_height=self._obs_parser.obs_half_height,
            obs_half_width=self._obs_parser.obs_half_width,
            visible_entities=visible_entities,
            step=agent_state.step,
        )

        # Detect own collective_id from nearest hub (once)
        if agent_state.my_collective_id is None:
            hub = agent_state.entity_map.find_nearest(state.position, type_contains="hub")
            if hub is not None:
                _, hub_entity = hub
                cid = hub_entity.properties.get("collective_id")
                if cid is not None:
                    agent_state.my_collective_id = cid

        # Detect useful actions by comparing state changes
        # Useful = mined resources, deposited to collective, aligned/scrambled junction
        self._detect_useful_action(state, agent_state)

        # Detect failed moves: if last action was a move but position didn't change
        last_pos = agent_state.blackboard.get("_last_pos")
        last_action = agent_state.blackboard.get("_last_action", "")
        if last_pos is not None and last_action.startswith("move_") and state.position == last_pos:
            # Move failed - track consecutive failures
            fail_count = agent_state.blackboard.get("_move_fail_count", 0) + 1
            agent_state.blackboard["_move_fail_count"] = fail_count

            # After 3 consecutive failed moves, clear navigation cache and targets
            if fail_count >= 3:
                agent_state.navigator._cached_path = None
                agent_state.navigator._cached_target = None
                # Clear any target resource selection to force re-evaluation
                if fail_count >= 6:
                    agent_state.blackboard.pop("target_resource", None)
                    agent_state.blackboard["_move_fail_count"] = 0
        else:
            agent_state.blackboard["_move_fail_count"] = 0

        agent_state.blackboard["_last_pos"] = state.position

        # Vibe-driven role system: agent's role IS their vibe
        # "default" → set initial role vibe
        # "gear" → stem mode (role selection)
        # any valid role → run that role's goals

        # Time-based role conversion: aligner → scrambler at specified step
        if (
            self._convert_to_scrambler_at_step is not None
            and agent_state.step == self._convert_to_scrambler_at_step
            and agent_state.role == "aligner"
        ):
            if self._trace_enabled:
                print(f"[planky][t={agent_state.step} a={self._agent_id}] converting aligner→scrambler")
            agent_state.blackboard["change_role"] = "scrambler"

        # Check if goals want to change role (via blackboard)
        if "change_role" in agent_state.blackboard:
            new_role = agent_state.blackboard.pop("change_role")
            if new_role in VIBE_TO_ROLE:
                return Action(name=f"change_vibe_{new_role}"), agent_state

        # Map vibe to role
        current_vibe = state.vibe
        if current_vibe == "default":
            if self._role in VIBE_TO_ROLE:
                # Non-stem agent: set initial role vibe
                return Action(name=f"change_vibe_{self._role}"), agent_state
            else:
                # Stem agent: default vibe = stem mode
                effective_role = "stem"
        elif current_vibe == "gear":
            # Gear vibe = stem mode (role selection)
            effective_role = "stem"
        elif current_vibe in VIBE_TO_ROLE:
            effective_role = current_vibe
        else:
            if self._role in VIBE_TO_ROLE:
                return Action(name=f"change_vibe_{self._role}"), agent_state
            effective_role = "stem"

        # Update goals if role changed
        if effective_role != agent_state.role:
            if self._should_trace(agent_state):
                print(f"[planky][t={agent_state.step} a={self._agent_id}] role: {agent_state.role}→{effective_role}")
            # Record role change in timeline
            agent_state.stats.add_event(
                agent_state.step, "role_change", f"changed role: {agent_state.role} -> {effective_role}"
            )
            agent_state.stats.role_changes += 1
            agent_state.role = effective_role
            agent_state.goals = _make_goal_list(effective_role)

        # Build context
        should_trace = self._should_trace(agent_state)
        trace = TraceLog() if should_trace else None

        # Calculate steps since last useful action
        last_useful = agent_state.blackboard.get("_last_useful_step", 0)
        steps_since_useful = agent_state.step - last_useful
        if trace:
            trace.steps_since_useful = steps_since_useful

        # If we've been idle too long (100+ steps), force a reset of cached state
        # This helps break out of stuck loops
        if steps_since_useful >= 100 and steps_since_useful % 50 == 0:
            # Clear cached navigation and target selections
            agent_state.navigator._cached_path = None
            agent_state.navigator._cached_target = None
            agent_state.blackboard.pop("target_resource", None)
            if trace:
                trace.activate("IdleReset", f"clearing cache after {steps_since_useful} idle steps")

        ctx = PlankyContext(
            state=state,
            map=agent_state.entity_map,
            blackboard=agent_state.blackboard,
            navigator=agent_state.navigator,
            trace=trace,
            action_names=self._action_names,
            agent_id=self._agent_id,
            step=agent_state.step,
            my_collective_id=agent_state.my_collective_id,
        )

        # If we're stuck (many failed moves), force exploration to discover terrain
        fail_count = agent_state.blackboard.get("_move_fail_count", 0)
        if fail_count >= 6:
            action = agent_state.navigator.explore(
                state.position,
                agent_state.entity_map,
                direction_bias=["north", "east", "south", "west"][self._agent_id % 4],
            )
            agent_state.blackboard["_active_goal"] = f"ForceExplore(stuck={fail_count})"
            if trace:
                trace.active_goal_chain = agent_state.blackboard["_active_goal"]
                trace.action_name = action.name
        else:
            # Evaluate goals normally
            action = evaluate_goals(agent_state.goals, ctx)

        # Emit trace
        if trace:
            line = trace.format_line(
                step=agent_state.step,
                agent_id=self._agent_id,
                role=agent_state.role,
                pos=state.position,
                hp=state.hp,
                level=self._trace_level,
            )
            print(f"[planky] {line}")
            # Log collective resources and entity map info
            if agent_state.step % 25 == 0 or agent_state.step == 3:
                print(
                    f"[planky][t={agent_state.step} a={self._agent_id}] "
                    f"collective: C={state.collective_carbon} O={state.collective_oxygen} "
                    f"G={state.collective_germanium} S={state.collective_silicon} "
                    f"cargo={state.cargo_total}/{state.cargo_capacity} "
                    f"energy={state.energy}"
                )

        # Publish policy infos for renderer
        active_goal = trace.active_goal_chain if trace else ""
        nav_target = trace.nav_target if trace else None
        # Capture active goal and nav target even without tracing
        if not trace:
            active_goal = agent_state.blackboard.get("_active_goal", "")
            nav_target = agent_state.navigator._cached_target

        info: dict[str, Any] = {
            "role": agent_state.role,
            "goal": active_goal,
        }
        if nav_target:
            info["target"] = f"{nav_target[0]},{nav_target[1]}"
        target_resource = agent_state.blackboard.get("target_resource")
        if target_resource:
            info["mining"] = target_resource
        self._infos = info

        # Track action for failed-move detection
        agent_state.blackboard["_last_action"] = action.name

        # Record tick stats
        has_gear = self._has_role_gear(state, agent_state.role)
        moved = last_pos is not None and state.position != last_pos
        agent_state.stats.record_tick(
            role=agent_state.role,
            has_gear=has_gear,
            action_name=action.name,
            moved=moved,
        )

        return action, agent_state

    def _has_role_gear(self, state: StateSnapshot, role: str) -> bool:
        """Check if the agent has gear appropriate for their role."""
        if role == "miner":
            return state.miner_gear
        elif role == "scout":
            return state.scout_gear
        elif role == "aligner":
            return state.aligner_gear
        elif role == "scrambler":
            return state.scrambler_gear
        return False

    def _should_trace(self, agent_state: PlankyAgentState) -> bool:
        if not self._trace_enabled:
            return False
        if self._trace_agent >= 0 and self._agent_id != self._trace_agent:
            return False
        return True

    def _detect_useful_action(self, state: StateSnapshot, agent_state: PlankyAgentState) -> None:
        """Detect if a useful action occurred by comparing state changes.

        Useful actions:
        - Mine: cargo increased
        - Deposit: cargo decreased AND collective increased
        - Align/Scramble: heart decreased (spent on junction action)
        - Got gear: gear flag changed
        - Got heart: heart count increased
        """
        bb = agent_state.blackboard
        stats = agent_state.stats
        step = agent_state.step

        # Get previous state values
        prev_cargo = bb.get("_prev_cargo", 0)
        prev_heart = bb.get("_prev_heart", 0)
        prev_collective_total = bb.get("_prev_collective_total", 0)
        prev_collective_c = bb.get("_prev_collective_c", 0)
        prev_collective_o = bb.get("_prev_collective_o", 0)
        prev_collective_g = bb.get("_prev_collective_g", 0)
        prev_collective_s = bb.get("_prev_collective_s", 0)

        # Previous gear state
        prev_miner_gear = bb.get("_prev_miner_gear", False)
        prev_scout_gear = bb.get("_prev_scout_gear", False)
        prev_aligner_gear = bb.get("_prev_aligner_gear", False)
        prev_scrambler_gear = bb.get("_prev_scrambler_gear", False)

        # Calculate current values
        current_cargo = state.cargo_total
        current_heart = state.heart
        current_collective = (
            state.collective_carbon + state.collective_oxygen + state.collective_germanium + state.collective_silicon
        )

        # Detect useful actions
        useful = False

        # Mined resources (cargo increased)
        if current_cargo > prev_cargo:
            useful = True

        # Deposited resources (cargo decreased, collective increased)
        if current_cargo < prev_cargo and current_collective > prev_collective_total:
            useful = True
            # Track per-resource deposits for timeline
            if state.collective_carbon > prev_collective_c:
                stats.record_deposit(step, "carbon", state.collective_carbon - prev_collective_c)
            if state.collective_oxygen > prev_collective_o:
                stats.record_deposit(step, "oxygen", state.collective_oxygen - prev_collective_o)
            if state.collective_germanium > prev_collective_g:
                stats.record_deposit(step, "germanium", state.collective_germanium - prev_collective_g)
            if state.collective_silicon > prev_collective_s:
                stats.record_deposit(step, "silicon", state.collective_silicon - prev_collective_s)

        # Got a heart (heart increased)
        if current_heart > prev_heart:
            useful = True

        # Spent a heart on align/scramble (heart decreased)
        if current_heart < prev_heart:
            useful = True
            # Track junction action based on current role
            stats.record_junction_action(agent_state.role)

        # Detect gear acquisition
        if state.miner_gear and not prev_miner_gear:
            stats.add_event(step, "got_gear", "got miner gear")
        if state.scout_gear and not prev_scout_gear:
            stats.add_event(step, "got_gear", "got scout gear")
        if state.aligner_gear and not prev_aligner_gear:
            stats.add_event(step, "got_gear", "got aligner gear")
        if state.scrambler_gear and not prev_scrambler_gear:
            stats.add_event(step, "got_gear", "got scrambler gear")

        # Detect gear loss
        if prev_miner_gear and not state.miner_gear:
            stats.add_event(step, "lost_gear", "lost miner gear")
        if prev_scout_gear and not state.scout_gear:
            stats.add_event(step, "lost_gear", "lost scout gear")
        if prev_aligner_gear and not state.aligner_gear:
            stats.add_event(step, "lost_gear", "lost aligner gear")
        if prev_scrambler_gear and not state.scrambler_gear:
            stats.add_event(step, "lost_gear", "lost scrambler gear")

        # Update tracking
        if useful:
            bb["_last_useful_step"] = agent_state.step

        # Store current values for next tick comparison
        bb["_prev_cargo"] = current_cargo
        bb["_prev_heart"] = current_heart
        bb["_prev_collective_total"] = current_collective
        bb["_prev_collective_c"] = state.collective_carbon
        bb["_prev_collective_o"] = state.collective_oxygen
        bb["_prev_collective_g"] = state.collective_germanium
        bb["_prev_collective_s"] = state.collective_silicon
        bb["_prev_miner_gear"] = state.miner_gear
        bb["_prev_scout_gear"] = state.scout_gear
        bb["_prev_aligner_gear"] = state.aligner_gear
        bb["_prev_scrambler_gear"] = state.scrambler_gear


class PlankyPolicy(MultiAgentPolicy):
    """Multi-agent goal-tree policy with URI-based role distribution.

    URI parameters:
        ?miner=4&scout=0&aligner=2&scrambler=4  — role counts
        ?trace=1&trace_level=2&trace_agent=0     — tracing
    """

    short_names = ["planky"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        device: str = "cpu",
        # Role counts — if stem > 0, defaults to all-stem unless explicit roles given
        miner: int = -1,
        scout: int = 0,
        aligner: int = -1,
        scrambler: int = -1,
        stem: int = 0,
        # Tracing, bio, and stats
        trace: int = 0,
        trace_level: int = 1,
        trace_agent: int = -1,
        bio: int = 0,
        stats: int = 0,
        # Accept any extra kwargs
        **kwargs: object,
    ) -> None:
        super().__init__(policy_env_info, device=device)
        self._feature_by_id = {f.id: f for f in policy_env_info.obs_features}
        self._action_name_to_index = {name: idx for idx, name in enumerate(policy_env_info.action_names)}
        self._noop_action_value = dtype_actions.type(self._action_name_to_index.get("noop", 0))

        # Tracing, bio (detailed agent timelines), and stats output
        self._trace_enabled = bool(trace)
        self._trace_level = trace_level
        self._trace_agent = trace_agent
        self._bio_enabled = bool(bio)
        self._stats_enabled = bool(stats)

        # Resolve defaults: if stem > 0 and miner/aligner/scrambler not explicitly set, zero them
        # If ANY explicit role is provided (not -1), treat unset roles as 0 to avoid surprises
        any_explicit = miner >= 0 or aligner >= 0 or scrambler >= 0 or scout > 0
        if stem > 0 or any_explicit:
            if miner == -1:
                miner = 0
            if aligner == -1:
                aligner = 0
            if scrambler == -1:
                scrambler = 0
        else:
            # Pure defaults (no explicit roles, no stem)
            miner = 4
            aligner = 4
            scrambler = 0

        # Build per-team role distribution
        team_roles: list[str] = []
        team_roles.extend(["miner"] * miner)
        team_roles.extend(["scout"] * scout)
        team_roles.extend(["aligner"] * aligner)
        team_roles.extend(["scrambler"] * scrambler)
        team_roles.extend(["stem"] * stem)

        # Tile the role distribution to cover all agents (supports multi-team setups).
        num_agents = policy_env_info.num_agents
        team_size = len(team_roles) if team_roles else 1
        num_teams = max(1, (num_agents + team_size - 1) // team_size)
        self._role_distribution: list[str] = (team_roles * num_teams)[:num_agents]

        # Find the first aligner agent_id for delayed scrambler conversion
        self._first_aligner_id: int | None = None
        for agent_id, role in enumerate(self._role_distribution):
            if role == "aligner":
                self._first_aligner_id = agent_id
                break

        if self._trace_enabled:
            print(f"[planky] Role distribution ({num_teams} teams): {self._role_distribution}")
            if self._first_aligner_id is not None:
                print(f"[planky] First aligner (agent {self._first_aligner_id}) will convert to scrambler at step 1000")

        self._agent_policies: dict[int, StatefulAgentPolicy[PlankyAgentState]] = {}
        self._max_step_seen = 0
        self._stats_dumped = False

        # Register for atexit stats dumping
        _policy_registry.add(self)

    def agent_policy(self, agent_id: int) -> StatefulAgentPolicy[PlankyAgentState]:
        if agent_id not in self._agent_policies:
            role = self._role_distribution[agent_id] if agent_id < len(self._role_distribution) else "default"

            # First aligner converts to scrambler at step 1000
            convert_to_scrambler_at_step = 1000 if agent_id == self._first_aligner_id else None

            brain = PlankyBrain(
                policy_env_info=self._policy_env_info,
                agent_id=agent_id,
                role=role,
                trace_enabled=self._trace_enabled,
                trace_level=self._trace_level,
                trace_agent=self._trace_agent,
                convert_to_scrambler_at_step=convert_to_scrambler_at_step,
            )

            self._agent_policies[agent_id] = StatefulAgentPolicy(
                brain,
                self._policy_env_info,
                agent_id=agent_id,
            )

        return self._agent_policies[agent_id]

    def step_batch(self, raw_observations: np.ndarray, raw_actions: np.ndarray) -> None:
        raw_actions[...] = self._noop_action_value
        num_agents = min(raw_observations.shape[0], self._policy_env_info.num_agents)
        for agent_id in range(num_agents):
            obs = self._raw_obs_to_agent_obs(agent_id, raw_observations[agent_id])
            action = self.agent_policy(agent_id).step(obs)
            action_index = self._action_name_to_index.get(action.name, 0)
            raw_actions[agent_id] = dtype_actions.type(action_index)

        # Track max step for end-of-episode detection
        self._max_step_seen = max(
            self._max_step_seen,
            max(
                (p._state.step if p._state else 0 for p in self._agent_policies.values()),
                default=0,
            ),
        )

    def reset(self) -> None:
        """Reset policy state; dump stats from previous episode if any."""
        # Only dump stats if we actually ran steps (max_step_seen > 10 to avoid init noise)
        if self._agent_policies and self._max_step_seen > 10 and not self._stats_dumped:
            self._dump_episode_stats()
        self._agent_policies.clear()
        self._max_step_seen = 0
        self._stats_dumped = False

    def __del__(self) -> None:
        """Dump stats on garbage collection if not already dumped."""
        try:
            if hasattr(self, "_stats_dumped") and not self._stats_dumped and self._agent_policies:
                self._dump_episode_stats()
        except Exception:
            pass  # Suppress errors during interpreter shutdown

    def _dump_episode_stats(self) -> None:
        """Print episode stats table at end of episode."""
        self._stats_dumped = True

        # Skip if stats/trace not enabled
        if not (self._stats_enabled or self._trace_enabled):
            return

        # Skip if no policies
        if not self._agent_policies:
            return

        # Collect stats from all agents
        agent_stats: list[tuple[int, str, int | None, AgentTickStats]] = []
        for agent_id, policy in self._agent_policies.items():
            if policy._state is None:
                continue
            state = policy._state
            # Skip if no actual ticks recorded
            if not state.stats.ticks_by_role:
                continue
            # Finalize stats (flush pending deposits)
            state.stats.finalize()
            agent_stats.append(
                (
                    agent_id,
                    state.role,
                    state.my_collective_id,
                    state.stats,
                )
            )

        if not agent_stats:
            return

        # Print header
        print("\n" + "=" * 100)
        print("PLANKY EPISODE STATS")
        print("=" * 100)

        # Per-agent table
        print("\n--- Per Agent ---")
        print(
            f"{'Agent':>6} {'Role':>10} {'Team':>6} {'Ticks':>8} {'w/Gear':>8} "
            f"{'Moving':>8} {'Still':>8} {'Aligned':>8} {'Scrambled':>9}"
        )
        print("-" * 90)
        for agent_id, role, collective_id, stats in sorted(agent_stats):
            total_ticks = sum(stats.ticks_by_role.values())
            total_gear = sum(stats.ticks_with_gear_by_role.values())
            total_moving = sum(stats.ticks_moving_by_role.values())
            total_still = sum(stats.ticks_still_by_role.values())
            team = "cogs" if collective_id == 1 else "clips" if collective_id == 0 else "?"
            aligned = stats._junctions_aligned
            scrambled = stats._junctions_scrambled
            print(
                f"{agent_id:>6} {role:>10} {team:>6} {total_ticks:>8} {total_gear:>8} "
                f"{total_moving:>8} {total_still:>8} {aligned:>8} {scrambled:>9}"
            )

        # Per-role aggregate
        print("\n--- Per Role ---")
        hdr = f"{'Role':>12} {'Ticks':>8} {'w/Gear':>8} {'Moving':>8} {'Still':>8}"
        print(f"{hdr} {'%Gear':>8} {'%Moving':>8} {'%Still':>8}")
        print("-" * 90)
        role_totals: dict[str, dict[str, int]] = {}
        for _, _, _, stats in agent_stats:
            for role in stats.ticks_by_role:
                if role not in role_totals:
                    role_totals[role] = {"ticks": 0, "gear": 0, "moving": 0, "still": 0}
                role_totals[role]["ticks"] += stats.ticks_by_role.get(role, 0)
                role_totals[role]["gear"] += stats.ticks_with_gear_by_role.get(role, 0)
                role_totals[role]["moving"] += stats.ticks_moving_by_role.get(role, 0)
                role_totals[role]["still"] += stats.ticks_still_by_role.get(role, 0)

        for role in sorted(role_totals.keys()):
            t = role_totals[role]
            ticks = t["ticks"]
            pct_gear = (t["gear"] / ticks * 100) if ticks > 0 else 0
            pct_moving = (t["moving"] / ticks * 100) if ticks > 0 else 0
            pct_still = (t["still"] / ticks * 100) if ticks > 0 else 0
            print(
                f"{role:>12} {ticks:>8} {t['gear']:>8} {t['moving']:>8} {t['still']:>8} "
                f"{pct_gear:>7.1f}% {pct_moving:>7.1f}% {pct_still:>7.1f}%"
            )

        # Per-team aggregate
        print("\n--- Per Team ---")
        hdr = f"{'Team':>12} {'Ticks':>8} {'w/Gear':>8} {'Moving':>8} {'Still':>8}"
        print(f"{hdr} {'%Gear':>8} {'%Moving':>8} {'%Still':>8}")
        print("-" * 90)
        zero_stats = {"ticks": 0, "gear": 0, "moving": 0, "still": 0}
        team_totals: dict[str, dict[str, int]] = {
            "c": dict(zero_stats),
            "clips": dict(zero_stats),
        }
        for _, _, collective_id, stats in agent_stats:
            team = "cogs" if collective_id == 1 else "clips" if collective_id == 0 else None
            if team is None:
                continue
            team_totals[team]["ticks"] += sum(stats.ticks_by_role.values())
            team_totals[team]["gear"] += sum(stats.ticks_with_gear_by_role.values())
            team_totals[team]["moving"] += sum(stats.ticks_moving_by_role.values())
            team_totals[team]["still"] += sum(stats.ticks_still_by_role.values())

        for team in ["c", "clips"]:
            t = team_totals[team]
            ticks = t["ticks"]
            if ticks == 0:
                continue
            pct_gear = (t["gear"] / ticks * 100) if ticks > 0 else 0
            pct_moving = (t["moving"] / ticks * 100) if ticks > 0 else 0
            pct_still = (t["still"] / ticks * 100) if ticks > 0 else 0
            print(
                f"{team:>12} {ticks:>8} {t['gear']:>8} {t['moving']:>8} {t['still']:>8} "
                f"{pct_gear:>7.1f}% {pct_moving:>7.1f}% {pct_still:>7.1f}%"
            )

        # Miner-specific: mining actions with/without gear
        total_mining_with_gear = sum(s.mining_actions_with_gear for _, _, _, s in agent_stats)
        total_mining_without_gear = sum(s.mining_actions_without_gear for _, _, _, s in agent_stats)
        total_mining = total_mining_with_gear + total_mining_without_gear
        if total_mining > 0:
            print("\n--- Miner Gear Efficiency ---")
            pct_with = (total_mining_with_gear / total_mining * 100) if total_mining > 0 else 0
            print(f"Mining actions with gear:    {total_mining_with_gear:>6} ({pct_with:>5.1f}%)")
            print(f"Mining actions without gear: {total_mining_without_gear:>6} ({100 - pct_with:>5.1f}%)")

        # Agent timelines (only if trace or bio enabled)
        if self._trace_enabled or self._bio_enabled:
            print("\n--- Agent Timelines ---")
            for agent_id, role, collective_id, stats in sorted(agent_stats):
                team = "cogs" if collective_id == 1 else "clips" if collective_id == 0 else "?"
                initial = stats.initial_role or "?"
                changes = stats.role_changes
                print(
                    f"\nAgent {agent_id} ({team}, initial role: {initial}, "
                    f"role changes: {changes}, final role: {role}):"
                )
                if not stats.timeline:
                    print("  (no events)")
                for event in stats.timeline:
                    # Summary events (high step numbers) show as "end"
                    if event.step >= 999000:
                        print(f"    end: {event.description}")
                    else:
                        print(f"  {event.step:>5}: {event.description}")

        print("=" * 100 + "\n")

    def _raw_obs_to_agent_obs(self, agent_id: int, raw_obs: np.ndarray) -> AgentObservation:
        tokens: list[ObservationToken] = []
        for token in raw_obs:
            feature_id = int(token[1])
            if feature_id == 0xFF:
                break
            feature = self._feature_by_id.get(feature_id)
            if feature is None:
                continue
            location_packed = int(token[0])
            value = int(token[2])
            tokens.append(
                ObservationToken(
                    feature=feature,
                    value=value,
                    raw_token=(location_packed, feature_id, value),
                )
            )
        return AgentObservation(agent_id=agent_id, tokens=tokens)
