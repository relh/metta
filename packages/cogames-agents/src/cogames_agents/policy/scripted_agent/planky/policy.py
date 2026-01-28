"""
Planky Policy — goal-tree scripted agent.

PlankyBrain coordinates per-agent state and goal evaluation.
PlankyPolicy is the multi-agent wrapper with URI-based role distribution.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from mettagrid.mettagrid_c import dtype_actions
from mettagrid.policy.policy import MultiAgentPolicy, StatefulAgentPolicy, StatefulPolicyImpl
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Action, ObservationToken
from mettagrid.simulator.interface import AgentObservation

from .context import PlankyContext
from .entity_map import EntityMap
from .goal import Goal, evaluate_goals
from .goals.aligner import AlignJunctionGoal, GetAlignerGearGoal
from .goals.gear import GetGearGoal
from .goals.miner import DepositCargoGoal, MineResourceGoal, PickResourceGoal
from .goals.scout import ExploreGoal, GetScoutGearGoal
from .goals.scrambler import GetScramblerGearGoal, ScrambleJunctionGoal
from .goals.shared import GetHeartsGoal
from .goals.stem import SelectRoleGoal
from .goals.survive import SurviveGoal
from .navigator import Navigator
from .obs_parser import ObsParser
from .trace import TraceLog

# Role vibes that map to roles
VIBE_TO_ROLE = {"miner", "scout", "aligner", "scrambler"}

# Default spawn position (center of 200x200 grid)
SPAWN_POS = (100, 100)


def _make_goal_list(role: str) -> list[Goal]:
    """Create goal list for a role."""
    if role == "miner":
        return [
            SurviveGoal(hp_threshold=15),
            GetGearGoal("miner_gear", "miner_station", "GetMinerGear"),
            PickResourceGoal(),
            DepositCargoGoal(),
            MineResourceGoal(),
        ]
    elif role == "scout":
        return [
            SurviveGoal(hp_threshold=50),
            GetScoutGearGoal(),
            ExploreGoal(),
        ]
    elif role == "aligner":
        return [
            SurviveGoal(hp_threshold=50),
            GetAlignerGearGoal(),
            GetHeartsGoal(),
            AlignJunctionGoal(),
        ]
    elif role == "scrambler":
        return [
            SurviveGoal(hp_threshold=30),
            GetScramblerGearGoal(),
            GetHeartsGoal(),
            ScrambleJunctionGoal(),
        ]
    elif role == "stem":
        role_lists = {
            "miner": _make_goal_list("miner"),
            "scout": _make_goal_list("scout"),
            "aligner": _make_goal_list("aligner"),
            "scrambler": _make_goal_list("scrambler"),
        }
        return [
            SurviveGoal(hp_threshold=20),
            SelectRoleGoal(role_lists),
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

    def initial_agent_state(self) -> PlankyAgentState:
        goals = _make_goal_list(self._role)
        return PlankyAgentState(
            agent_id=self._agent_id,
            role=self._role,
            goals=goals,
        )

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

        # Handle vibe activation — same pattern as Pinky
        # Step 1 with default vibe → change to assigned role vibe
        if agent_state.step == 1 and state.vibe == "default" and self._role in VIBE_TO_ROLE:
            return Action(name=f"change_vibe_{self._role}"), agent_state

        # "gear" vibe → change back to assigned role vibe
        if state.vibe == "gear" and self._role in VIBE_TO_ROLE:
            return Action(name=f"change_vibe_{self._role}"), agent_state

        # If vibe is not our role (inactive), noop
        if self._role in VIBE_TO_ROLE and state.vibe != self._role:
            return Action(name="noop"), agent_state

        # Check if stem agent has selected a new role
        if "goal_list" in agent_state.blackboard:
            agent_state.goals = agent_state.blackboard.pop("goal_list")
            selected = agent_state.blackboard.get("selected_role", "unknown")
            agent_state.role = selected
            if self._should_trace(agent_state):
                print(f"[planky][t={agent_state.step} a={self._agent_id}] stem→{selected}")

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

        # If we're stuck (many failed moves), force exploration to discover terrain
        fail_count = agent_state.blackboard.get("_move_fail_count", 0)
        if fail_count >= 3:
            action = agent_state.navigator.explore(
                state.position,
                agent_state.entity_map,
                direction_bias=["north", "east", "south", "west"][self._agent_id % 4],
            )
            if trace:
                trace.active_goal_chain = f"ForceExplore(stuck={fail_count})"
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

        # Track action for failed-move detection
        agent_state.blackboard["_last_action"] = action.name

        return action, agent_state

    def _should_trace(self, agent_state: PlankyAgentState) -> bool:
        if not self._trace_enabled:
            return False
        if self._trace_agent >= 0 and self._agent_id != self._trace_agent:
            return False
        return True


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
        # Role counts
        miner: int = 4,
        scout: int = 0,
        aligner: int = 2,
        scrambler: int = 4,
        stem: int = 0,
        # Tracing
        trace: int = 0,
        trace_level: int = 1,
        trace_agent: int = -1,
        # Accept any extra kwargs
        **kwargs: object,
    ) -> None:
        super().__init__(policy_env_info, device=device)
        self._feature_by_id = {f.id: f for f in policy_env_info.obs_features}
        self._action_name_to_index = {name: idx for idx, name in enumerate(policy_env_info.action_names)}
        self._noop_action_value = dtype_actions.type(self._action_name_to_index.get("noop", 0))

        # Tracing
        self._trace_enabled = bool(trace)
        self._trace_level = trace_level
        self._trace_agent = trace_agent

        # Build role distribution
        self._role_distribution: list[str] = []
        self._role_distribution.extend(["miner"] * miner)
        self._role_distribution.extend(["scout"] * scout)
        self._role_distribution.extend(["aligner"] * aligner)
        self._role_distribution.extend(["scrambler"] * scrambler)
        self._role_distribution.extend(["stem"] * stem)

        if self._trace_enabled:
            print(f"[planky] Role distribution: {self._role_distribution}")

        self._agent_policies: dict[int, StatefulAgentPolicy[PlankyAgentState]] = {}

    def agent_policy(self, agent_id: int) -> StatefulAgentPolicy[PlankyAgentState]:
        if agent_id not in self._agent_policies:
            role = self._role_distribution[agent_id] if agent_id < len(self._role_distribution) else "default"

            brain = PlankyBrain(
                policy_env_info=self._policy_env_info,
                agent_id=agent_id,
                role=role,
                trace_enabled=self._trace_enabled,
                trace_level=self._trace_level,
                trace_agent=self._trace_agent,
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
        active_agents = min(num_agents, len(self._role_distribution))
        for agent_id in range(active_agents):
            obs = self._raw_obs_to_agent_obs(agent_id, raw_observations[agent_id])
            action = self.agent_policy(agent_id).step(obs)
            action_index = self._action_name_to_index.get(action.name, 0)
            raw_actions[agent_id] = dtype_actions.type(action_index)

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
