from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from mettagrid_sdk.games.cogsguard import (
    COGSGUARD_BOOTSTRAP_HUB_OFFSETS,
    COGSGUARD_GEAR_COSTS,
    COGSGUARD_HUB_ALIGN_DISTANCE,
    COGSGUARD_JUNCTION_ALIGN_DISTANCE,
    COGSGUARD_JUNCTION_AOE_RANGE,
    COGSGUARD_ROLE_HP_THRESHOLDS,
    CogsguardEventExtractor,
    CogsguardPromptAdapter,
    CogsguardStateAdapter,
)
from mettagrid_sdk.runtime.observation import ObservationEnvelope
from mettagrid_sdk.sdk import MacroDirective, MettagridState, SemanticEntity

from cog_cyborg.memory import MemoryStore
from mettagrid.policy.policy import AgentPolicy, MultiAgentPolicy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Action
from mettagrid.simulator.interface import AgentObservation

_ELEMENTS = ("carbon", "oxygen", "germanium", "silicon")
_MOVE_DELTAS = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
}
_STATION_OFFSETS = {
    "aligner": (-3, 4),
    "scrambler": (-1, 4),
    "miner": (1, 4),
    "scout": (3, 4),
}
_ALIGNER_EXPLORE_OFFSETS = (
    (0, -22),
    (16, -16),
    (22, 0),
    (16, 16),
    (0, 22),
    (-16, 16),
    (-22, 0),
    (-16, -16),
)
_MINER_EXPLORE_OFFSETS = ((-28, -28), (28, -28), (-28, 28), (28, 28))
_SCRAMBLER_EXPLORE_OFFSETS = ((36, -36), (36, 36), (-36, 36), (-36, -36))
_HP_THRESHOLDS = COGSGUARD_ROLE_HP_THRESHOLDS
_TEMP_BLOCK_STEPS = 10
_HUB_ALIGN_DISTANCE = COGSGUARD_HUB_ALIGN_DISTANCE
_JUNCTION_ALIGN_DISTANCE = COGSGUARD_JUNCTION_ALIGN_DISTANCE
_JUNCTION_AOE_RANGE = COGSGUARD_JUNCTION_AOE_RANGE
_RETREAT_MARGIN = 20
_EMERGENCY_RESOURCE_LOW = 3
_DEFAULT_BOUND_MARGIN = 8
_ALIGNER_GEAR_DELAY_STEPS = 0
_HEART_BATCH_TARGETS = {"aligner": 4, "scrambler": 2}
_TARGET_CLAIM_STEPS = 30
_CLAIMED_TARGET_PENALTY = 12.0
_TARGET_SWITCH_THRESHOLD = 3.0
_SHARED_JUNCTION_MEMORY_STEPS = 400
_EXTRACTOR_MEMORY_STEPS = 600
_OSCILLATION_HISTORY_STEPS = 6
_OSCILLATION_UNSTICK_STEPS = 4
_MINING_ALIGNER_MIN_RESOURCE = 20
_ALIGNER_PRIORITY = (4, 5, 6, 7, 3)
_SCRAMBLER_PRIORITY = (7, 6)
_GEAR_COSTS = COGSGUARD_GEAR_COSTS
_HUB_OFFSETS = COGSGUARD_BOOTSTRAP_HUB_OFFSETS
_COGSGUARD_PROMPT_ADAPTER = CogsguardPromptAdapter()
_STATION_TARGETS_BY_AGENT = {
    "aligner": {
        0: (-3, 7),
        1: (-3, 6),
        2: (0, 4),
        3: (-1, 4),
        4: (-5, 4),
        5: (-6, 4),
        6: (-3, 2),
        7: (-3, 1),
    },
    "scrambler": {
        0: (-1, 7),
        1: (-1, 6),
        2: (2, 4),
        3: (1, 4),
        4: (-3, 4),
        5: (-4, 4),
        6: (-1, 2),
        7: (-1, 1),
    },
    "miner": {
        0: (1, 7),
        1: (1, 6),
        2: (4, 4),
        3: (3, 4),
        4: (-1, 4),
        5: (-2, 4),
        6: (1, 2),
        7: (1, 1),
    },
}


@dataclass(slots=True)
class KnownEntity:
    entity_type: str
    global_x: int
    global_y: int
    labels: tuple[str, ...]
    team: str | None
    owner: str | None
    last_seen_step: int
    attributes: dict[str, str | int | float | bool]

    @property
    def position(self) -> tuple[int, int]:
        return (self.global_x, self.global_y)


@dataclass(slots=True)
class MoveAttempt:
    direction: str
    stationary_use: bool


@dataclass(slots=True)
class PressureMetrics:
    frontier_neutral_junctions: int
    best_frontier_coverage: int
    best_enemy_scramble_block: int


@dataclass(slots=True)
class NavigationObservation:
    position: tuple[int, int]
    subtask: str
    target_kind: str
    target_position: tuple[int, int] | None


class SharedWorldModel:
    def __init__(self) -> None:
        self._entities: dict[str, KnownEntity] = {}

    def reset(self) -> None:
        self._entities.clear()

    def update(self, state: MettagridState) -> None:
        step = state.step or 0
        for entity in state.visible_entities:
            if entity.entity_type == "agent":
                continue
            global_x = _attr_int(entity, "global_x", entity.position.x)
            global_y = _attr_int(entity, "global_y", entity.position.y)
            key = f"{entity.entity_type}@{global_x},{global_y}"
            self._entities[key] = KnownEntity(
                entity_type=entity.entity_type,
                global_x=global_x,
                global_y=global_y,
                labels=tuple(entity.labels),
                team=_attr_str(entity, "team"),
                owner=_attr_str(entity, "owner"),
                last_seen_step=step,
                attributes=dict(entity.attributes),
            )

    def prune_missing_extractors(
        self,
        *,
        current_position: tuple[int, int],
        visible_entities: list[SemanticEntity],
        obs_width: int,
        obs_height: int,
    ) -> None:
        half_width = obs_width // 2
        half_height = obs_height // 2
        min_x = current_position[0] - half_width
        max_x = current_position[0] + half_width
        min_y = current_position[1] - half_height
        max_y = current_position[1] + half_height
        visible_extractors = {
            (
                _attr_int(entity, "global_x", entity.position.x),
                _attr_int(entity, "global_y", entity.position.y),
            )
            for entity in visible_entities
            if entity.entity_type.endswith("_extractor")
        }
        stale_keys = [
            key
            for key, entity in self._entities.items()
            if entity.entity_type.endswith("_extractor")
            and min_x <= entity.global_x <= max_x
            and min_y <= entity.global_y <= max_y
            and entity.position not in visible_extractors
        ]
        for key in stale_keys:
            self._entities.pop(key, None)

    def entities(
        self,
        *,
        entity_type: str | None = None,
        predicate: Callable[[KnownEntity], bool] | None = None,
    ) -> list[KnownEntity]:
        result = []
        for entity in self._entities.values():
            if entity_type is not None and entity.entity_type != entity_type:
                continue
            if predicate is not None and not predicate(entity):
                continue
            result.append(entity)
        return result

    def nearest(
        self,
        *,
        position: tuple[int, int],
        entity_type: str | None = None,
        predicate: Callable[[KnownEntity], bool] | None = None,
    ) -> KnownEntity | None:
        candidates = self.entities(entity_type=entity_type, predicate=predicate)
        if not candidates:
            return None
        return min(candidates, key=lambda entity: (_manhattan(position, entity.position), entity.position))

    def occupied_cells(self, *, exclude: set[tuple[int, int]] | None = None) -> set[tuple[int, int]]:
        excluded = set() if exclude is None else exclude
        return {
            entity.position
            for entity in self._entities.values()
            if entity.position not in excluded and entity.entity_type != "agent"
        }

    def is_occupied(self, position: tuple[int, int]) -> bool:
        return position in self.occupied_cells()

    def entity_at(
        self,
        *,
        position: tuple[int, int],
        entity_type: str | None = None,
        predicate: Callable[[KnownEntity], bool] | None = None,
    ) -> KnownEntity | None:
        for entity in self._entities.values():
            if entity.position != position:
                continue
            if entity_type is not None and entity.entity_type != entity_type:
                continue
            if predicate is not None and not predicate(entity):
                continue
            return entity
        return None

    def forget_nearest(
        self,
        *,
        position: tuple[int, int],
        entity_type: str,
        max_distance: int,
    ) -> bool:
        nearest = self.nearest(position=position, entity_type=entity_type)
        if nearest is None or _manhattan(position, nearest.position) > max_distance:
            return False
        key = f"{nearest.entity_type}@{nearest.global_x},{nearest.global_y}"
        self._entities.pop(key, None)
        return True


