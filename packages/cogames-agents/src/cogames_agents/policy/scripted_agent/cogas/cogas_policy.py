"""
Cogas Policy v3 -- high-throughput junction alignment competitive agent.

Combines Planky's declarative goal decomposition with game-phase awareness
(EARLY -> MID -> LATE) and dynamic role switching for maximizing
junction.held.

v3 throughput improvements:
  - More aggressive aligner-heavy defaults (5 aligners, 2 scramblers)
  - Faster flex agent transitions at step 40 (was 50) or 400 explored (was 500)
  - Reduced cooldowns and increased chain lookahead for faster junction capture

Phases:
  EARLY  (steps 0-200):  exploration + gear acquisition
  MID    (steps 200-1000): aggressive junction capture, heavy aligner/scrambler
  LATE   (steps 1000+):   mop up (clips events stop at 1000)

Optional evolution mode (evolution=1) uses EvolutionaryRoleCoordinator to
discover optimal role compositions through evolutionary selection.

URI: metta://policy/cogas
Parameters: ?miner=2&scout=1&aligner=5&scrambler=2&defensive=0
            ?trace=1&trace_level=2&trace_agent=0
            ?debug=0/1/2
            ?evolution=0&evolution_games=10&evolution_persist=
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np

from cogames_agents.policy.evolution.cogsguard.evolution import EvolutionConfig
from cogames_agents.policy.evolution.cogsguard.evolutionary_coordinator import (
    AgentRoleAssignment,
    EvolutionaryRoleCoordinator,
)
from cogames_agents.policy.scripted_agent.planky.context import PlankyContext, StateSnapshot
from cogames_agents.policy.scripted_agent.planky.entity_map import EntityMap
from cogames_agents.policy.scripted_agent.planky.goal import Goal, evaluate_goals
from cogames_agents.policy.scripted_agent.planky.navigator import Navigator
from cogames_agents.policy.scripted_agent.planky.obs_parser import ObsParser
from cogames_agents.policy.scripted_agent.planky.trace import TraceLog
from mettagrid.mettagrid_c import dtype_actions
from mettagrid.policy.policy import MultiAgentPolicy, StatefulAgentPolicy, StatefulPolicyImpl
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Action
from mettagrid.simulator.interface import AgentObservation

from .debug_logger import DebugLogger
from .goals import (
    make_aligner_goals,
    make_defensive_goals,
    make_miner_goals,
    make_scout_goals,
    make_scrambler_goals,
)
from .resource_manager import ResourceManager

# Role vibes (defensive uses aligner vibe to re-align junctions)
VIBE_TO_ROLE = {"miner", "scout", "aligner", "scrambler", "defensive"}

# Default spawn position (center of 200x200 grid)
SPAWN_POS = (100, 100)

# Energy cost per move
ENERGY_PER_MOVE = 3
ENERGY_RESERVE = 15


class Phase(Enum):
    EARLY = "early"  # Steps 0-200: exploration + gear acquisition
    MID = "mid"  # Steps 200-1000: aggressive junction capture (clips events active)
    LATE = "late"  # Steps 1000+: mop up (clips events stop at 1000)


class Coordinator:
    """Shared team coordinator for heart reservation, junction assignment, and score tracking."""

    def __init__(self) -> None:
        # Heart reservation: agent_id -> True if reserved
        self._heart_reservations: set[int] = set()
        # Heart priority: agent_id -> priority (lower = higher priority)
        self._heart_priorities: dict[int, int] = {}
        # Junction claims: position -> agent_id
        self._junction_claims: dict[tuple[int, int], int] = {}
        # Scramble claims: position -> agent_id
        self._scramble_claims: dict[tuple[int, int], int] = {}
        # Shared map knowledge across agents
        self._shared_entities: dict[tuple[int, int], Any] = {}
        # Shared station locations: station_type -> position
        self._known_stations: dict[str, tuple[int, int]] = {}
        # Score tracking: estimated junction counts per team
        self._cogs_junctions: int = 0
        self._clips_junctions: int = 0
        self._score_update_step: int = -1
        # Heart economy tracking
        self._heart_consumers: int = 0  # Number of agents that need hearts (aligners + scramblers)
        self._max_concurrent_heart_pickups: int = 2
        # Shared resource manager for miner coordination
        self._resource_manager = ResourceManager()

    def set_heart_consumers(self, count: int) -> None:
        """Set the number of heart-consuming agents. Scales max concurrent pickups."""
        self._heart_consumers = count
        # Scale: allow up to ~40% of consumers to pick up hearts concurrently
        # but at least 2 and at most 4 to avoid total contention
        self._max_concurrent_heart_pickups = max(2, min(4, (count + 1) // 2))

    def register_heart_priority(self, agent_id: int, role: str) -> None:
        """Register heart pickup priority for an agent. Aligners get priority over scramblers."""
        # Aligners are higher priority (0) since they directly score points
        # Scramblers are lower priority (1) since they deny enemy points
        self._heart_priorities[agent_id] = 0 if role == "aligner" else 1

    def reserve_heart(self, agent_id: int) -> bool:
        """Reserve a heart pickup slot. Returns True if reservation granted.

        Uses dynamic capacity based on team size and priority-based preemption
        so aligners can get hearts before scramblers when capacity is tight.
        """
        if agent_id in self._heart_reservations:
            return True
        if len(self._heart_reservations) < self._max_concurrent_heart_pickups:
            self._heart_reservations.add(agent_id)
            return True
        # Capacity full — check if this agent has higher priority than any current holder
        my_priority = self._heart_priorities.get(agent_id, 1)
        if my_priority == 0:  # Aligner trying to preempt
            for held_id in list(self._heart_reservations):
                if self._heart_priorities.get(held_id, 1) > my_priority:
                    # Preempt lower-priority holder
                    self._heart_reservations.discard(held_id)
                    self._heart_reservations.add(agent_id)
                    return True
        return False

    def release_heart(self, agent_id: int) -> None:
        self._heart_reservations.discard(agent_id)

    def share_station(self, station_type: str, position: tuple[int, int]) -> None:
        """Share a discovered station location with the team."""
        self._known_stations[station_type] = position

    def get_shared_station(self, station_type: str) -> Optional[tuple[int, int]]:
        """Get a previously discovered station location."""
        return self._known_stations.get(station_type)

    def claim_junction(self, agent_id: int, pos: tuple[int, int]) -> bool:
        """Claim a junction target. Returns True if granted."""
        current = self._junction_claims.get(pos)
        if current is None or current == agent_id:
            self._junction_claims[pos] = agent_id
            return True
        return False

    def release_junction(self, agent_id: int) -> None:
        to_remove = [p for p, a in self._junction_claims.items() if a == agent_id]
        for p in to_remove:
            del self._junction_claims[p]

    def claimed_junctions(self) -> set[tuple[int, int]]:
        return set(self._junction_claims.keys())

    def claim_scramble(self, agent_id: int, pos: tuple[int, int]) -> bool:
        """Claim a scramble target."""
        current = self._scramble_claims.get(pos)
        if current is None or current == agent_id:
            self._scramble_claims[pos] = agent_id
            return True
        return False

    def release_scramble(self, agent_id: int) -> None:
        to_remove = [p for p, a in self._scramble_claims.items() if a == agent_id]
        for p in to_remove:
            del self._scramble_claims[p]

    def claimed_scrambles(self) -> set[tuple[int, int]]:
        return set(self._scramble_claims.keys())

    def update_score(self, entity_map: Any, step: int) -> None:
        """Estimate team scores from shared entity map. Called once per step."""
        if step == self._score_update_step:
            return
        self._score_update_step = step
        self._cogs_junctions = len(
            entity_map.find(type_contains="junction", property_filter={"alignment": "cogs"})
        ) + len(entity_map.find(type_contains="junction", property_filter={"alignment": "cogs"}))
        self._clips_junctions = len(
            entity_map.find(type_contains="junction", property_filter={"alignment": "clips"})
        ) + len(entity_map.find(type_contains="junction", property_filter={"alignment": "clips"}))

    @property
    def is_winning(self) -> bool:
        return self._cogs_junctions > self._clips_junctions

    @property
    def is_losing(self) -> bool:
        return self._clips_junctions > self._cogs_junctions

    @property
    def cogs_junctions(self) -> int:
        return self._cogs_junctions

    @property
    def clips_junctions(self) -> int:
        return self._clips_junctions


class CogasAgentState:
    """Persistent state for a Cogas agent."""

    def __init__(self, agent_id: int, role: str, goals: list[Goal]) -> None:
        self.agent_id = agent_id
        self.role = role
        self.goals = goals
        self.entity_map = EntityMap()
        self.navigator = Navigator()
        self.blackboard: dict[str, Any] = {}
        self.step = 0
        self.phase = Phase.EARLY


class CogasBrain(StatefulPolicyImpl[CogasAgentState]):
    """Per-agent brain with phase-aware goal evaluation."""

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        agent_id: int,
        role: str,
        coordinator: Coordinator,
        trace_enabled: bool = False,
        trace_level: int = 1,
        trace_agent: int = -1,
        debug_logger: Optional[DebugLogger] = None,
    ) -> None:
        self._agent_id = agent_id
        self._policy_env_info = policy_env_info
        self._role = role
        self._coordinator = coordinator
        self._obs_parser = ObsParser(policy_env_info)
        self._action_names = policy_env_info.action_names

        self._trace_enabled = trace_enabled
        self._trace_level = trace_level
        self._trace_agent = trace_agent
        self._debug_logger = debug_logger

    def initial_agent_state(self) -> CogasAgentState:
        goals = self._make_goals_for_phase(Phase.EARLY)
        return CogasAgentState(
            agent_id=self._agent_id,
            role=self._role,
            goals=goals,
        )

    def step_with_state(self, obs: AgentObservation, agent_state: CogasAgentState) -> tuple[Action, CogasAgentState]:
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

        # Detect failed moves
        last_pos = agent_state.blackboard.get("_last_pos")
        last_action = agent_state.blackboard.get("_last_action", "")
        if last_pos is not None and last_action.startswith("move_") and state.position == last_pos:
            fail_count = agent_state.blackboard.get("_move_fail_count", 0) + 1
            agent_state.blackboard["_move_fail_count"] = fail_count
            if fail_count >= 10:
                agent_state.navigator._cached_path = None
                agent_state.navigator._cached_target = None
                if fail_count >= 15:
                    agent_state.blackboard.pop("target_resource", None)
                    agent_state.blackboard["_move_fail_count"] = 0
        else:
            agent_state.blackboard["_move_fail_count"] = 0

        agent_state.blackboard["_last_pos"] = state.position

        # Handle vibe activation (defensive uses aligner vibe)
        vibe_name = "aligner" if self._role == "defensive" else self._role
        if self._role in VIBE_TO_ROLE and state.vibe != vibe_name:
            # Try to set the right vibe; limit retries to avoid infinite loops
            vibe_retries = agent_state.blackboard.get("_vibe_retries", 0)
            if vibe_retries < 3:
                agent_state.blackboard["_vibe_retries"] = vibe_retries + 1
                return Action(name=f"change_vibe_{vibe_name}"), agent_state
            # After 3 retries, stop trying and proceed with goals
            # (the vibe may not exist or may require gear first)
        else:
            # Vibe matches — reset retry counter
            agent_state.blackboard["_vibe_retries"] = 0

        # Phase transitions
        new_phase = self._evaluate_phase(agent_state, state)
        if new_phase != agent_state.phase:
            old_phase = agent_state.phase
            agent_state.phase = new_phase
            # Dynamic role switching on phase transitions
            self._check_phase_role_switch(agent_state, old_phase, new_phase)
            agent_state.goals = self._make_goals_for_phase(new_phase)
            if self._should_trace(agent_state):
                message = (
                    f"[cogas][t={agent_state.step} a={self._agent_id}] phase->{new_phase.value} role={agent_state.role}"
                )
                print(message)
        elif new_phase == Phase.LATE and agent_state.step % 20 == 0:
            # Re-evaluate goals periodically in late game as score changes
            agent_state.goals = self._make_goals_for_phase(new_phase)

        # Build context
        should_trace = self._should_trace(agent_state)
        trace = TraceLog() if should_trace else None

        ctx = PlankyContext(
            state=state,
            map=agent_state.entity_map,
            blackboard=agent_state.blackboard,
            navigator=agent_state.navigator,
            trace=trace,
            action_names=self._action_names,
            agent_id=self._agent_id,
            step=agent_state.step,
        )

        # Store coordinator in blackboard for goals to access
        ctx.blackboard["_coordinator"] = self._coordinator

        # Stuck detection with forced exploration — threshold raised to 10 to
        # allow station bumping (bumps look like "failed moves" since position
        # doesn't change, but they DO trigger gear/heart/alignment interactions)
        fail_count = agent_state.blackboard.get("_move_fail_count", 0)
        if fail_count >= 10:
            action = agent_state.navigator.explore(
                state.position,
                agent_state.entity_map,
                direction_bias=["north", "east", "south", "west"][self._agent_id % 4],
            )
            if trace:
                trace.active_goal_chain = f"ForceExplore(stuck={fail_count})"
                trace.action_name = action.name
        else:
            action = evaluate_goals(agent_state.goals, ctx)

        # Energy gate: if action is a move but energy < move cost, noop instead
        # of wasting a step on a guaranteed-to-fail move. Non-move actions
        # (change_vibe, use, bump) pass through unaffected.
        if action.name.startswith("move_") and state.energy < ENERGY_PER_MOVE:
            action = Action(name="noop")

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
            print(f"[cogas] {line}")

        # Debug logging
        if self._debug_logger is not None:
            # Determine target from coordinator claims
            target = None
            claimed = self._coordinator._junction_claims
            for pos, aid in claimed.items():
                if aid == self._agent_id:
                    target = pos
                    break
            if target is None:
                scr = self._coordinator._scramble_claims
                for pos, aid in scr.items():
                    if aid == self._agent_id:
                        target = pos
                        break

            self._debug_logger.record_agent_tick(
                agent_id=self._agent_id,
                role=agent_state.role,
                position=state.position,
                action=action.name,
                target=target,
                phase=agent_state.phase.value,
                hp=state.hp,
                energy=state.energy,
                step=agent_state.step,
            )

        agent_state.blackboard["_last_action"] = action.name
        return action, agent_state

    def _evaluate_phase(self, agent_state: CogasAgentState, state: StateSnapshot) -> Phase:
        """Determine current phase based on game step.

        Phase boundaries:
          EARLY  (0-200):  exploration + gear acquisition
          MID    (200-1000): aggressive junction capture (clips events active until 1000)
          LATE   (1000+):  mop up — clips events stop, uncontested alignment
        """
        step = agent_state.step

        # Update shared score estimate
        self._coordinator.update_score(agent_state.entity_map, step)

        if step <= 200:
            return Phase.EARLY
        if step <= 1000:
            return Phase.MID
        return Phase.LATE

    def _has_role_gear(self, state: StateSnapshot) -> bool:
        role = self._role
        if role == "defensive":
            role = "aligner"  # Defensive uses aligner gear
        gear_map = {
            "miner": state.miner_gear,
            "scout": state.scout_gear,
            "aligner": state.aligner_gear,
            "scrambler": state.scrambler_gear,
        }
        return gear_map.get(role, False)

    def _make_goals_for_phase(self, phase: Phase) -> list[Goal]:
        """Create role-specific goal list for the given phase."""
        role = self._role

        winning = self._coordinator.is_winning
        losing = self._coordinator.is_losing

        if role == "miner":
            return make_miner_goals(phase)
        elif role == "scout":
            return make_scout_goals(phase)
        elif role == "aligner":
            return make_aligner_goals(phase, self._coordinator, self._agent_id, winning=winning)
        elif role == "scrambler":
            return make_scrambler_goals(phase, self._coordinator, self._agent_id, losing=losing)
        elif role == "defensive":
            return make_defensive_goals(phase, self._coordinator, self._agent_id)
        else:
            return []

    def _check_phase_role_switch(self, agent_state: CogasAgentState, old_phase: Phase, new_phase: Phase) -> None:
        """Dynamically switch agent roles based on game phase and score.

        Late game (post-1000): clips events stop, so scramblers less needed.
        Convert scouts to aligners in mid game.
        Keep miners mining — resource throughput is critical.
        """
        if new_phase == Phase.LATE:
            # After clips events stop (step 1000+), scouts become aligners
            if self._role == "scout":
                self._role = "aligner"
                agent_state.role = "aligner"
                if self._should_trace(agent_state):
                    print(f"[cogas][t={agent_state.step} a={self._agent_id}] role->aligner (late phase)")
            # Keep miners mining — resource pipeline is the bottleneck
            # Keep scramblers to clean up remaining clips junctions
        elif new_phase == Phase.MID and self._role == "scout":
            self._role = "aligner"
            agent_state.role = "aligner"
            if self._should_trace(agent_state):
                print(f"[cogas][t={agent_state.step} a={self._agent_id}] role->aligner (mid phase)")

    def _check_flex_transition(self, agent_state: CogasAgentState, state: StateSnapshot) -> None:
        """Transition flex agent from scout to aligner when appropriate."""
        if agent_state.blackboard.get("_flex_transitioned"):
            return

        explored = len(agent_state.entity_map.explored)
        should_transition = agent_state.step > 40 or explored > 400

        if should_transition:
            agent_state.blackboard["_flex_transitioned"] = True
            self._role = "aligner"
            agent_state.role = "aligner"
            agent_state.goals = make_aligner_goals(agent_state.phase, self._coordinator, self._agent_id)
            if self._should_trace(agent_state):
                print(f"[cogas][t={agent_state.step} a={self._agent_id}] flex->aligner")

    def _should_trace(self, agent_state: CogasAgentState) -> bool:
        if not self._trace_enabled:
            return False
        if self._trace_agent >= 0 and self._agent_id != self._trace_agent:
            return False
        return True


class CogasPolicy(MultiAgentPolicy):
    """Multi-agent phased goal-tree policy for competitive CogsGuard play.

    URI: metta://policy/cogas
    Parameters:
        ?miner=2&scout=1&aligner=4&scrambler=3&defensive=0  -- role counts
        ?trace=1&trace_level=2&trace_agent=0                 -- tracing
    """

    short_names = ["cogas"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        device: str = "cpu",
        # Role counts - v3 high-throughput aligner-heavy distribution
        miner: int = 2,
        scout: int = 1,
        aligner: int = 5,
        scrambler: int = 2,
        defensive: int = 0,
        # Tracing
        trace: int = 0,
        trace_level: int = 1,
        trace_agent: int = -1,
        # Debug logging
        debug: int = 0,
        # Evolution mode
        evolution: int = 0,
        evolution_games: int = 10,
        evolution_persist: str = "",
        # Accept any extra kwargs
        **kwargs: object,
    ) -> None:
        super().__init__(policy_env_info, device=device)
        self._feature_by_id = {f.id: f for f in policy_env_info.obs_features}
        self._action_name_to_index = {name: idx for idx, name in enumerate(policy_env_info.action_names)}
        self._noop_action_value = dtype_actions.type(self._action_name_to_index.get("noop", 0))

        self._trace_enabled = bool(trace)
        self._trace_level = trace_level
        self._trace_agent = trace_agent

        # Shared coordinator
        self._coordinator = Coordinator()

        # Build role distribution
        self._role_distribution: list[str] = []
        self._role_distribution.extend(["aligner"] * aligner)
        self._role_distribution.extend(["scrambler"] * scrambler)
        self._role_distribution.extend(["miner"] * miner)
        self._role_distribution.extend(["scout"] * scout)
        if defensive:
            self._role_distribution.extend(["defensive"] * defensive)

        # Evolution mode
        self._evolution_enabled = bool(evolution)
        self._evolution_coordinator: Optional[EvolutionaryRoleCoordinator] = None
        self._evolution_persist_path: Optional[Path] = Path(evolution_persist) if evolution_persist else None
        if self._evolution_enabled:
            num_agents_evo = len(self._role_distribution)
            config = EvolutionConfig()
            self._evolution_coordinator = EvolutionaryRoleCoordinator(
                num_agents=num_agents_evo,
                config=config,
                games_per_generation=int(evolution_games),
            )
            # Seed from cogas role distribution to bias initial generation
            self._seed_evolution_from_cogas()
            # Load persisted best config if available
            if self._evolution_persist_path and self._evolution_persist_path.exists():
                self._load_evolution_state()
            print(
                f"[cogas:evolution] Enabled: generation={self._evolution_coordinator.generation}, "
                f"games_per_gen={evolution_games}, persist={evolution_persist or 'none'}",
                file=sys.stderr,
            )

        # Debug logger
        num_agents = len(self._role_distribution)
        self._debug_logger: Optional[DebugLogger] = None
        if debug >= 1:
            self._debug_logger = DebugLogger(level=debug, num_agents=num_agents)

        if self._trace_enabled:
            dist = self._role_distribution
            if self._evolution_enabled:
                dist = self._get_evolved_role_distribution()
            print(f"[cogas] Role distribution: {dist}")

        # Configure heart economy based on role distribution
        heart_consumers = sum(1 for r in self._role_distribution if r in ("aligner", "scrambler", "defensive"))
        self._coordinator.set_heart_consumers(heart_consumers)

        self._agent_policies: dict[int, StatefulAgentPolicy[CogasAgentState]] = {}
        self._episode_count: int = 0
        # Track per-episode aligned junction scores for evolution fitness
        self._episode_aligned_scores: list[float] = []

    # -- Evolution helpers --------------------------------------------------

    def _seed_evolution_from_cogas(self) -> None:
        """Seed the evolutionary coordinator's initial role distribution
        to match the static cogas role counts so evolution starts from a
        known-good baseline."""
        if self._evolution_coordinator is None:
            return
        # Map the static distribution into initial role assignments so the
        # coordinator starts with the same balance as the hand-tuned config.
        for agent_id, role_name in enumerate(self._role_distribution):
            vibe_to_base = {
                "miner": "BaseMiner",
                "scout": "BaseScout",
                "aligner": "BaseAligner",
                "scrambler": "BaseScrambler",
                "flex": "BaseScout",  # flex starts as scout
            }
            base_role_name = vibe_to_base.get(role_name, "BaseMiner")
            catalog = self._evolution_coordinator.catalog
            role_id = catalog.find_role_id(base_role_name)
            if role_id >= 0 and role_id < len(catalog.roles):
                self._evolution_coordinator.agent_assignments[agent_id] = AgentRoleAssignment(
                    agent_id=agent_id,
                    role_id=role_id,
                    role_name=base_role_name,
                )

    def _get_evolved_role_distribution(self) -> list[str]:
        """Build a role distribution list from the current evolutionary assignments."""
        if self._evolution_coordinator is None:
            return self._role_distribution
        result: list[str] = []
        for agent_id in range(len(self._role_distribution)):
            role = self._evolution_coordinator.get_agent_role(agent_id)
            if role is not None:
                vibe = self._evolution_coordinator.map_role_to_vibe(role)
                result.append(vibe)
            else:
                # Assign via evolution and map
                vibe = self._evolution_coordinator.choose_vibe(agent_id)
                result.append(vibe)
        return result

    def _get_role_for_agent(self, agent_id: int) -> str:
        """Get role for an agent, using evolution if enabled."""
        if self._evolution_enabled and self._evolution_coordinator is not None:
            # Check if already assigned this episode
            assignment = self._evolution_coordinator.agent_assignments.get(agent_id)
            if assignment is not None:
                return self._evolution_coordinator.map_role_to_vibe(
                    self._evolution_coordinator.get_agent_role(agent_id)  # type: ignore[arg-type]
                )
            return self._evolution_coordinator.choose_vibe(agent_id)
        if agent_id < len(self._role_distribution):
            return self._role_distribution[agent_id]
        return "miner"

    def _record_evolution_episode(self, aligned_score: float) -> None:
        """Record episode results for evolutionary fitness tracking."""
        if self._evolution_coordinator is None:
            return
        # Normalize score: use aligned junction fraction (assume ~20 total junctions)
        normalized = min(1.0, aligned_score / 20.0)
        won = self._coordinator.is_winning

        # Record per-agent performance
        for agent_id in list(self._evolution_coordinator.agent_assignments):
            self._evolution_coordinator.record_agent_performance(agent_id, normalized, won)

        # Signal end of game (may trigger evolution)
        old_gen = self._evolution_coordinator.generation
        self._evolution_coordinator.end_game(won)
        new_gen = self._evolution_coordinator.generation

        # Log progress
        summary = self._evolution_coordinator.get_catalog_summary()
        print(
            f"[cogas:evolution] Episode {self._episode_count}: "
            f"aligned={aligned_score:.1f} norm={normalized:.2f} won={won} "
            f"gen={summary['generation']} roles={summary['num_roles']}",
            file=sys.stderr,
        )
        if new_gen > old_gen:
            role_strs = [f"{r['name']}(f={r['fitness']:.2f})" for r in summary["roles"]]
            print(
                f"[cogas:evolution] EVOLVED to generation {new_gen}. Roles: {role_strs}",
                file=sys.stderr,
            )
            # Persist best config after evolution
            if self._evolution_persist_path:
                self._save_evolution_state()

    def _save_evolution_state(self) -> None:
        """Persist the best evolutionary configuration to disk."""
        if self._evolution_coordinator is None or self._evolution_persist_path is None:
            return
        summary = self._evolution_coordinator.get_catalog_summary()
        state = {
            "generation": summary["generation"],
            "roles": summary["roles"],
            "best_role_distribution": self._get_evolved_role_distribution(),
        }
        try:
            self._evolution_persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._evolution_persist_path.write_text(json.dumps(state, indent=2))
            print(
                f"[cogas:evolution] Saved state to {self._evolution_persist_path}",
                file=sys.stderr,
            )
        except OSError as e:
            print(f"[cogas:evolution] Failed to save state: {e}", file=sys.stderr)

    def _load_evolution_state(self) -> None:
        """Load persisted evolutionary state and apply the best role distribution."""
        if self._evolution_coordinator is None or self._evolution_persist_path is None:
            return
        try:
            data = json.loads(self._evolution_persist_path.read_text())
            saved_gen = data.get("generation", 0)
            self._evolution_coordinator.generation = saved_gen
            # Apply saved role distribution as baseline
            saved_dist = data.get("best_role_distribution", [])
            if saved_dist and len(saved_dist) == len(self._role_distribution):
                self._role_distribution = saved_dist
                self._seed_evolution_from_cogas()
            print(
                f"[cogas:evolution] Loaded state from {self._evolution_persist_path} (generation={saved_gen})",
                file=sys.stderr,
            )
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"[cogas:evolution] Failed to load state: {e}", file=sys.stderr)

    # -- Agent policy -------------------------------------------------------

    def agent_policy(self, agent_id: int) -> StatefulAgentPolicy[CogasAgentState]:
        if agent_id not in self._agent_policies:
            role = self._get_role_for_agent(agent_id)

            # Register heart priority for roles that consume hearts
            if role in ("aligner", "scrambler", "defensive"):
                self._coordinator.register_heart_priority(agent_id, role)

            brain = CogasBrain(
                policy_env_info=self._policy_env_info,
                agent_id=agent_id,
                role=role,
                coordinator=self._coordinator,
                trace_enabled=self._trace_enabled,
                trace_level=self._trace_level,
                trace_agent=self._trace_agent,
                debug_logger=self._debug_logger,
            )

            self._agent_policies[agent_id] = StatefulAgentPolicy(
                brain,
                self._policy_env_info,
                agent_id=agent_id,
            )

        return self._agent_policies[agent_id]

    def reset(self, simulation: Any = None) -> None:
        """Reset policy state between episodes. Records evolution fitness."""
        # Record evolution data from the completed episode (if any)
        if self._evolution_enabled and self._episode_aligned_scores:
            # Use mean aligned junction count as fitness signal
            avg_aligned = sum(self._episode_aligned_scores) / len(self._episode_aligned_scores)
            self._record_evolution_episode(avg_aligned)
            self._episode_aligned_scores.clear()
            self._episode_count += 1

            # Reassign roles for next episode based on evolved distribution
            self._agent_policies.clear()

        # Reset coordinator state for fresh episode
        self._coordinator = Coordinator()

        # Reset debug logger
        if self._debug_logger is not None:
            self._debug_logger.reset_episode()

        super().reset(simulation)

    def step_batch(self, raw_observations: np.ndarray, raw_actions: np.ndarray) -> None:
        raw_actions[...] = self._noop_action_value
        num_agents = min(raw_observations.shape[0], self._policy_env_info.num_agents)
        active_agents = min(num_agents, len(self._role_distribution))
        for agent_id in range(active_agents):
            obs = self._raw_obs_to_agent_obs(agent_id, raw_observations[agent_id])
            action = self.agent_policy(agent_id).step(obs)
            action_index = self._action_name_to_index.get(action.name, 0)
            raw_actions[agent_id] = dtype_actions.type(action_index)

        # Debug: record junction status and flush tick
        if self._debug_logger is not None:
            self._record_debug_junction_status()
            self._debug_logger.flush_tick()

        # Track aligned junction score for evolution fitness
        if self._evolution_enabled:
            self._episode_aligned_scores.append(float(self._coordinator.cogs_junctions))

    def _raw_obs_to_agent_obs(self, agent_id: int, raw_obs: np.ndarray) -> AgentObservation:
        from mettagrid.simulator import ObservationToken

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

    def _record_debug_junction_status(self) -> None:
        """Aggregate junction counts from all agents' entity maps and record."""
        aligned = 0
        enemy = 0
        neutral = 0
        step = 0
        seen_positions: set[tuple[int, int]] = set()

        for ap in self._agent_policies.values():
            astate: CogasAgentState = ap._agent_state  # type: ignore[attr-defined]
            if astate is None:
                continue
            step = max(step, astate.step)
            for ent in astate.entity_map.find(type_contains="junction"):
                pos = ent.position
                if pos in seen_positions:
                    continue
                seen_positions.add(pos)
                alignment = ent.properties.get("alignment")
                if alignment == "cogs":
                    aligned += 1
                elif alignment == "clips":
                    enemy += 1
                else:
                    neutral += 1

        self._debug_logger.record_junction_status(  # type: ignore[union-attr]
            aligned=aligned,
            enemy=enemy,
            neutral=neutral,
            step=step,
        )
        # Score estimate: aligned junctions × steps remaining is a proxy
        # for junction.held
        self._debug_logger.record_score_estimate(  # type: ignore[union-attr]
            step=step,
            value=float(aligned),
        )
