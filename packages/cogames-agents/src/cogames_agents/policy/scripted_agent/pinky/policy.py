"""
Pinky Policy - main policy implementation.

AgentBrain coordinates per-agent state, services, and behavior.
PinkyPolicy is the multi-agent wrapper with URI-based vibe distribution.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from mettagrid.mettagrid_c import PackedCoordinate, dtype_actions
from mettagrid.policy.policy import MultiAgentPolicy, StatefulAgentPolicy, StatefulPolicyImpl
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Action, ObservationToken
from mettagrid.simulator.interface import AgentObservation

from .behaviors import (
    AlignerBehavior,
    MinerBehavior,
    RoleBehavior,
    ScoutBehavior,
    ScramblerBehavior,
    Services,
    change_vibe_action,
)
from .services import MapTracker, Navigator, SafetyManager
from .state import AgentState
from .types import DEBUG, VIBE_TO_ROLE, DebugInfo, Role

# The "gear" vibe triggers changing to role vibe
GEAR_VIBE = "gear"


class PinkyAgentBrain(StatefulPolicyImpl[AgentState]):
    """Per-agent coordinator that owns state and delegates to behavior/services."""

    # Role behaviors mapping
    ROLE_BEHAVIORS: dict[Role, type[RoleBehavior]] = {
        Role.MINER: MinerBehavior,
        Role.SCOUT: ScoutBehavior,
        Role.ALIGNER: AlignerBehavior,
        Role.SCRAMBLER: ScramblerBehavior,
    }

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        agent_id: int,
        initial_vibe: Optional[str] = None,
        debug: bool = False,
        lazy: bool = False,
    ):
        self._agent_id = agent_id
        self._policy_env_info = policy_env_info
        self._initial_vibe = initial_vibe or "miner"
        self._debug = debug
        self._lazy = lazy  # If True, don't auto-activate on step 1; wait for gear vibe

        # Track previous debug output to avoid duplicate prints
        self._prev_debug_output: Optional[str] = None

        # Determine initial role from vibe
        self._role = VIBE_TO_ROLE.get(self._initial_vibe, Role.MINER)

        # Create services
        self._navigator = Navigator(policy_env_info)
        self._map_tracker = MapTracker(policy_env_info)
        self._safety = SafetyManager()

        # Create behavior for this role
        behavior_class = self.ROLE_BEHAVIORS.get(self._role, MinerBehavior)
        self._behavior: RoleBehavior = behavior_class()

        # Action lookup
        self._action_names = policy_env_info.action_names

    def initial_agent_state(self) -> AgentState:
        """Create initial state for this agent."""
        return AgentState(
            agent_id=self._agent_id,
            role=self._role,
            vibe=self._initial_vibe,
        )

    def step_with_state(self, obs: AgentObservation, state: AgentState) -> tuple[Action, AgentState]:
        """Process observation and return action with updated state.

        Vibe behavior:
        - Step 1 with default vibe → change to assigned role vibe (auto-activate, unless lazy=True)
        - "gear" vibe → change to assigned role vibe
        - Role vibe (miner/scout/aligner/scrambler) → execute role behavior
        - Other vibes (heart, etc.) → noop
        """
        state.step += 1

        # Store observation for behavior use
        state.last_obs = obs

        # Update last action executed from observation (for position tracking)
        state.nav.last_action_executed = self._get_last_action_from_obs(obs)

        # Update position based on last action
        self._navigator.update_position(state)

        # Reset per-step flags
        state.nav.using_object_this_step = False

        # Update map knowledge from observation (this also reads current vibe)
        self._map_tracker.update(state, obs)

        # Create services bundle (needed for vibe change action)
        services = Services(
            navigator=self._navigator,
            map_tracker=self._map_tracker,
            safety=self._safety,
            action_names=self._action_names,
        )

        # Step 1 with default vibe OR "gear" vibe → change to assigned role vibe
        # This must happen BEFORE the "noop if not role vibe" check!
        # (but only if agent has an assigned role, not if they're meant to stay default)
        # In lazy mode, skip step 1 auto-activation; only activate on gear vibe
        if self._initial_vibe != "default":
            should_activate = state.vibe == GEAR_VIBE or (
                not self._lazy and state.step == 1 and state.vibe == "default"
            )
            if should_activate:
                role_vibe = self._initial_vibe  # The assigned role (miner/scout/etc.)
                action = change_vibe_action(role_vibe, services)
                state.nav.last_action = action
                state.debug_info = DebugInfo(
                    mode="activate",
                    goal=f"change_vibe_to_{role_vibe}",
                    target_object="vibe",
                )
                if self._debug:
                    self._print_debug_if_changed(state, action)
                elif DEBUG and state.step <= 20:
                    print(
                        f"[A{state.agent_id}] Step {state.step}: vibe={state.vibe}, changing to {role_vibe}, "
                        f"pos={state.pos}, hp={state.hp}"
                    )
                return action, state

        # Check if vibe changed and update role/behavior accordingly
        new_role = VIBE_TO_ROLE.get(state.vibe)
        if new_role is not None and new_role != state.role:
            state.role = new_role
            behavior_class = self.ROLE_BEHAVIORS.get(new_role, MinerBehavior)
            self._behavior = behavior_class()
            if DEBUG:
                print(f"[A{state.agent_id}] Vibe changed to {state.vibe}, switching to role {new_role.value}")

        # If vibe is "default" or not a role vibe, do nothing (noop)
        if state.vibe not in VIBE_TO_ROLE:
            action = Action(name="noop")
            state.nav.last_action = action
            if DEBUG and state.step <= 20:
                print(
                    f"[A{state.agent_id}] Step {state.step}: vibe={state.vibe} (inactive), "
                    f"pos={state.pos}, hp={state.hp}, action=noop"
                )
            return action, state

        # Role vibe → execute role behavior
        if state.vibe in VIBE_TO_ROLE:
            # Update role/behavior if vibe changed to a different role
            new_role = VIBE_TO_ROLE[state.vibe]
            if new_role != state.role:
                state.role = new_role
                behavior_class = self.ROLE_BEHAVIORS.get(new_role, MinerBehavior)
                self._behavior = behavior_class()
                if DEBUG:
                    print(f"[A{state.agent_id}] Role changed to {new_role.value}")

            # Execute role behavior
            action = self._behavior.act(state, services)
            state.nav.last_action = action

            if self._debug:
                self._print_debug_if_changed(state, action)
            elif DEBUG and state.step <= 100:
                print(
                    f"[A{state.agent_id}] Step {state.step}: role={state.role.value}, "
                    f"pos={state.pos}, hp={state.hp}, cargo={state.total_cargo}, action={action.name}"
                )
            return action, state

        # Other vibes (heart, etc.) → noop
        action = Action(name="noop")
        state.nav.last_action = action
        state.debug_info = DebugInfo(mode="inactive", goal=f"vibe={state.vibe}")
        if self._debug:
            self._print_debug_if_changed(state, action)
        elif DEBUG and state.step <= 20:
            print(
                f"[A{state.agent_id}] Step {state.step}: vibe={state.vibe} (inactive), "
                f"pos={state.pos}, hp={state.hp}, action=noop"
            )
        return action, state

    def _get_last_action_from_obs(self, obs: AgentObservation) -> Optional[str]:
        """Extract last executed action from observation.

        Global observation tokens (like last_action) can be at any location,
        so we search all tokens for the feature name.
        """
        for tok in obs.tokens:
            if tok.feature.name == "last_action":
                # Convert action ID to name
                action_id = tok.value
                if 0 <= action_id < len(self._action_names):
                    return self._action_names[action_id]
        return None

    def _print_debug_if_changed(self, state: AgentState, action: Action) -> None:
        """Print debug info only if it changed from the previous step."""
        debug_output = state.debug_info.format(state.role.value, action.name)
        if debug_output != self._prev_debug_output:
            # Format position as [col,row]
            pos_str = f"[{state.pos[1]},{state.pos[0]}]"
            dest = state.debug_info.target_pos
            if dest:
                dest_str = f"[{dest[1]},{dest[0]}]"
                dist = abs(state.pos[0] - dest[0]) + abs(state.pos[1] - dest[1])
                target_info = f"({state.debug_info.target_object},dist={dist})"
            else:
                dest_str = "[-,-]"
                target_info = f"({state.debug_info.target_object or '-'})"
            role = state.role.value
            mode = state.debug_info.mode

            # Build gear string - show which gear the agent has
            gear_list = []
            if state.miner_gear:
                gear_list.append("miner")
            if state.scout_gear:
                gear_list.append("scout")
            if state.aligner_gear:
                gear_list.append("aligner")
            if state.scrambler_gear:
                gear_list.append("scrambler")
            gear_str = ",".join(gear_list) if gear_list else "-"

            print(
                f"[pinky][Step {state.step}][A{state.agent_id}] [{role}] [g:{gear_str}] [h:{state.heart}] [{mode}] "
                f"{pos_str}->{dest_str} {target_info} : {action.name}"
            )
            self._prev_debug_output = debug_output


class PinkyPolicy(MultiAgentPolicy):
    """Multi-agent policy with URI-based vibe distribution.

    URI parameters specify how many agents get each role:
    - ?miner=1 → agent 0 is miner, rest are default (noop)
    - ?miner=2&scout=1 → agents 0,1 are miners, agent 2 is scout, rest are default
    - Agents beyond the specified count stay neutral (default vibe, noop)
    """

    short_names = ["pinky"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        device: str = "cpu",
        # URI parameters for vibe counts (default: 4 miners, 2 aligners, 4 scramblers)
        miner: int = 4,
        scout: int = 0,
        aligner: int = 2,
        scrambler: int = 4,
        # Debug flag - print structured intent info each step
        debug: int = 0,
        # Lazy mode - don't auto-activate on step 1; wait for gear vibe
        lazy: int = 0,
        # Accept any extra kwargs to be flexible
        **kwargs: object,
    ):
        super().__init__(policy_env_info, device=device)
        self._feature_by_id = {feature.id: feature for feature in policy_env_info.obs_features}
        self._action_name_to_index = {name: idx for idx, name in enumerate(policy_env_info.action_names)}
        self._noop_action_value = dtype_actions.type(self._action_name_to_index.get("noop", 0))

        # Debug mode from URI param (?debug=1)
        self._debug = bool(debug)
        # Lazy mode from URI param (?lazy=1) - wait for gear vibe instead of auto-activating
        self._lazy = bool(lazy)

        # Build vibe distribution from counts - agents beyond this list stay default
        self._vibe_distribution: list[str] = []
        self._vibe_distribution.extend(["miner"] * miner)
        self._vibe_distribution.extend(["scout"] * scout)
        self._vibe_distribution.extend(["aligner"] * aligner)
        self._vibe_distribution.extend(["scrambler"] * scrambler)

        if DEBUG or self._debug:
            lazy_str = " (lazy mode - wait for gear)" if self._lazy else ""
            print(f"[PINKY] Vibe distribution: {self._vibe_distribution}{lazy_str} (agents beyond this stay default)")
            if self._debug:
                print("[PINKY] Debug mode enabled - will print: role:mode:goal:target:action")

        # Cache for agent policies
        self._agent_policies: dict[int, StatefulAgentPolicy[AgentState]] = {}

    def agent_policy(self, agent_id: int) -> StatefulAgentPolicy[AgentState]:
        """Get or create policy for an agent."""
        if agent_id not in self._agent_policies:
            # Assign vibe from distribution, or "default" if agent_id exceeds distribution
            if agent_id < len(self._vibe_distribution):
                initial_vibe = self._vibe_distribution[agent_id]
            else:
                initial_vibe = "default"  # No role assigned, will noop

            if DEBUG or self._debug:
                print(f"[PINKY] Agent {agent_id} assigned vibe: {initial_vibe}")

            # Create brain for this agent
            brain = PinkyAgentBrain(
                policy_env_info=self._policy_env_info,
                agent_id=agent_id,
                initial_vibe=initial_vibe,
                debug=self._debug,
                lazy=self._lazy,
            )

            # Wrap in StatefulAgentPolicy
            self._agent_policies[agent_id] = StatefulAgentPolicy(
                brain,
                self._policy_env_info,
                agent_id=agent_id,
            )

        return self._agent_policies[agent_id]

    def step_batch(self, raw_observations: np.ndarray, raw_actions: np.ndarray) -> None:
        raw_actions[...] = self._noop_action_value
        num_agents = min(raw_observations.shape[0], self._policy_env_info.num_agents)
        active_agents = min(num_agents, len(self._vibe_distribution))
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
            location = PackedCoordinate.unpack(location_packed) or (0, 0)
            value = int(token[2])
            tokens.append(
                ObservationToken(
                    feature=feature,
                    location=location,
                    value=value,
                    raw_token=(location_packed, feature_id, value),
                )
            )
        return AgentObservation(agent_id=agent_id, tokens=tokens)