class SemanticCogAgentPolicy(AgentPolicy):
    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        *,
        agent_id: int,
        world_model: SharedWorldModel,
        shared_claims: dict[tuple[int, int], tuple[int, int]],
        shared_junctions: dict[tuple[int, int], tuple[str | None, int]],
    ) -> None:
        super().__init__(policy_env_info)
        self._agent_id = agent_id
        self._world_model = world_model
        self._shared_claims = shared_claims
        self._shared_junctions = shared_junctions
        self._state_adapter = CogsguardStateAdapter()
        self._event_extractor = CogsguardEventExtractor()
        self._memory = MemoryStore()
        self._previous_state: MettagridState | None = None
        self._last_global_pos: tuple[int, int] | None = None
        self._last_attempt: MoveAttempt | None = None
        self._temp_blocks: dict[tuple[int, int], int] = {}
        self._step_index = 0
        self._action_names = set(policy_env_info.action_names)
        self._vibe_actions = set(policy_env_info.vibe_action_names)
        self._fallback_action = "noop" if "noop" in self._action_names else policy_env_info.action_names[0]
        self._explore_index = 0
        self._default_resource_bias = _ELEMENTS[agent_id % len(_ELEMENTS)]
        self._resource_bias = self._default_resource_bias
        self._last_inventory_signature: tuple[tuple[str, int], ...] | None = None
        self._stalled_steps = 0
        self._oscillation_steps = 0
        self._recent_navigation: deque[NavigationObservation] = deque(maxlen=_OSCILLATION_HISTORY_STEPS)
        self._current_target_position: tuple[int, int] | None = None
        self._current_target_kind: str | None = None
        self._claimed_target: tuple[int, int] | None = None
        self._sticky_target_position: tuple[int, int] | None = None
        self._sticky_target_kind: str | None = None
        self._current_directive = MacroDirective()

    def step(self, obs: AgentObservation) -> Action:
        self._step_index += 1
        self._current_target_position = None
        self._current_target_kind = None
        state = self._state_adapter.build_state(
            ObservationEnvelope(raw_observation=obs, policy_env_info=self.policy_env_info, step=self._step_index)
        )
        state.recent_events = self._event_extractor.extract_events(self._previous_state, state)
        self._memory.append_semantic_events(
            state.recent_events,
            game=state.game,
            role_context=state.self_state.role,
            tags=[state.self_state.role or "unknown"],
        )

        self._world_model.update(state)
        self._update_shared_junctions(state)
        self._world_model.prune_missing_extractors(
            current_position=_absolute_position(state),
            visible_entities=state.visible_entities,
            obs_width=self.policy_env_info.obs_width,
            obs_height=self.policy_env_info.obs_height,
        )
        current_pos = _absolute_position(state)
        self._update_temp_blocks(current_pos)
        self._update_stall_counter(state, current_pos)

        directive = self._sanitize_macro_directive(self._macro_directive(state))
        self._current_directive = directive
        self._resource_bias = (
            self._default_resource_bias if directive.resource_bias is None else directive.resource_bias
        )
        role = directive.role or self._desired_role(state)
        action, summary = self._choose_action(state, role)
        self._record_navigation_observation(current_pos, summary)
        macro_snapshot = self._macro_snapshot(state, role)
        self._infos = {
            "role": role,
            "subtask": summary,
            "summary": summary,
            "oscillation_steps": self._oscillation_steps,
            "phase": _phase_name(state, role),
            "heart": int(state.self_state.inventory.get("heart", 0)),
            "heart_batch_target": _heart_batch_target(state, role),
            "target_kind": self._current_target_kind or "",
            "target_position": (
                "" if self._current_target_position is None else _format_position(self._current_target_position)
            ),
            "directive_role": directive.role or "",
            "directive_resource_bias": directive.resource_bias or "",
            "directive_objective": directive.objective or "",
            "directive_note": directive.note,
            "directive_target_entity_id": directive.target_entity_id or "",
            "directive_target_region": directive.target_region or "",
            **macro_snapshot,
        }
        self._previous_state = state
        self._last_global_pos = current_pos
        self._last_inventory_signature = _inventory_signature(state)
        return action

    def reset(self, simulation=None) -> None:
        self._memory = MemoryStore()
        self._previous_state = None
        self._world_model.reset()
        self._last_global_pos = None
        self._last_attempt = None
        self._temp_blocks.clear()
        self._step_index = 0
        self._explore_index = 0
        self._resource_bias = self._default_resource_bias
        self._last_inventory_signature = None
        self._stalled_steps = 0
        self._oscillation_steps = 0
        self._recent_navigation.clear()
        self._clear_target_claim()
        self._clear_sticky_target()
        self._current_directive = MacroDirective()
        self._infos = {}

    def _macro_directive(self, state: MettagridState) -> MacroDirective:
        del state
        return MacroDirective()

    def render_skill_library(self) -> str:
        return _COGSGUARD_PROMPT_ADAPTER.render_skill_library()

    def _sanitize_macro_directive(self, directive: MacroDirective) -> MacroDirective:
        role = directive.role if directive.role in {"miner", "aligner", "scrambler", "scout"} else None
        resource_bias = directive.resource_bias if directive.resource_bias in _ELEMENTS else None
        note = directive.note.strip()
        objective = directive.objective.strip() if directive.objective is not None else None
        target_entity_id = directive.target_entity_id.strip() if directive.target_entity_id is not None else None
        target_region = directive.target_region.strip() if directive.target_region is not None else None
        return MacroDirective(
            role=role,
            target_entity_id=target_entity_id or None,
            target_region=target_region or None,
            resource_bias=resource_bias,
            objective=objective or None,
            note=note,
            metadata=dict(directive.metadata),
        )

    def _desired_role(self, state: MettagridState) -> str:
        aligner_budget, scrambler_budget = self._pressure_budgets(state)
        scrambler_ids = set(_SCRAMBLER_PRIORITY[:scrambler_budget])
        aligner_ids = []
        for agent_id in _ALIGNER_PRIORITY:
            if agent_id in scrambler_ids:
                continue
            aligner_ids.append(agent_id)
            if len(aligner_ids) == aligner_budget:
                break
        if self._agent_id in scrambler_ids:
            return "scrambler"
        if self._agent_id in aligner_ids:
            return "aligner"
        return "miner"

    def _choose_action(self, state: MettagridState, role: str) -> tuple[Action, str]:
        if role not in {"aligner", "miner"}:
            self._clear_target_claim()
            self._clear_sticky_target()
        elif role == "aligner" and self._sticky_target_kind not in {None, "junction"}:
            self._clear_sticky_target()
        elif role == "miner" and (
            self._sticky_target_kind is not None and not self._sticky_target_kind.endswith("_extractor")
        ):
            self._clear_sticky_target()
        safe_target = self._nearest_hub(state)
        safe_distance = 0 if safe_target is None else _manhattan(_absolute_position(state), safe_target.position)
        if self._should_retreat(state, role, safe_target):
            self._clear_target_claim()
            self._clear_sticky_target()
            if safe_target is not None and safe_distance > 2:
                return self._move_to_known(state, safe_target, summary="retreat_to_hub")
            if _has_role_gear(state, role):
                return self._hold(summary="retreat_hold", vibe="change_vibe_default")

        if self._oscillation_steps >= _OSCILLATION_UNSTICK_STEPS:
            return self._unstick_action(state, role)

        if self._stalled_steps >= 12:
            return self._unstick_action(state, role)

        if role != "miner" and _needs_emergency_mining(state):
            return self._miner_action(state, summary_prefix="emergency_")

        if role == "aligner" and not _has_role_gear(state, role):
            if (state.step or self._step_index) < _ALIGNER_GEAR_DELAY_STEPS:
                self._clear_target_claim()
                self._clear_sticky_target()
                return self._miner_action(state, summary_prefix="delay_gear_")

        if not _has_role_gear(state, role):
            self._clear_target_claim()
            self._clear_sticky_target()
            if not _team_can_afford_gear(state, role):
                return self._miner_action(state, summary_prefix=f"fund_{role}_gear_")
            return self._acquire_role_gear(state, role)

        if role == "miner":
            return self._miner_action(state)
        if role == "aligner":
            return self._aligner_action(state)
        if role == "scrambler":
            return self._scrambler_action(state)
        return self._explore_action(state, role=role, summary="explore")

    def _acquire_role_gear(self, state: MettagridState, role: str) -> tuple[Action, str]:
        station_type = f"{role}_station"
        current_pos = _absolute_position(state)
        station = self._world_model.nearest(position=current_pos, entity_type=station_type)
        if station is not None:
            return self._move_to_known(state, station, summary=f"get_{role}_gear", vibe="change_vibe_gear")

        target = _spawn_relative_station_target(self._agent_id, role)
        if target is None:
            hub = self._nearest_hub(state)
            if hub is None:
                return self._explore_action(state, role=role, summary=f"find_{role}_station")
            dx, dy = _STATION_OFFSETS[role]
            target = (hub.global_x + dx, hub.global_y + dy)
        return self._move_to_position(state, target, summary=f"search_{role}_station", vibe="change_vibe_gear")

    def _miner_action(self, state: MettagridState, summary_prefix: str = "") -> tuple[Action, str]:
        if self._should_deposit_resources(state):
            depot = self._nearest_friendly_depot(state)
            if depot is not None:
                return self._move_to_known(
                    state,
                    depot,
                    summary=f"{summary_prefix}deposit_resources",
                    vibe="change_vibe_miner",
                )

        extractor = self._preferred_miner_extractor(state)
        if extractor is not None:
            self._set_sticky_target(extractor.position, extractor.entity_type)
            return self._move_to_known(
                state,
                extractor,
                summary=f"{summary_prefix}mine_{extractor.entity_type.removesuffix('_extractor')}",
                vibe="change_vibe_miner",
            )

        self._clear_sticky_target()
        return self._explore_action(state, role="miner", summary=f"{summary_prefix}find_extractors")

    def _aligner_action(self, state: MettagridState) -> tuple[Action, str]:
        hearts = int(state.self_state.inventory.get("heart", 0))
        hub = self._nearest_hub(state)
        if hearts <= 0:
            self._clear_target_claim()
            self._clear_sticky_target()
            if not _team_can_refill_hearts(state):
                return self._miner_action(state, summary_prefix="rebuild_hearts_")
            if hub is not None:
                return self._move_to_known(state, hub, summary="acquire_heart", vibe="change_vibe_heart")
            return self._explore_action(state, role="aligner", summary="find_hub_for_heart")
        if _should_batch_hearts(state, role="aligner", hub=hub):
            self._clear_target_claim()
            self._clear_sticky_target()
            assert hub is not None
            return self._move_to_known(state, hub, summary="batch_hearts", vibe="change_vibe_heart")

        target = self._preferred_alignable_neutral_junction(state)
        if target is not None:
            self._claim_target(target.position)
            self._set_sticky_target(target.position, target.entity_type)
            return self._move_to_known(state, target, summary="align_junction", vibe="change_vibe_aligner")

        self._clear_target_claim()
        self._clear_sticky_target()
        if _resource_total(state) > 0:
            depot = self._nearest_friendly_depot(state)
            if depot is not None:
                return self._move_to_known(state, depot, summary="deposit_cargo", vibe="change_vibe_aligner")

        return self._explore_action(state, role="aligner", summary="find_neutral_junction")

    def _scrambler_action(self, state: MettagridState) -> tuple[Action, str]:
        hearts = int(state.self_state.inventory.get("heart", 0))
        hub = self._nearest_hub(state)
        if hearts <= 0:
            self._clear_sticky_target()
            if not _team_can_refill_hearts(state):
                return self._miner_action(state, summary_prefix="rebuild_hearts_")
            if hub is not None:
                return self._move_to_known(state, hub, summary="acquire_heart", vibe="change_vibe_heart")
            return self._explore_action(state, role="scrambler", summary="find_hub_for_heart")
        if _should_batch_hearts(state, role="scrambler", hub=hub):
            self._clear_sticky_target()
            assert hub is not None
            return self._move_to_known(state, hub, summary="batch_hearts", vibe="change_vibe_heart")

        target = self._preferred_scramble_target(state)
        if target is not None:
            self._set_sticky_target(target.position, target.entity_type)
            return self._move_to_known(state, target, summary="scramble_junction", vibe="change_vibe_scrambler")

        self._clear_sticky_target()
        return self._explore_action(state, role="scrambler", summary="find_enemy_junction")

    def _explore_action(self, state: MettagridState, *, role: str, summary: str) -> tuple[Action, str]:
        current_pos = _absolute_position(state)
        hub = self._nearest_hub(state)
        center = (hub.global_x, hub.global_y) if hub is not None else current_pos
        offsets = _explore_offsets(role)
        offset_index = (self._explore_index + self._agent_id) % len(offsets)
        target = offsets[offset_index]
        absolute_target = (center[0] + target[0], center[1] + target[1])
        if _manhattan(current_pos, absolute_target) <= 2:
            self._explore_index += 1
            offset_index = (self._explore_index + self._agent_id) % len(offsets)
            target = offsets[offset_index]
            absolute_target = (center[0] + target[0], center[1] + target[1])
        return self._move_to_position(state, absolute_target, summary=summary, vibe=_role_vibe(role))

    def _move_to_known(
        self,
        state: MettagridState,
        entity: KnownEntity,
        *,
        summary: str,
        vibe: str | None = None,
    ) -> tuple[Action, str]:
        self._current_target_position = entity.position
        self._current_target_kind = entity.entity_type
        return self._move_to_position(state, entity.position, summary=summary, vibe=vibe)

    def _move_to_position(
        self,
        state: MettagridState,
        target: tuple[int, int],
        *,
        summary: str,
        vibe: str | None = None,
    ) -> tuple[Action, str]:
        self._current_target_position = target
        self._current_target_kind = self._current_target_kind or "position"
        current = _absolute_position(state)
        next_step = self._next_step(current, target)
        if next_step is None:
            self._last_attempt = None
            return self._hold(summary=f"{summary}_hold", vibe=vibe)

        direction = _direction_from_step(current, next_step)
        stationary_use = next_step == target and self._world_model.is_occupied(target)
        self._last_attempt = MoveAttempt(direction=direction, stationary_use=stationary_use)
        return self._action(f"move_{direction}", vibe=vibe), summary

    def _hold(self, *, summary: str, vibe: str | None = None) -> tuple[Action, str]:
        self._last_attempt = None
        if "retreat" in summary:
            self._current_target_kind = "retreat"
        return self._action(self._fallback_action, vibe=vibe), summary

    def _claim_target(self, target: tuple[int, int]) -> None:
        self._clear_stale_claims()
        self._clear_target_claim()
        self._shared_claims[target] = (self._agent_id, self._step_index)
        self._claimed_target = target

    def _clear_target_claim(self) -> None:
        if self._claimed_target is None:
            return
        claim = self._shared_claims.get(self._claimed_target)
        if claim is not None and claim[0] == self._agent_id:
            self._shared_claims.pop(self._claimed_target)
        self._claimed_target = None

    def _set_sticky_target(self, position: tuple[int, int], entity_type: str) -> None:
        self._sticky_target_position = position
        self._sticky_target_kind = entity_type

    def _clear_sticky_target(self) -> None:
        self._sticky_target_position = None
        self._sticky_target_kind = None

    def _clear_stale_claims(self) -> None:
        stale_positions = [
            position
            for position, (_, step) in self._shared_claims.items()
            if self._step_index - step > _TARGET_CLAIM_STEPS
        ]
        for position in stale_positions:
            self._shared_claims.pop(position)

    def _next_step(self, current: tuple[int, int], target: tuple[int, int]) -> tuple[int, int] | None:
        if current == target:
            return None

        blocked = self._world_model.occupied_cells(exclude={target})
        blocked.update(cell for cell, until_step in self._temp_blocks.items() if until_step >= self._step_index)
        if _manhattan(current, target) <= 1:
            return target

        min_x = min(current[0], target[0]) - _DEFAULT_BOUND_MARGIN
        max_x = max(current[0], target[0]) + _DEFAULT_BOUND_MARGIN
        min_y = min(current[1], target[1]) - _DEFAULT_BOUND_MARGIN
        max_y = max(current[1], target[1]) + _DEFAULT_BOUND_MARGIN

        frontier: list[tuple[int, int, tuple[int, int]]] = [(0, 0, current)]
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        best_cost = {current: 0}

        while frontier:
            _, cost, node = heapq.heappop(frontier)
            if node == target:
                break
            if cost > best_cost.get(node, cost):
                continue
            for dx, dy in _MOVE_DELTAS.values():
                nxt = (node[0] + dx, node[1] + dy)
                if nxt in blocked:
                    continue
                if nxt[0] < min_x or nxt[0] > max_x or nxt[1] < min_y or nxt[1] > max_y:
                    continue
                next_cost = cost + 1
                if next_cost >= best_cost.get(nxt, 1 << 30):
                    continue
                best_cost[nxt] = next_cost
                came_from[nxt] = node
                priority = next_cost + _manhattan(nxt, target)
                heapq.heappush(frontier, (priority, next_cost, nxt))

        if target not in came_from:
            return _greedy_step(current, target, blocked)

        step = target
        while came_from[step] != current:
            step = came_from[step]
        return step

    def _update_temp_blocks(self, current_pos: tuple[int, int]) -> None:
        self._temp_blocks = {
            cell: until_step for cell, until_step in self._temp_blocks.items() if until_step >= self._step_index
        }
        if self._last_attempt is None or self._last_global_pos is None:
            return
        if current_pos != self._last_global_pos:
            return
        if self._last_attempt.stationary_use:
            return
        dx, dy = _MOVE_DELTAS[self._last_attempt.direction]
        blocked_cell = (current_pos[0] + dx, current_pos[1] + dy)
        self._temp_blocks[blocked_cell] = self._step_index + _TEMP_BLOCK_STEPS

    def _nearest_hub(self, state: MettagridState) -> KnownEntity | None:
        hub = self._world_model.nearest(
            position=_absolute_position(state),
            entity_type="hub",
            predicate=lambda entity: entity.team == _team_id(state),
        )
        if hub is not None:
            return hub

        bootstrap_offset = _HUB_OFFSETS.get(self._agent_id)
        if bootstrap_offset is None:
            return None
        return KnownEntity(
            entity_type="hub",
            global_x=bootstrap_offset[0],
            global_y=bootstrap_offset[1],
            labels=(),
            team=_team_id(state),
            owner=_team_id(state),
            last_seen_step=state.step or self._step_index,
            attributes={},
        )

    def _nearest_friendly_depot(self, state: MettagridState) -> KnownEntity | None:
        team_id = _team_id(state)
        depot = self._world_model.nearest(
            position=_absolute_position(state),
            predicate=lambda entity: (
                (entity.entity_type == "hub" and entity.team == team_id)
                or (entity.entity_type == "junction" and entity.owner == team_id)
            ),
        )
        shared_friendly = self._shared_junction_entities(state, predicate=lambda entity: entity.owner == team_id)
        if shared_friendly:
            shared_nearest = min(
                shared_friendly,
                key=lambda entity: (_manhattan(_absolute_position(state), entity.position), entity.position),
            )
            if depot is None or _manhattan(_absolute_position(state), shared_nearest.position) < _manhattan(
                _absolute_position(state), depot.position
            ):
                depot = shared_nearest
        if depot is not None:
            return depot
        return self._nearest_hub(state)

    def _update_shared_junctions(self, state: MettagridState) -> None:
        hub = self._nearest_hub(state)
        if hub is None:
            return
        for entity in state.visible_entities:
            if entity.entity_type != "junction":
                continue
            rel_position = (
                int(entity.attributes["global_x"]) - hub.global_x,
                int(entity.attributes["global_y"]) - hub.global_y,
            )
            owner = entity.attributes.get("owner")
            self._shared_junctions[rel_position] = (
                None if owner in {None, "neutral"} else str(owner),
                state.step or self._step_index,
            )

    def _shared_junction_entities(
        self,
        state: MettagridState,
        *,
        predicate: Callable[[KnownEntity], bool],
    ) -> list[KnownEntity]:
        hub = self._nearest_hub(state)
        if hub is None:
            return []
        step = state.step or self._step_index
        result = []
        for (dx, dy), (owner, last_seen_step) in self._shared_junctions.items():
            if step - last_seen_step > _SHARED_JUNCTION_MEMORY_STEPS:
                continue
            entity = KnownEntity(
                entity_type="junction",
                global_x=hub.global_x + dx,
                global_y=hub.global_y + dy,
                labels=(),
                team=owner,
                owner=owner,
                last_seen_step=last_seen_step,
                attributes={},
            )
            if predicate(entity):
                result.append(entity)
        return result

    def _known_junctions(
        self,
        state: MettagridState,
        *,
        predicate: Callable[[KnownEntity], bool],
    ) -> list[KnownEntity]:
        by_position = {
            entity.position: entity
            for entity in self._world_model.entities(entity_type="junction", predicate=predicate)
        }
        for entity in self._shared_junction_entities(state, predicate=predicate):
            by_position.setdefault(entity.position, entity)
        return list(by_position.values())

    def _nearest_alignable_neutral_junction(self, state: MettagridState) -> KnownEntity | None:
        team_id = _team_id(state)
        current_pos = _absolute_position(state)
        hubs = self._world_model.entities(entity_type="hub", predicate=lambda entity: entity.team == team_id)
        friendly_junctions = self._known_junctions(state, predicate=lambda entity: entity.owner == team_id)
        network_sources = [*hubs, *friendly_junctions]
        candidates = []
        for entity in self._known_junctions(state, predicate=lambda junction: junction.owner in {None, "neutral"}):
            if not _within_alignment_network(entity.position, network_sources):
                continue
            candidates.append(entity)
        if not candidates:
            return None
        directed_candidate = self._directive_target_candidate(candidates)
        if directed_candidate is not None:
            return directed_candidate
        enemy_junctions = self._known_junctions(
            state,
            predicate=lambda junction: junction.owner not in {None, "neutral", team_id},
        )
        unreachable = [
            entity
            for entity in self._known_junctions(state, predicate=lambda junction: junction.owner in {None, "neutral"})
            if entity not in candidates
        ]
        return min(
            candidates,
            key=lambda entity: (
                _aligner_target_score(
                    current_position=current_pos,
                    candidate=entity,
                    unreachable=unreachable,
                    enemy_junctions=enemy_junctions,
                    claimed_by_other=_is_claimed_by_other(
                        claims=self._shared_claims,
                        candidate=entity.position,
                        agent_id=self._agent_id,
                        step=self._step_index,
                    ),
                ),
                entity.position,
            ),
        )

    def _preferred_alignable_neutral_junction(self, state: MettagridState) -> KnownEntity | None:
        candidate = self._nearest_alignable_neutral_junction(state)
        sticky = self._sticky_align_target(state)
        if sticky is None:
            return candidate
        if candidate is None:
            return sticky

        current_pos = _absolute_position(state)
        team_id = _team_id(state)
        neutral_junctions = self._world_model.entities(
            entity_type="junction",
            predicate=lambda junction: junction.owner in {None, "neutral"},
        )
        enemy_junctions = self._world_model.entities(
            entity_type="junction",
            predicate=lambda junction: junction.owner not in {None, "neutral", team_id},
        )
        sticky_score = _aligner_target_score(
            current_position=current_pos,
            candidate=sticky,
            unreachable=[entity for entity in neutral_junctions if entity.position != sticky.position],
            enemy_junctions=enemy_junctions,
            claimed_by_other=False,
        )[0]
        candidate_score = _aligner_target_score(
            current_position=current_pos,
            candidate=candidate,
            unreachable=[entity for entity in neutral_junctions if entity.position != candidate.position],
            enemy_junctions=enemy_junctions,
            claimed_by_other=_is_claimed_by_other(
                claims=self._shared_claims,
                candidate=candidate.position,
                agent_id=self._agent_id,
                step=self._step_index,
            ),
        )[0]
        if candidate.position != sticky.position and candidate_score + _TARGET_SWITCH_THRESHOLD < sticky_score:
            return candidate
        return sticky

    def _sticky_align_target(self, state: MettagridState) -> KnownEntity | None:
        if self._sticky_target_kind != "junction" or self._sticky_target_position is None:
            return None
        team_id = _team_id(state)
        hubs = self._world_model.entities(entity_type="hub", predicate=lambda entity: entity.team == team_id)
        friendly_junctions = self._known_junctions(state, predicate=lambda entity: entity.owner == team_id)
        target = next(
            (
                entity
                for entity in self._known_junctions(state, predicate=lambda entity: entity.owner in {None, "neutral"})
                if entity.position == self._sticky_target_position
            ),
            None,
        )
        if target is None:
            self._clear_sticky_target()
            return None
        if not _within_alignment_network(target.position, [*hubs, *friendly_junctions]):
            self._clear_sticky_target()
            return None
        return target

    def _preferred_miner_extractor(self, state: MettagridState) -> KnownEntity | None:
        if self._should_force_miner_explore_reset(state):
            self._clear_sticky_target()
            return None

        current_pos = _absolute_position(state)
        candidates: list[KnownEntity] = []
        for resource_name in _resource_priority(state, resource_bias=self._resource_bias):
            matches = self._world_model.entities(
                entity_type=f"{resource_name}_extractor",
                predicate=lambda entity: _is_usable_recent_extractor(entity, step=state.step or self._step_index),
            )
            candidates.extend(
                sorted(
                    matches,
                    key=lambda entity: (_manhattan(current_pos, entity.position), entity.position),
                )
            )
        if not candidates:
            return None

        directed_candidate = self._directive_target_candidate(candidates)
        if directed_candidate is not None:
            return directed_candidate

        sticky = self._sticky_miner_target(state)
        if sticky is None:
            return candidates[0]

        candidate = candidates[0]
        sticky_distance = _manhattan(current_pos, sticky.position)
        candidate_distance = _manhattan(current_pos, candidate.position)
        if candidate.position != sticky.position and candidate_distance + _TARGET_SWITCH_THRESHOLD < sticky_distance:
            return candidate
        return sticky

    def _should_force_miner_explore_reset(self, state: MettagridState) -> bool:
        if self._stalled_steps < 12:
            return False
        if any(entity.entity_type.endswith("_extractor") for entity in state.visible_entities):
            return False
        hub = self._nearest_hub(state)
        if hub is None:
            return False
        return _manhattan(_absolute_position(state), hub.position) <= 1

    def _sticky_miner_target(self, state: MettagridState) -> KnownEntity | None:
        if self._sticky_target_kind is None or self._sticky_target_position is None:
            return None
        if not self._sticky_target_kind.endswith("_extractor"):
            return None
        target = next(
            (
                entity
                for entity in self._world_model.entities(
                    entity_type=self._sticky_target_kind,
                    predicate=lambda entity: _is_usable_recent_extractor(entity, step=state.step or self._step_index),
                )
                if entity.position == self._sticky_target_position
            ),
            None,
        )
        if target is None:
            self._clear_sticky_target()
            return None
        return target

    def _best_scramble_target(self, state: MettagridState) -> KnownEntity | None:
        team_id = _team_id(state)
        current_pos = _absolute_position(state)
        hub = self._nearest_hub(state)
        neutral_junctions = self._known_junctions(state, predicate=lambda entity: entity.owner in {None, "neutral"})
        enemy_junctions = self._known_junctions(
            state,
            predicate=lambda entity: entity.owner not in {None, "neutral", team_id},
        )
        if not enemy_junctions:
            return None
        directed_candidate = self._directive_target_candidate(enemy_junctions)
        if directed_candidate is not None:
            return directed_candidate
        hub_position = current_pos if hub is None else hub.position
        return min(
            enemy_junctions,
            key=lambda entity: (
                _scramble_target_score(
                    current_position=current_pos,
                    hub_position=hub_position,
                    candidate=entity,
                    neutral_junctions=neutral_junctions,
                ),
                entity.position,
            ),
        )

    def _directive_target_candidate(self, candidates: list[KnownEntity]) -> KnownEntity | None:
        if not candidates:
            return None
        target_entity_id = self._current_directive.target_entity_id
        if target_entity_id is not None:
            for entity in candidates:
                if f"{entity.entity_type}@{entity.global_x},{entity.global_y}" == target_entity_id:
                    return entity
        target_region = self._current_directive.target_region
        if target_region is None:
            return None
        region = target_region.strip()
        if not region:
            return None
        for entity in candidates:
            if region in entity.labels:
                return entity
            if region in {value for value in entity.attributes.values() if isinstance(value, str)}:
                return entity
        return None

    def _preferred_scramble_target(self, state: MettagridState) -> KnownEntity | None:
        candidate = self._best_scramble_target(state)
        sticky = self._sticky_scramble_target(state)
        if sticky is None:
            return candidate
        if candidate is None:
            return sticky

        current_pos = _absolute_position(state)
        hub = self._nearest_hub(state)
        hub_position = current_pos if hub is None else hub.position
        neutral_junctions = self._world_model.entities(
            entity_type="junction",
            predicate=lambda entity: entity.owner in {None, "neutral"},
        )
        sticky_score = _scramble_target_score(
            current_position=current_pos,
            hub_position=hub_position,
            candidate=sticky,
            neutral_junctions=neutral_junctions,
        )[0]
        candidate_score = _scramble_target_score(
            current_position=current_pos,
            hub_position=hub_position,
            candidate=candidate,
            neutral_junctions=neutral_junctions,
        )[0]
        if candidate.position != sticky.position and candidate_score + _TARGET_SWITCH_THRESHOLD < sticky_score:
            return candidate
        return sticky

    def _sticky_scramble_target(self, state: MettagridState) -> KnownEntity | None:
        if self._sticky_target_kind != "junction" or self._sticky_target_position is None:
            return None
        team_id = _team_id(state)
        target = next(
            (
                entity
                for entity in self._known_junctions(
                    state,
                    predicate=lambda entity: entity.owner not in {None, "neutral", team_id},
                )
                if entity.position == self._sticky_target_position
            ),
            None,
        )
        if target is None:
            self._clear_sticky_target()
            return None
        return target

    def _macro_snapshot(self, state: MettagridState, role: str) -> dict[str, int | str | bool]:
        safe_target = self._nearest_friendly_depot(state)
        safe_distance = 0 if safe_target is None else _manhattan(_absolute_position(state), safe_target.position)
        hp = int(state.self_state.inventory.get("hp", 0))
        team_id = _team_id(state)
        in_enemy_aoe = self._in_enemy_aoe(state, _absolute_position(state), team_id=team_id)
        low_hp_risk = self._should_retreat(state, role, safe_target)
        payload_at_risk = low_hp_risk and (
            int(state.self_state.inventory.get("heart", 0)) > 0 or _resource_total(state) > 0
        )
        pressure_metrics = self._pressure_metrics(state)
        aligner_budget, scrambler_budget = self._pressure_budgets(state)
        heart_supply = _heart_supply_capacity(state)

        macro_note = (
            f"frontier={pressure_metrics.frontier_neutral_junctions} "
            f"best_cover={pressure_metrics.best_frontier_coverage} "
            f"best_scramble={pressure_metrics.best_enemy_scramble_block} "
            f"pressure={aligner_budget + scrambler_budget} "
            f"safe_distance={safe_distance}"
        )
        return {
            "hp": hp,
            "safe_distance": safe_distance,
            "low_hp_risk": low_hp_risk,
            "payload_at_risk": payload_at_risk,
            "team_can_afford_role_gear": _team_can_afford_gear(state, role),
            "in_enemy_aoe": in_enemy_aoe,
            "frontier_neutral_junctions": pressure_metrics.frontier_neutral_junctions,
            "best_frontier_coverage": pressure_metrics.best_frontier_coverage,
            "best_enemy_scramble_block": pressure_metrics.best_enemy_scramble_block,
            "heart_supply": heart_supply,
            "pressure_budget": aligner_budget + scrambler_budget,
            "aligner_budget": aligner_budget,
            "scrambler_budget": scrambler_budget,
            "macro_note": macro_note,
        }

    def _pressure_metrics(self, state: MettagridState) -> PressureMetrics:
        team_id = _team_id(state)
        hub = self._nearest_hub(state)
        friendly_sources = []
        if hub is not None:
            friendly_sources.append(hub)
        friendly_sources.extend(self._known_junctions(state, predicate=lambda entity: entity.owner == team_id))
        neutral_junctions = self._known_junctions(state, predicate=lambda entity: entity.owner in {None, "neutral"})
        frontier_junctions = [
            entity for entity in neutral_junctions if _within_alignment_network(entity.position, friendly_sources)
        ]
        unreachable_junctions = [entity for entity in neutral_junctions if entity not in frontier_junctions]
        best_frontier_coverage = max(
            (
                sum(
                    1
                    for neutral in unreachable_junctions
                    if _manhattan(candidate.position, neutral.position) <= _JUNCTION_ALIGN_DISTANCE
                )
                for candidate in frontier_junctions
            ),
            default=0,
        )
        enemy_junctions = self._known_junctions(
            state,
            predicate=lambda entity: entity.owner not in {None, "neutral", team_id},
        )
        best_enemy_scramble_block = max(
            (
                sum(
                    1
                    for neutral in neutral_junctions
                    if _manhattan(enemy.position, neutral.position) <= _JUNCTION_AOE_RANGE
                )
                for enemy in enemy_junctions
            ),
            default=0,
        )
        return PressureMetrics(
            frontier_neutral_junctions=len(frontier_junctions),
            best_frontier_coverage=best_frontier_coverage,
            best_enemy_scramble_block=best_enemy_scramble_block,
        )

    def _pressure_budgets(self, state: MettagridState) -> tuple[int, int]:
        step = state.step or self._step_index

        pressure_budget = 4
        if step >= 40 and _team_min_resource(state) >= _MINING_ALIGNER_MIN_RESOURCE:
            pressure_budget = 5

        scrambler_budget = 0
        if step >= 1_500:
            scrambler_budget = 1
        if step >= 5_000 and _team_can_refill_hearts(state):
            scrambler_budget = 2
        aligner_budget = pressure_budget - scrambler_budget
        return aligner_budget, scrambler_budget

    def _in_enemy_aoe(self, state: MettagridState, position: tuple[int, int], *, team_id: str) -> bool:
        enemies = self._known_junctions(
            state,
            predicate=lambda entity: entity.owner not in {None, "neutral", team_id},
        )
        for enemy in enemies:
            if _manhattan(position, enemy.position) <= _JUNCTION_AOE_RANGE:
                return True
        return False

    def _should_retreat(self, state: MettagridState, role: str, safe_target: KnownEntity | None) -> bool:
        hp = int(state.self_state.inventory.get("hp", 0))
        if safe_target is None:
            return hp <= _retreat_threshold(state, role)

        safe_steps = max(0, _manhattan(_absolute_position(state), safe_target.position) - _JUNCTION_AOE_RANGE)
        margin = _RETREAT_MARGIN
        if self._in_enemy_aoe(state, _absolute_position(state), team_id=_team_id(state)):
            margin += 10
        margin += int(state.self_state.inventory.get("heart", 0)) * 5
        margin += min(_resource_total(state), 12) // 2
        if not _has_role_gear(state, role):
            margin += 10
        if (state.step or 0) >= 2_500:
            margin += 10 if role in {"aligner", "scrambler"} else 5
        return hp <= safe_steps + margin

    def _should_deposit_resources(self, state: MettagridState) -> bool:
        cargo = _resource_total(state)
        if cargo <= 0:
            return False
        if cargo >= _deposit_threshold(state):
            return True

        safe_target = self._nearest_friendly_depot(state)
        if safe_target is None:
            return cargo >= 4

        safe_distance = _manhattan(_absolute_position(state), safe_target.position)
        if cargo >= 16 and safe_distance > 18:
            return True
        if cargo >= 8 and self._should_retreat(state, "miner", safe_target):
            return True
        if cargo >= 12 and self._in_enemy_aoe(state, _absolute_position(state), team_id=_team_id(state)):
            return True
        return False

    def _action(self, name: str, *, vibe: str | None = None) -> Action:
        action_name = name if name in self._action_names else self._fallback_action
        vibe_name = vibe if vibe in self._vibe_actions else None
        return Action(name=action_name, vibe=vibe_name)

    def _update_stall_counter(self, state: MettagridState, current_pos: tuple[int, int]) -> None:
        inventory_signature = _inventory_signature(state)
        if self._last_global_pos == current_pos and self._last_inventory_signature == inventory_signature:
            self._stalled_steps += 1
        else:
            self._stalled_steps = 0

    def _record_navigation_observation(self, current_pos: tuple[int, int], summary: str) -> None:
        self._recent_navigation.append(
            NavigationObservation(
                position=current_pos,
                subtask=summary,
                target_kind=self._current_target_kind or "",
                target_position=self._current_target_position,
            )
        )
        self._oscillation_steps = self._extractor_oscillation_length()

    def _extractor_oscillation_length(self) -> int:
        if len(self._recent_navigation) < 2:
            return 0
        observations = list(self._recent_navigation)
        max_size = min(len(observations), _OSCILLATION_HISTORY_STEPS)
        for size in range(max_size, 1, -1):
            window = observations[-size:]
            first = window[0]
            second = window[1]
            if first.position == second.position:
                continue
            if not first.subtask.startswith("mine_"):
                continue
            if not first.target_kind.endswith("_extractor"):
                continue
            if first.target_position is None:
                continue
            if any(
                item.subtask != first.subtask
                or item.target_kind != first.target_kind
                or item.target_position != first.target_position
                for item in window
            ):
                continue
            if all(
                item.position == (first.position if index % 2 == 0 else second.position)
                for index, item in enumerate(window)
            ):
                return size
        return 0

    def _unstick_action(self, state: MettagridState, role: str) -> tuple[Action, str]:
        current = _absolute_position(state)
        if role == "miner":
            self._world_model.forget_nearest(
                position=current,
                entity_type=f"{self._resource_bias}_extractor",
                max_distance=2,
            )
            for resource_name in _ELEMENTS:
                self._world_model.forget_nearest(
                    position=current,
                    entity_type=f"{resource_name}_extractor",
                    max_distance=2,
                )
        self._explore_index += 1
        blocked = self._world_model.occupied_cells()
        blocked.update(cell for cell, until_step in self._temp_blocks.items() if until_step >= self._step_index)
        for direction in _unstick_directions(self._agent_id, self._step_index):
            dx, dy = _MOVE_DELTAS[direction]
            nxt = (current[0] + dx, current[1] + dy)
            if nxt in blocked:
                continue
            self._last_attempt = MoveAttempt(direction=direction, stationary_use=False)
            return self._action(f"move_{direction}", vibe=_role_vibe(role)), f"unstick_{role}"
        return self._hold(summary=f"unstick_{role}_hold", vibe=_role_vibe(role))


class MettagridSemanticPolicy(MultiAgentPolicy):
    short_names = ["mettagrid-semantic", "semantic-cog", "sdk-semantic"]

    def __init__(self, policy_env_info: PolicyEnvInterface, device: str = "cpu", **kwargs) -> None:
        super().__init__(policy_env_info, device=device, **kwargs)
        self._agent_policies: dict[int, SemanticCogAgentPolicy] = {}
        self._shared_claims: dict[tuple[int, int], tuple[int, int]] = {}
        self._shared_junctions: dict[tuple[int, int], tuple[str | None, int]] = {}

    def agent_policy(self, agent_id: int) -> AgentPolicy:
        if agent_id not in self._agent_policies:
            self._agent_policies[agent_id] = SemanticCogAgentPolicy(
                self.policy_env_info,
                agent_id=agent_id,
                world_model=SharedWorldModel(),
                shared_claims=self._shared_claims,
                shared_junctions=self._shared_junctions,
            )
        return self._agent_policies[agent_id]

    def reset(self) -> None:
        self._shared_claims.clear()
        self._shared_junctions.clear()
        for policy in self._agent_policies.values():
            policy.reset()


def _absolute_position(state: MettagridState) -> tuple[int, int]:
    return (
        int(state.self_state.attributes.get("global_x", 0)),
        int(state.self_state.attributes.get("global_y", 0)),
    )


def _attr_int(entity: SemanticEntity, name: str, default: int = 0) -> int:
    value = entity.attributes.get(name)
    return default if value is None else int(value)


def _attr_str(entity: SemanticEntity, name: str) -> str | None:
    value = entity.attributes.get(name)
    if value is None:
        return None
    return str(value)


def _has_role_gear(state: MettagridState, role: str) -> bool:
    return int(state.self_state.inventory.get(role, 0)) > 0


def _resource_total(state: MettagridState) -> int:
    return sum(int(state.self_state.inventory.get(resource, 0)) for resource in _ELEMENTS)


def _deposit_threshold(state: MettagridState) -> int:
    if _has_role_gear(state, "miner"):
        return 40
    return 4


def _team_id(state: MettagridState) -> str:
    if state.team_summary is None:
        return str(state.self_state.attributes.get("team", ""))
    return state.team_summary.team_id


def _needs_emergency_mining(state: MettagridState) -> bool:
    if state.team_summary is None:
        return False
    return _team_min_resource(state) < _EMERGENCY_RESOURCE_LOW


def _team_min_resource(state: MettagridState) -> int:
    if state.team_summary is None:
        return 0
    return min(int(state.team_summary.shared_inventory.get(resource, 0)) for resource in _ELEMENTS)


def _resource_priority(state: MettagridState, *, resource_bias: str) -> list[str]:
    shared_inventory = {} if state.team_summary is None else state.team_summary.shared_inventory
    return sorted(
        _ELEMENTS,
        key=lambda resource: (
            int(shared_inventory.get(resource, 0)),
            0 if resource == resource_bias else 1,
            resource,
        ),
    )


def _inventory_signature(state: MettagridState) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((name, int(value)) for name, value in state.self_state.inventory.items()))


def _role_vibe(role: str) -> str:
    if role in {"aligner", "miner", "scrambler", "scout"}:
        return f"change_vibe_{role}"
    return "change_vibe_default"


def _retreat_threshold(state: MettagridState, role: str) -> int:
    threshold = _HP_THRESHOLDS[role]
    step = state.step or 0
    if step >= 2_500:
        if role in {"aligner", "scrambler"}:
            threshold += 15
        elif role == "miner":
            threshold += 10
    if not _has_role_gear(state, role):
        threshold += 10
    return threshold


def _phase_name(state: MettagridState, role: str) -> str:
    hp = int(state.self_state.inventory.get("hp", 0))
    if hp <= _retreat_threshold(state, role):
        return "retreat"
    if not _has_role_gear(state, role):
        if role != "miner" and not _team_can_afford_gear(state, role):
            return "fund_gear"
        return "regear"
    if role in {"aligner", "scrambler"} and int(state.self_state.inventory.get("heart", 0)) <= 0:
        return "hearts"
    if role == "miner" and _resource_total(state) >= _deposit_threshold(state):
        return "deposit"
    if role == "miner":
        return "economy"
    if role == "aligner":
        return "expand"
    if role == "scrambler":
        return "pressure"
    return "explore"


def _heart_batch_target(state: MettagridState, role: str) -> int:
    if role not in _HEART_BATCH_TARGETS:
        return 0
    target = _HEART_BATCH_TARGETS[role]
    step = state.step or 0
    if role == "aligner" and step >= 3_000:
        target = 3
    return target


def _team_can_afford_gear(state: MettagridState, role: str) -> bool:
    if role not in _GEAR_COSTS:
        return True
    if state.team_summary is None:
        return False
    inventory = state.team_summary.shared_inventory
    return all(int(inventory.get(resource, 0)) >= amount for resource, amount in _GEAR_COSTS[role].items())


def _team_can_refill_hearts(state: MettagridState) -> bool:
    if state.team_summary is None:
        return False
    inventory = state.team_summary.shared_inventory
    if int(inventory.get("heart", 0)) > 0:
        return True
    return all(int(inventory.get(resource, 0)) >= 7 for resource in _ELEMENTS)


def _heart_supply_capacity(state: MettagridState) -> int:
    if state.team_summary is None:
        return 0
    inventory = state.team_summary.shared_inventory
    return int(inventory.get("heart", 0)) + _team_min_resource(state) // 7


def _should_batch_hearts(
    state: MettagridState,
    *,
    role: str,
    hub: KnownEntity | None,
) -> bool:
    if hub is None:
        return False
    hearts = int(state.self_state.inventory.get("heart", 0))
    batch_target = _heart_batch_target(state, role)
    if hearts <= 0 or hearts >= batch_target:
        return False
    if not _team_can_refill_hearts(state):
        return False
    return _manhattan(_absolute_position(state), hub.position) <= 1


def _direction_from_step(current: tuple[int, int], next_step: tuple[int, int]) -> str:
    dx = next_step[0] - current[0]
    dy = next_step[1] - current[1]
    if dx == 1:
        return "east"
    if dx == -1:
        return "west"
    if dy == 1:
        return "south"
    if dy == -1:
        return "north"
    raise ValueError(f"Non-adjacent step from {current} to {next_step}")


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _format_position(position: tuple[int, int]) -> str:
    return f"{position[0]},{position[1]}"


def _within_alignment_network(
    candidate: tuple[int, int],
    sources: list[KnownEntity],
) -> bool:
    for source in sources:
        max_distance = _HUB_ALIGN_DISTANCE if source.entity_type == "hub" else _JUNCTION_ALIGN_DISTANCE
        if _manhattan(candidate, source.position) <= max_distance:
            return True
    return False


def _aligner_target_score(
    *,
    current_position: tuple[int, int],
    candidate: KnownEntity,
    unreachable: list[KnownEntity],
    enemy_junctions: list[KnownEntity],
    claimed_by_other: bool,
) -> tuple[float, float]:
    distance = float(_manhattan(current_position, candidate.position))
    expansion = sum(
        1 for entity in unreachable if _manhattan(candidate.position, entity.position) <= _JUNCTION_ALIGN_DISTANCE
    )
    enemy_aoe = (
        1.0
        if any(_manhattan(candidate.position, enemy.position) <= _JUNCTION_AOE_RANGE for enemy in enemy_junctions)
        else 0.0
    )
    return (
        distance
        - min(expansion * 3.0, 24.0)
        + enemy_aoe * 8.0
        + (_CLAIMED_TARGET_PENALTY if claimed_by_other else 0.0),
        -float(expansion),
    )


def _is_claimed_by_other(
    *,
    claims: dict[tuple[int, int], tuple[int, int]],
    candidate: tuple[int, int],
    agent_id: int,
    step: int,
) -> bool:
    claim = claims.get(candidate)
    if claim is None:
        return False
    owner_id, owner_step = claim
    if owner_id == agent_id:
        return False
    return step - owner_step <= _TARGET_CLAIM_STEPS


def _is_usable_recent_extractor(entity: KnownEntity, *, step: int) -> bool:
    remaining_uses = int(entity.attributes.get("remaining_uses", 1))
    if remaining_uses <= 0:
        return False
    return step - entity.last_seen_step <= _EXTRACTOR_MEMORY_STEPS


def _scramble_target_score(
    *,
    current_position: tuple[int, int],
    hub_position: tuple[int, int],
    candidate: KnownEntity,
    neutral_junctions: list[KnownEntity],
) -> tuple[float, float]:
    distance = float(_manhattan(current_position, candidate.position))
    blocked_neutrals = sum(
        1 for neutral in neutral_junctions if _manhattan(candidate.position, neutral.position) <= _JUNCTION_AOE_RANGE
    )
    corner_pressure = min(_manhattan(hub_position, candidate.position) / 8.0, 10.0)
    return (
        distance - blocked_neutrals * 4.0 - corner_pressure,
        -float(blocked_neutrals),
    )


def _greedy_step(
    current: tuple[int, int],
    target: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> tuple[int, int] | None:
    candidates = []
    for direction, (dx, dy) in _MOVE_DELTAS.items():
        nxt = (current[0] + dx, current[1] + dy)
        if nxt in blocked:
            continue
        candidates.append((_manhattan(nxt, target), direction, nxt))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _explore_offsets(role: str) -> tuple[tuple[int, int], ...]:
    if role == "miner":
        return _MINER_EXPLORE_OFFSETS
    if role == "scrambler":
        return _SCRAMBLER_EXPLORE_OFFSETS
    return _ALIGNER_EXPLORE_OFFSETS


def _spawn_relative_station_target(agent_id: int, role: str) -> tuple[int, int] | None:
    station_targets = _STATION_TARGETS_BY_AGENT.get(role)
    if station_targets is None:
        return None
    return station_targets.get(agent_id)


def _unstick_directions(agent_id: int, step_index: int) -> tuple[str, ...]:
    orders = (
        ("north", "east", "south", "west"),
        ("east", "south", "west", "north"),
        ("south", "west", "north", "east"),
        ("west", "north", "east", "south"),
    )
    return orders[(agent_id + step_index) % len(orders)]
