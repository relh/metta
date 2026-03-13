from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, field

from mettagrid_sdk.games.cogsguard import CogsguardStateAdapter
from mettagrid_sdk.runtime.observation import ObservationEnvelope
from pydantic import BaseModel, Field

from cogames.cli.mission import get_mission
from cogames.cli.policy import parse_policy_spec
from mettagrid.policy.loader import initialize_or_load_policy
from mettagrid.policy.policy import PolicySpec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.runner.rollout import resolve_env_for_seed
from mettagrid.simulator.interface import SimulatorEventHandler
from mettagrid.simulator.rollout import Rollout

_RESOURCE_NAMES = ("carbon", "oxygen", "germanium", "silicon")
_ROLE_NAMES = ("miner", "aligner", "scrambler", "scout")
_FAR_JUNCTION_DISTANCE = 40
_MANDATORY_CHECKPOINT_STEPS = {1, 250, 1_000}
_BOOTSTRAP_HUB_OFFSETS = {
    0: (0, 3),
    1: (0, 2),
    2: (3, 0),
    3: (2, 0),
    4: (-2, 0),
    5: (-3, 0),
    6: (0, -2),
    7: (0, -3),
}
_ROLE_HP_THRESHOLDS = {"miner": 15, "aligner": 50, "scrambler": 30, "scout": 30, "unknown": 30}
_JUNCTION_ALIGN_DISTANCE = 15
_HUB_ALIGN_DISTANCE = 25
_JUNCTION_AOE_RANGE = 10
_GEAR_COSTS = {
    "miner": {"carbon": 1, "oxygen": 1, "germanium": 3, "silicon": 1},
    "aligner": {"carbon": 3, "oxygen": 1, "germanium": 1, "silicon": 1},
    "scrambler": {"carbon": 1, "oxygen": 3, "germanium": 1, "silicon": 1},
    "scout": {"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 3},
}


class ResourceVector(BaseModel):
    carbon: int = 0
    oxygen: int = 0
    germanium: int = 0
    silicon: int = 0
    heart: int = 0
    influence: int = 0
    solar: int = 0

    def element_total(self) -> int:
        return self.carbon + self.oxygen + self.germanium + self.silicon

    def min_element(self) -> int:
        return min(self.carbon, self.oxygen, self.germanium, self.silicon)


class RoleCounts(BaseModel):
    miner: int = 0
    aligner: int = 0
    scrambler: int = 0
    scout: int = 0
    unknown: int = 0


class RoleDistanceSummary(BaseModel):
    miner: int = 0
    aligner: int = 0
    scrambler: int = 0
    scout: int = 0
    unknown: int = 0


class TrajectoryCheckpoint(BaseModel):
    step: int
    avg_reward_per_agent: float
    aligned_junctions: int
    aligned_junctions_gained: int
    aligned_junction_held: float
    enemy_aligned_junction_held: float
    control_per_heart_withdrawn: float
    effective_heart_gains: int = 0
    effective_heart_spends: int = 0
    affordable_hearts_in_bank: int = 0
    control_per_heart_gain: float = 0.0
    control_per_heart_spend: float = 0.0
    control_per_alignment_gain: float
    team_inventory: ResourceVector
    team_deposits: ResourceVector
    team_withdrawals: ResourceVector
    equipped_roles: RoleCounts
    declared_roles: RoleCounts
    role_max_hub_distance: RoleDistanceSummary
    carrying_hearts: int
    carrying_resources: int
    stationary_agents: int
    max_stationary_streak: int
    far_enemy_junctions_seen: int
    far_neutral_junctions_seen: int
    frontier_neutral_junctions: int = 0
    best_frontier_coverage: int = 0
    best_enemy_scramble_block: int = 0
    heart_supply_capacity: int = 0
    pressure_budget: int = 0
    pressure_oversubscription: int = 0
    aligner_target_collisions: int = 0
    unique_aligner_targets: int = 0
    hub_zone_agents: int = 0
    hub_queue_agents: int = 0
    low_hp_agents: int = 0
    risky_low_hp_agents: int = 0
    payload_risk_agents: int = 0
    gearless_unaffordable_agents: int = 0
    heart_starved_agents: int = 0
    cumulative_low_hp_steps: int = 0
    cumulative_risky_low_hp_steps: int = 0
    cumulative_payload_risk_steps: int = 0


class TrajectoryMilestones(BaseModel):
    first_miner_gear_step: int | None = None
    first_aligner_gear_step: int | None = None
    first_scrambler_gear_step: int | None = None
    first_heart_carried_step: int | None = None
    first_heart_withdrawal_step: int | None = None
    first_alignment_step: int | None = None
    first_scramble_step: int | None = None


class TrajectoryReport(BaseModel):
    policy_name: str
    mission_name: str
    seed: int
    steps: int
    avg_reward_per_agent: float
    avg_deaths_per_agent: float = 0.0
    final_aligned_junctions: int
    final_aligned_junction_held: float
    final_enemy_aligned_junction_held: float
    plateau_step: int | None = None
    agent_motifs: list["AgentMotifSummary"] = Field(default_factory=list)
    checkpoints: list[TrajectoryCheckpoint] = Field(default_factory=list)
    milestones: TrajectoryMilestones = Field(default_factory=TrajectoryMilestones)
    insights: list[str] = Field(default_factory=list)


class AgentMotifSummary(BaseModel):
    agent_id: int
    declared_role: str
    role_switches: int = 0
    gear_loss_events: int = 0
    regear_events: int = 0
    avg_regear_delay: float = 0.0
    total_gearless_steps: int = 0
    longest_gearless_stretch: int = 0
    target_switches: int = 0
    target_abandonments: int = 0
    target_progress_steps: int = 0
    target_regress_steps: int = 0
    target_stall_steps: int = 0
    risky_low_hp_steps: int = 0
    risky_low_hp_episodes: int = 0
    avg_retreat_resolution: float = 0.0
    heart_seek_episodes: int = 0
    avg_heart_seek_delay: float = 0.0
    avg_heart_to_use_delay: float = 0.0
    max_hearts_carried: int = 0
    likely_respawns: int = 0
    gearless_unaffordable_steps: int = 0
    heart_starved_steps: int = 0
    payload_risk_steps: int = 0
    payload_loss_events: int = 0
    payload_loss_hearts: int = 0
    payload_loss_resources: int = 0


class TrajectoryComparison(BaseModel):
    mission_name: str
    seed: int
    reports: list[TrajectoryReport] = Field(default_factory=list)


@dataclass(slots=True)
class _AgentMotifTracker:
    declared_role: str = "unknown"
    role_switches: int = 0
    gear_loss_events: int = 0
    regear_events: int = 0
    regear_delays: list[int] = field(default_factory=list)
    gearless_start_step: int | None = None
    total_gearless_steps: int = 0
    longest_gearless_stretch: int = 0
    target_switches: int = 0
    target_abandonments: int = 0
    target_progress_steps: int = 0
    target_regress_steps: int = 0
    target_stall_steps: int = 0
    risky_low_hp_steps: int = 0
    risky_low_hp_episodes: int = 0
    retreat_start_step: int | None = None
    retreat_resolution_delays: list[int] = field(default_factory=list)
    heart_seek_episodes: int = 0
    heart_seek_start_step: int | None = None
    heart_seek_delays: list[int] = field(default_factory=list)
    heart_hold_start_step: int | None = None
    heart_to_use_delays: list[int] = field(default_factory=list)
    max_hearts_carried: int = 0
    effective_heart_gains: int = 0
    effective_heart_spends: int = 0
    likely_respawns: int = 0
    gearless_unaffordable_steps: int = 0
    heart_starved_steps: int = 0
    payload_risk_steps: int = 0
    payload_loss_events: int = 0
    payload_loss_hearts: int = 0
    payload_loss_resources: int = 0
    previous_has_gear: bool = False
    previous_declared_role: str = ""
    previous_phase: str = ""
    previous_target: tuple[str, str] | None = None
    previous_risky_low_hp: bool = False
    previous_position: tuple[int, int] | None = None
    previous_hp: int = 100
    previous_heart: int = 0
    previous_resources: int = 0


class _CogsguardTrajectorySampler(SimulatorEventHandler):
    def __init__(self, policy_env_info: PolicyEnvInterface, sample_every: int) -> None:
        super().__init__()
        self._policy_env_info = policy_env_info
        self._sample_every = sample_every
        self._state_adapter = CogsguardStateAdapter()
        self._team_id: str | None = None
        self._hub_position: tuple[int, int] = (0, 0)
        self._checkpoints: list[TrajectoryCheckpoint] = []
        self._milestones = TrajectoryMilestones()
        self._previous_positions: dict[int, tuple[int, int]] = {}
        self._stationary_streaks: dict[int, int] = {}
        self._far_enemy_junctions_seen: set[tuple[int, int]] = set()
        self._far_neutral_junctions_seen: set[tuple[int, int]] = set()
        self._hub_relative_junctions: dict[tuple[int, int], str | None] = {}
        self._cumulative_low_hp_steps = 0
        self._cumulative_risky_low_hp_steps = 0
        self._cumulative_payload_risk_steps = 0
        self._agent_motifs: dict[int, _AgentMotifTracker] = {}

    def on_episode_start(self) -> None:
        super().on_episode_start()
        self._team_id = None
        self._hub_position = (0, 0)
        self._checkpoints.clear()
        self._milestones = TrajectoryMilestones()
        self._previous_positions.clear()
        self._stationary_streaks.clear()
        self._far_enemy_junctions_seen.clear()
        self._far_neutral_junctions_seen.clear()
        self._hub_relative_junctions.clear()
        self._cumulative_low_hp_steps = 0
        self._cumulative_risky_low_hp_steps = 0
        self._cumulative_payload_risk_steps = 0
        self._agent_motifs.clear()

    def on_step(self) -> None:
        super().on_step()
        step = self._sim.current_step
        states = self._collect_states(step)
        self._update_stationary_streaks(states)
        self._update_team_id(states)
        self._update_hub_position(states)
        self._update_pressure_observations(states)
        self._update_hub_relative_junctions(states)
        self._update_low_hp_exposure(states)
        self._update_agent_motifs(states)
        self._update_milestones(step, states)
        if step in _MANDATORY_CHECKPOINT_STEPS or step % self._sample_every == 0 or self._sim.is_done():
            self._checkpoints.append(self._build_checkpoint(step, states))

    @property
    def checkpoints(self) -> list[TrajectoryCheckpoint]:
        return list(self._checkpoints)

    @property
    def milestones(self) -> TrajectoryMilestones:
        return self._milestones.model_copy(deep=True)

    @property
    def team_id(self) -> str:
        if self._team_id is None:
            raise ValueError("team_id requested before trajectory sampling completed")
        return self._team_id

    @property
    def agent_motifs(self) -> list[AgentMotifSummary]:
        return [
            AgentMotifSummary(
                agent_id=agent_id,
                declared_role=tracker.declared_role,
                role_switches=tracker.role_switches,
                gear_loss_events=tracker.gear_loss_events,
                regear_events=tracker.regear_events,
                avg_regear_delay=_safe_ratio(sum(tracker.regear_delays), len(tracker.regear_delays)),
                total_gearless_steps=tracker.total_gearless_steps,
                longest_gearless_stretch=tracker.longest_gearless_stretch,
                target_switches=tracker.target_switches,
                target_abandonments=tracker.target_abandonments,
                target_progress_steps=tracker.target_progress_steps,
                target_regress_steps=tracker.target_regress_steps,
                target_stall_steps=tracker.target_stall_steps,
                risky_low_hp_steps=tracker.risky_low_hp_steps,
                risky_low_hp_episodes=tracker.risky_low_hp_episodes,
                avg_retreat_resolution=_safe_ratio(
                    sum(tracker.retreat_resolution_delays),
                    len(tracker.retreat_resolution_delays),
                ),
                heart_seek_episodes=tracker.heart_seek_episodes,
                avg_heart_seek_delay=_safe_ratio(
                    sum(tracker.heart_seek_delays),
                    len(tracker.heart_seek_delays),
                ),
                avg_heart_to_use_delay=_safe_ratio(
                    sum(tracker.heart_to_use_delays),
                    len(tracker.heart_to_use_delays),
                ),
                max_hearts_carried=tracker.max_hearts_carried,
                likely_respawns=tracker.likely_respawns,
                gearless_unaffordable_steps=tracker.gearless_unaffordable_steps,
                heart_starved_steps=tracker.heart_starved_steps,
                payload_risk_steps=tracker.payload_risk_steps,
                payload_loss_events=tracker.payload_loss_events,
                payload_loss_hearts=tracker.payload_loss_hearts,
                payload_loss_resources=tracker.payload_loss_resources,
            )
            for agent_id, tracker in sorted(self._agent_motifs.items())
        ]

    def _collect_states(self, step: int):
        return [
            self._state_adapter.build_state(
                ObservationEnvelope(
                    raw_observation=self._sim.agent(agent_id).observation,
                    policy_env_info=self._policy_env_info,
                    step=step,
                )
            )
            for agent_id in range(self._sim.num_agents)
        ]

    def _update_stationary_streaks(self, states) -> None:
        for agent_id, state in enumerate(states):
            position = (
                int(state.self_state.attributes["global_x"]),
                int(state.self_state.attributes["global_y"]),
            )
            previous = self._previous_positions.get(agent_id)
            if previous == position:
                self._stationary_streaks[agent_id] = self._stationary_streaks.get(agent_id, 0) + 1
            else:
                self._stationary_streaks[agent_id] = 0
            self._previous_positions[agent_id] = position

    def _update_team_id(self, states) -> None:
        if self._team_id is None:
            self._team_id = states[0].team_summary.team_id

    def _update_hub_position(self, states) -> None:
        for state in states:
            for entity in state.visible_entities:
                if entity.entity_type != "hub":
                    continue
                if "friendly" not in entity.labels:
                    continue
                self._hub_position = (int(entity.attributes["global_x"]), int(entity.attributes["global_y"]))
                return

    def _update_pressure_observations(self, states) -> None:
        team_id = self._team_id or states[0].team_summary.team_id
        enemy_team = _enemy_team_id(team_id)
        for state in states:
            for entity in state.visible_entities:
                if entity.entity_type != "junction":
                    continue
                position = (int(entity.attributes["global_x"]), int(entity.attributes["global_y"]))
                if _manhattan(position, self._hub_position) < _FAR_JUNCTION_DISTANCE:
                    continue
                owner = entity.attributes.get("owner")
                if owner == enemy_team:
                    self._far_enemy_junctions_seen.add(position)
                if owner in {None, "neutral"}:
                    self._far_neutral_junctions_seen.add(position)

    def _update_hub_relative_junctions(self, states) -> None:
        for agent_id, state in enumerate(states):
            hub_position = _hub_position_for_agent(agent_id, state)
            if hub_position is None:
                continue
            for entity in state.visible_entities:
                if entity.entity_type != "junction":
                    continue
                rel_position = (
                    int(entity.attributes["global_x"]) - hub_position[0],
                    int(entity.attributes["global_y"]) - hub_position[1],
                )
                owner = entity.attributes.get("owner")
                self._hub_relative_junctions[rel_position] = None if owner in {None, "neutral"} else str(owner)

    def _update_low_hp_exposure(self, states) -> None:
        for agent_id, state in enumerate(states):
            role = state.self_state.role if state.self_state.role in _ROLE_HP_THRESHOLDS else "unknown"
            hp = _inventory_amount(state, "hp")
            if hp > _ROLE_HP_THRESHOLDS[role]:
                continue
            self._cumulative_low_hp_steps += 1
            safe_distance = _safe_depot_distance(agent_id, state)
            if safe_distance > 2:
                self._cumulative_risky_low_hp_steps += 1

    def _update_agent_motifs(self, states) -> None:
        policy_infos = self._sim._context.get("policy_infos", {})
        for agent_id, state in enumerate(states):
            tracker = self._agent_motifs.setdefault(agent_id, _AgentMotifTracker())
            role = _declared_role(agent_id, state, policy_infos)
            phase = str(policy_infos.get(agent_id, {}).get("phase", "")).strip()
            if tracker.previous_declared_role and tracker.previous_declared_role != role:
                tracker.role_switches += 1
            tracker.declared_role = role
            has_gear = state.self_state.role != "unknown"
            hp = _inventory_amount(state, "hp")
            hearts = _inventory_amount(state, "heart")
            resources = _carried_resource_total(state)
            position = (int(state.self_state.attributes["global_x"]), int(state.self_state.attributes["global_y"]))
            safe_distance = _safe_depot_distance(agent_id, state)
            risky_low_hp = hp <= _ROLE_HP_THRESHOLDS[role] and safe_distance > 2
            payload_at_risk = risky_low_hp and (hearts > 0 or resources > 0)
            target_signature = _target_signature(policy_infos.get(agent_id))
            previous_target_position = _target_position_from_signature(tracker.previous_target)
            current_target_position = _target_position_from_signature(target_signature)

            if tracker.previous_has_gear and not has_gear:
                tracker.gear_loss_events += 1
                tracker.gearless_start_step = self._sim.current_step
                if hp >= 90 and _near_bootstrap_hub(agent_id, position):
                    tracker.likely_respawns += 1
                if tracker.previous_heart > 0 or tracker.previous_resources > 0:
                    tracker.payload_loss_events += 1
                    tracker.payload_loss_hearts += tracker.previous_heart
                    tracker.payload_loss_resources += tracker.previous_resources
            if not tracker.previous_has_gear and has_gear:
                tracker.regear_events += 1
                if tracker.gearless_start_step is not None:
                    tracker.regear_delays.append(self._sim.current_step - tracker.gearless_start_step)
                tracker.gearless_start_step = None
            if not has_gear:
                tracker.total_gearless_steps += 1
                if role != "unknown" and not _team_can_afford_gear(state, role):
                    tracker.gearless_unaffordable_steps += 1
                if tracker.gearless_start_step is None:
                    tracker.gearless_start_step = self._sim.current_step
                tracker.longest_gearless_stretch = max(
                    tracker.longest_gearless_stretch,
                    self._sim.current_step - tracker.gearless_start_step + 1,
                )
            if (
                tracker.previous_target is not None
                and target_signature is not None
                and tracker.previous_target != target_signature
            ):
                tracker.target_switches += 1
            if (
                tracker.previous_target is not None
                and tracker.previous_position is not None
                and tracker.previous_target != target_signature
                and previous_target_position is not None
                and _manhattan(tracker.previous_position, previous_target_position) > 1
            ):
                tracker.target_abandonments += 1
            if (
                tracker.previous_target is not None
                and target_signature is not None
                and tracker.previous_target == target_signature
                and tracker.previous_position is not None
                and current_target_position is not None
            ):
                previous_distance = _manhattan(tracker.previous_position, current_target_position)
                current_distance = _manhattan(position, current_target_position)
                if current_distance < previous_distance:
                    tracker.target_progress_steps += 1
                elif current_distance > previous_distance:
                    tracker.target_regress_steps += 1
                else:
                    tracker.target_stall_steps += 1
            if risky_low_hp:
                tracker.risky_low_hp_steps += 1
                if payload_at_risk:
                    tracker.payload_risk_steps += 1
                    self._cumulative_payload_risk_steps += 1
                if not tracker.previous_risky_low_hp:
                    tracker.risky_low_hp_episodes += 1
                    tracker.retreat_start_step = self._sim.current_step
            elif tracker.previous_risky_low_hp and tracker.retreat_start_step is not None:
                tracker.retreat_resolution_delays.append(self._sim.current_step - tracker.retreat_start_step)
                tracker.retreat_start_step = None

            previous_heart = getattr(tracker, "previous_heart", 0)
            if hearts > previous_heart:
                tracker.effective_heart_gains += hearts - previous_heart
            if hearts < previous_heart:
                tracker.effective_heart_spends += previous_heart - hearts
            if role in {"aligner", "scrambler"}:
                tracker.max_hearts_carried = max(tracker.max_hearts_carried, hearts)
                if phase == "hearts" and hearts <= 0 and tracker.heart_seek_start_step is None:
                    tracker.heart_seek_episodes += 1
                    tracker.heart_seek_start_step = self._sim.current_step
                if phase == "hearts" and hearts <= 0 and not _team_can_refill_hearts(state):
                    tracker.heart_starved_steps += 1
                elif hearts > 0 and tracker.heart_seek_start_step is not None:
                    tracker.heart_seek_delays.append(self._sim.current_step - tracker.heart_seek_start_step)
                    tracker.heart_seek_start_step = None
                elif phase not in {"", "hearts"} and hearts <= 0 and tracker.heart_seek_start_step is not None:
                    tracker.heart_seek_start_step = None
            if role in {"aligner", "scrambler"} and previous_heart <= 0 and hearts > 0:
                tracker.heart_hold_start_step = self._sim.current_step
            if (
                role in {"aligner", "scrambler"}
                and hearts < previous_heart
                and tracker.heart_hold_start_step is not None
            ):
                tracker.heart_to_use_delays.append(self._sim.current_step - tracker.heart_hold_start_step)
                tracker.heart_hold_start_step = self._sim.current_step if hearts > 0 else None

            tracker.previous_has_gear = has_gear
            tracker.previous_declared_role = role
            tracker.previous_phase = phase
            tracker.previous_target = target_signature
            tracker.previous_risky_low_hp = risky_low_hp
            tracker.previous_position = position
            tracker.previous_hp = hp
            tracker.previous_heart = hearts
            tracker.previous_resources = resources

    def _update_milestones(self, step: int, states) -> None:
        equipped_roles = _equipped_role_counts(states)
        if self._milestones.first_miner_gear_step is None and equipped_roles.miner > 0:
            self._milestones.first_miner_gear_step = step
        if self._milestones.first_aligner_gear_step is None and equipped_roles.aligner > 0:
            self._milestones.first_aligner_gear_step = step
        if self._milestones.first_scrambler_gear_step is None and equipped_roles.scrambler > 0:
            self._milestones.first_scrambler_gear_step = step
        if self._milestones.first_heart_carried_step is None and any(
            _inventory_amount(state, "heart") > 0 for state in states
        ):
            self._milestones.first_heart_carried_step = step

        team_id = self._team_id or states[0].team_summary.team_id
        enemy_team = _enemy_team_id(team_id)
        game_stats = self._sim.episode_stats["game"]

        if (
            self._milestones.first_heart_withdrawal_step is None
            and _game_stat_value(game_stats, f"{team_id}/heart.withdrawn") > 0
        ):
            self._milestones.first_heart_withdrawal_step = step
        if (
            self._milestones.first_alignment_step is None
            and _game_stat_value(game_stats, f"{team_id}/aligned.junction.gained") > 0
        ):
            self._milestones.first_alignment_step = step
        if (
            self._milestones.first_scramble_step is None
            and _game_stat_value(game_stats, f"{enemy_team}/aligned.junction.lost") > 0
        ):
            self._milestones.first_scramble_step = step

    def _build_checkpoint(self, step: int, states) -> TrajectoryCheckpoint:
        team_id = self._team_id or states[0].team_summary.team_id
        enemy_team = _enemy_team_id(team_id)
        game_stats = self._sim.episode_stats["game"]
        rewards = self._sim.episode_rewards
        frontier_neutrals, best_frontier_coverage, best_enemy_scramble_block = _frontier_metrics(
            team_id=team_id,
            enemy_team=enemy_team,
            hub_relative_junctions=self._hub_relative_junctions,
        )
        aligner_target_collisions, unique_aligner_targets = _aligner_target_overlap(
            self._sim._context.get("policy_infos", {})
        )
        hub_zone_agents, hub_queue_agents = _hub_queue_pressure(
            states=states,
            policy_infos=self._sim._context.get("policy_infos", {}),
            hub_position=self._hub_position,
        )
        low_hp_agents, risky_low_hp_agents = _current_low_hp_counts(states)
        payload_risk_agents = sum(1 for agent_id, state in enumerate(states) if _current_payload_risk(agent_id, state))
        effective_heart_gains = sum(tracker.effective_heart_gains for tracker in self._agent_motifs.values())
        effective_heart_spends = sum(tracker.effective_heart_spends for tracker in self._agent_motifs.values())
        gearless_unaffordable_agents = sum(
            1
            for agent_id, state in enumerate(states)
            if state.self_state.role == "unknown"
            and _declared_role(agent_id, state, self._sim._context.get("policy_infos", {})) != "unknown"
            and not _team_can_afford_gear(
                state,
                _declared_role(agent_id, state, self._sim._context.get("policy_infos", {})),
            )
        )
        heart_starved_agents = sum(
            1
            for agent_id, state in enumerate(states)
            if _declared_role(agent_id, state, self._sim._context.get("policy_infos", {})) in {"aligner", "scrambler"}
            and _inventory_amount(state, "heart") <= 0
            and str(self._sim._context.get("policy_infos", {}).get(agent_id, {}).get("phase", "")).strip() == "hearts"
            and not _team_can_refill_hearts(state)
        )
        pressure_budget = _policy_info_shared_int(self._sim._context.get("policy_infos", {}), "pressure_budget")
        heart_supply_capacity = _policy_info_shared_int(self._sim._context.get("policy_infos", {}), "heart_supply")
        declared_roles = _declared_role_counts(states, self._sim._context.get("policy_infos", {}))
        pressure_oversubscription = max(
            0,
            declared_roles.aligner + declared_roles.scrambler - pressure_budget,
        )
        team_inventory = _resource_vector_from_game_stats(game_stats, prefix=f"{team_id}/", suffix="amount")
        return TrajectoryCheckpoint(
            step=step,
            avg_reward_per_agent=float(sum(rewards) / len(rewards)),
            aligned_junctions=int(_game_stat_value(game_stats, f"{team_id}/aligned.junction")),
            aligned_junctions_gained=int(_game_stat_value(game_stats, f"{team_id}/aligned.junction.gained")),
            aligned_junction_held=_game_stat_value(game_stats, f"{team_id}/aligned.junction.held"),
            enemy_aligned_junction_held=_game_stat_value(game_stats, f"{enemy_team}/aligned.junction.held"),
            control_per_heart_withdrawn=_safe_ratio(
                _game_stat_value(game_stats, f"{team_id}/aligned.junction.held"),
                _game_stat_value(game_stats, f"{team_id}/heart.withdrawn"),
            ),
            effective_heart_gains=effective_heart_gains,
            effective_heart_spends=effective_heart_spends,
            affordable_hearts_in_bank=team_inventory.min_element() // 7,
            control_per_heart_gain=_safe_ratio(
                _game_stat_value(game_stats, f"{team_id}/aligned.junction.held"),
                effective_heart_gains,
            ),
            control_per_heart_spend=_safe_ratio(
                _game_stat_value(game_stats, f"{team_id}/aligned.junction.held"),
                effective_heart_spends,
            ),
            control_per_alignment_gain=_safe_ratio(
                _game_stat_value(game_stats, f"{team_id}/aligned.junction.held"),
                _game_stat_value(game_stats, f"{team_id}/aligned.junction.gained"),
            ),
            team_inventory=team_inventory,
            team_deposits=_resource_vector_from_game_stats(game_stats, prefix=f"{team_id}/", suffix="deposited"),
            team_withdrawals=_resource_vector_from_game_stats(game_stats, prefix=f"{team_id}/", suffix="withdrawn"),
            equipped_roles=_equipped_role_counts(states),
            declared_roles=declared_roles,
            role_max_hub_distance=_role_max_hub_distance(
                states,
                self._sim._context.get("policy_infos", {}),
                hub_position=self._hub_position,
            ),
            carrying_hearts=sum(1 for state in states if _inventory_amount(state, "heart") > 0),
            carrying_resources=sum(_carried_resource_total(state) for state in states),
            stationary_agents=sum(1 for streak in self._stationary_streaks.values() if streak > 0),
            max_stationary_streak=max(self._stationary_streaks.values(), default=0),
            far_enemy_junctions_seen=len(self._far_enemy_junctions_seen),
            far_neutral_junctions_seen=len(self._far_neutral_junctions_seen),
            frontier_neutral_junctions=frontier_neutrals,
            best_frontier_coverage=best_frontier_coverage,
            best_enemy_scramble_block=best_enemy_scramble_block,
            heart_supply_capacity=heart_supply_capacity,
            pressure_budget=pressure_budget,
            pressure_oversubscription=pressure_oversubscription,
            aligner_target_collisions=aligner_target_collisions,
            unique_aligner_targets=unique_aligner_targets,
            hub_zone_agents=hub_zone_agents,
            hub_queue_agents=hub_queue_agents,
            low_hp_agents=low_hp_agents,
            risky_low_hp_agents=risky_low_hp_agents,
            payload_risk_agents=payload_risk_agents,
            gearless_unaffordable_agents=gearless_unaffordable_agents,
            heart_starved_agents=heart_starved_agents,
            cumulative_low_hp_steps=self._cumulative_low_hp_steps,
            cumulative_risky_low_hp_steps=self._cumulative_risky_low_hp_steps,
            cumulative_payload_risk_steps=self._cumulative_payload_risk_steps,
        )


def analyze_cogsguard_policy(
    *,
    mission_name: str,
    policy_spec: PolicySpec,
    cogs: int = 8,
    steps: int = 10_000,
    seed: int = 42,
    sample_every: int = 100,
    max_action_time_ms: int = 10_000,
) -> TrajectoryReport:
    _, env_cfg, _ = get_mission(mission_name, cogs=cogs, steps=steps)
    env_for_rollout = resolve_env_for_seed(env_cfg, seed)
    policy_env_info = PolicyEnvInterface.from_mg_cfg(env_for_rollout)
    multi_policy = initialize_or_load_policy(policy_env_info, policy_spec, device_override="cpu")
    agent_policies = [multi_policy.agent_policy(agent_id) for agent_id in range(env_for_rollout.game.num_agents)]
    sampler = _CogsguardTrajectorySampler(policy_env_info, sample_every=sample_every)
    rollout = Rollout(
        env_for_rollout,
        agent_policies,
        policy_names=[policy_spec.name] * len(agent_policies),
        max_action_time_ms=max_action_time_ms,
        render_mode="none",
        seed=seed,
        event_handlers=[sampler],
    )
    rollout.run_until_done()
    game_stats = rollout._sim.episode_stats["game"]
    rewards = rollout._sim.episode_rewards
    team_prefix = sampler.team_id
    report = TrajectoryReport(
        policy_name=policy_spec.name,
        mission_name=mission_name,
        seed=seed,
        steps=rollout._sim.current_step,
        avg_reward_per_agent=float(sum(rewards) / len(rewards)),
        avg_deaths_per_agent=_average_agent_metric(rollout._sim.episode_stats, "death"),
        final_aligned_junctions=int(_game_stat_value(game_stats, f"{team_prefix}/aligned.junction")),
        final_aligned_junction_held=_game_stat_value(game_stats, f"{team_prefix}/aligned.junction.held"),
        final_enemy_aligned_junction_held=_game_stat_value(
            game_stats, f"{_enemy_team_id(team_prefix)}/aligned.junction.held"
        ),
        plateau_step=_plateau_step(sampler.checkpoints),
        agent_motifs=sampler.agent_motifs,
        checkpoints=sampler.checkpoints,
        milestones=sampler.milestones,
    )
    report.insights.extend(_derive_cogsguard_insights(report))
    return report


def compare_cogsguard_policies(
    *,
    mission_name: str,
    policy_specs: list[PolicySpec],
    cogs: int = 8,
    steps: int = 10_000,
    seed: int = 42,
    sample_every: int = 100,
    max_action_time_ms: int = 10_000,
) -> TrajectoryComparison:
    return TrajectoryComparison(
        mission_name=mission_name,
        seed=seed,
        reports=[
            analyze_cogsguard_policy(
                mission_name=mission_name,
                policy_spec=policy_spec,
                cogs=cogs,
                steps=steps,
                seed=seed,
                sample_every=sample_every,
                max_action_time_ms=max_action_time_ms,
            )
            for policy_spec in policy_specs
        ],
    )


def render_trajectory_report(report: TrajectoryReport) -> str:
    milestone_lines = [
        f"miner_gear={_format_milestone(report.milestones.first_miner_gear_step)}",
        f"aligner_gear={_format_milestone(report.milestones.first_aligner_gear_step)}",
        f"heart_withdraw={_format_milestone(report.milestones.first_heart_withdrawal_step)}",
        f"first_alignment={_format_milestone(report.milestones.first_alignment_step)}",
        f"first_scramble={_format_milestone(report.milestones.first_scramble_step)}",
    ]
    lines = [
        f"{report.policy_name}: reward={report.avg_reward_per_agent:.4f} "
        f"deaths={report.avg_deaths_per_agent:.3f} "
        f"held={report.final_aligned_junction_held:.0f} "
        f"enemy_held={report.final_enemy_aligned_junction_held:.0f} "
        f"plateau={_format_milestone(report.plateau_step)}",
        "milestones: " + ", ".join(milestone_lines),
    ]
    for checkpoint in report.checkpoints:
        lines.append(
            f"step {checkpoint.step:>5}: held={checkpoint.aligned_junction_held:>8.0f} "
            f"enemy_held={checkpoint.enemy_aligned_junction_held:>8.0f} "
            f"bank={checkpoint.team_inventory.element_total():>4} "
            f"afford_hearts={checkpoint.affordable_hearts_in_bank:>3} "
            f"deposited={checkpoint.team_deposits.element_total():>4} "
            f"heart_gain/spend={checkpoint.effective_heart_gains:>3}/{checkpoint.effective_heart_spends:>3} "
            f"raw_withdraw={checkpoint.team_withdrawals.heart:>3} "
            f"control_per_heart={checkpoint.control_per_heart_spend:>7.1f} "
            f"control_per_align={checkpoint.control_per_alignment_gain:>7.1f} "
            f"frontier={checkpoint.frontier_neutral_junctions:>2} "
            f"best_cover={checkpoint.best_frontier_coverage:>2} "
            f"best_scramble={checkpoint.best_enemy_scramble_block:>2} "
            f"heart_supply={checkpoint.heart_supply_capacity:>2} "
            f"pressure={checkpoint.pressure_budget:>2}/{checkpoint.pressure_oversubscription:>2} "
            f"aligner_collisions={checkpoint.aligner_target_collisions:>2} "
            f"hub_queue={checkpoint.hub_queue_agents:>2}/{checkpoint.hub_zone_agents:>2} "
            f"far_enemy={checkpoint.far_enemy_junctions_seen:>2} "
            f"scrambler_range={checkpoint.role_max_hub_distance.scrambler:>3} "
            f"risky_hp={checkpoint.risky_low_hp_agents:>2}/{checkpoint.low_hp_agents:>2} "
            f"cum_risky_hp={checkpoint.cumulative_risky_low_hp_steps:>4} "
            f"payload_risk={checkpoint.payload_risk_agents:>2}/{checkpoint.cumulative_payload_risk_steps:>4} "
            f"gear_blocked={checkpoint.gearless_unaffordable_agents:>2} "
            f"heart_starved={checkpoint.heart_starved_agents:>2} "
            f"declared={checkpoint.declared_roles.model_dump()} "
            f"equipped={checkpoint.equipped_roles.model_dump()} "
            f"stall={checkpoint.max_stationary_streak:>3}"
        )
    if report.insights:
        lines.append("insights:")
        lines.extend(f"- {insight}" for insight in report.insights)
    if report.agent_motifs:
        lines.append("motifs:")
        for motif in sorted(
            report.agent_motifs,
            key=lambda item: (
                item.role_switches,
                item.total_gearless_steps,
                item.risky_low_hp_steps,
                item.target_abandonments,
                item.target_switches,
                item.agent_id,
            ),
            reverse=True,
        )[:4]:
            lines.append(
                f"- agent {motif.agent_id} role={motif.declared_role} "
                f"role_switches={motif.role_switches} "
                f"gearless={motif.total_gearless_steps}/{motif.longest_gearless_stretch} "
                f"regear_avg={motif.avg_regear_delay:.1f} "
                f"switches={motif.target_switches}/{motif.target_abandonments} "
                f"pursuit={motif.target_progress_steps}/{motif.target_regress_steps}/{motif.target_stall_steps} "
                f"risky_hp={motif.risky_low_hp_steps}/{motif.risky_low_hp_episodes} "
                f"retreat_avg={motif.avg_retreat_resolution:.1f} "
                f"heart_seek={motif.avg_heart_seek_delay:.1f}/{motif.heart_seek_episodes} "
                f"heart_avg={motif.avg_heart_to_use_delay:.1f} "
                f"gear_blocked={motif.gearless_unaffordable_steps} "
                f"heart_starved={motif.heart_starved_steps} "
                f"payload_risk={motif.payload_risk_steps} "
                f"payload_loss={motif.payload_loss_events}:{motif.payload_loss_hearts}/{motif.payload_loss_resources} "
                f"max_hearts={motif.max_hearts_carried} "
                f"respawns={motif.likely_respawns}"
            )
    return "\n".join(lines)


def render_trajectory_comparison(comparison: TrajectoryComparison) -> str:
    return "\n\n".join(render_trajectory_report(report) for report in comparison.reports)


def _resource_vector_from_game_stats(game_stats: dict[str, float], *, prefix: str, suffix: str) -> ResourceVector:
    return ResourceVector(
        carbon=int(_game_stat_value(game_stats, f"{prefix}carbon.{suffix}")),
        oxygen=int(_game_stat_value(game_stats, f"{prefix}oxygen.{suffix}")),
        germanium=int(_game_stat_value(game_stats, f"{prefix}germanium.{suffix}")),
        silicon=int(_game_stat_value(game_stats, f"{prefix}silicon.{suffix}")),
        heart=int(_game_stat_value(game_stats, f"{prefix}heart.{suffix}")),
        influence=int(_game_stat_value(game_stats, f"{prefix}influence.{suffix}")),
        solar=int(_game_stat_value(game_stats, f"{prefix}solar.{suffix}")),
    )


def _equipped_role_counts(states) -> RoleCounts:
    counter = Counter(state.self_state.role for state in states)
    return RoleCounts(
        miner=counter["miner"],
        aligner=counter["aligner"],
        scrambler=counter["scrambler"],
        scout=counter["scout"],
        unknown=counter["unknown"],
    )


def _declared_role_counts(states, policy_infos: dict[int, dict]) -> RoleCounts:
    counter: Counter[str] = Counter()
    for agent_id, state in enumerate(states):
        counter[_declared_role(agent_id, state, policy_infos)] += 1
    return RoleCounts(
        miner=counter["miner"],
        aligner=counter["aligner"],
        scrambler=counter["scrambler"],
        scout=counter["scout"],
        unknown=counter["unknown"],
    )


def _carried_resource_total(state) -> int:
    return sum(_inventory_amount(state, resource) for resource in _RESOURCE_NAMES)


def _inventory_amount(state, item: str) -> int:
    value = state.self_state.inventory.get(item)
    return 0 if value is None else int(value)


def _game_stat_value(game_stats: dict[str, float], key: str) -> float:
    value = game_stats.get(key)
    return 0.0 if value is None else float(value)


def _average_agent_metric(episode_stats: dict, metric_name: str) -> float:
    agent_stats = episode_stats.get("agent", [])
    if not agent_stats:
        return 0.0
    values = [float(agent.get(metric_name, 0.0)) for agent in agent_stats]
    return sum(values) / len(values)


def _declared_role(agent_id: int, state, policy_infos: dict[int, dict]) -> str:
    role = state.self_state.role
    if agent_id in policy_infos and "role" in policy_infos[agent_id]:
        role = str(policy_infos[agent_id]["role"])
    if role not in _ROLE_NAMES:
        return "unknown"
    return role


def _role_max_hub_distance(
    states,
    policy_infos: dict[int, dict],
    *,
    hub_position: tuple[int, int],
) -> RoleDistanceSummary:
    max_distances = {role: 0 for role in [*_ROLE_NAMES, "unknown"]}
    for agent_id, state in enumerate(states):
        role = _declared_role(agent_id, state, policy_infos)
        position = (int(state.self_state.attributes["global_x"]), int(state.self_state.attributes["global_y"]))
        max_distances[role] = max(max_distances[role], _manhattan(position, hub_position))
    return RoleDistanceSummary(**max_distances)


def _policy_info_shared_int(policy_infos: dict[int, dict], key: str) -> int:
    for info in policy_infos.values():
        if key in info:
            return int(info[key])
    return 0


def _enemy_team_id(team_id: str) -> str:
    return "clips" if team_id == "cogs" else "cogs"


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _derive_cogsguard_insights(report: TrajectoryReport) -> list[str]:
    if not report.checkpoints:
        return []

    insights: list[str] = []
    early = _latest_checkpoint_before(report.checkpoints, 250)
    mid = _latest_checkpoint_before(report.checkpoints, 1000)
    late = report.checkpoints[-1]

    if (
        early is not None
        and early.team_deposits.element_total() < 600
        and early.declared_roles.aligner >= early.declared_roles.miner
    ):
        insights.append(
            "Opening pressure is overcommitted to aligners before the economy is online; "
            "early deposits are too low for the role mix."
        )
    if early is not None and early.effective_heart_gains == 0:
        insights.append(
            "The first 250 steps are not producing hearts yet; "
            "the opening economy is not converting into scoring pressure."
        )
    if (
        mid is not None
        and mid.aligned_junction_held < 20_000
        and mid.team_inventory.min_element() > 200
        and mid.effective_heart_gains < 20
    ):
        insights.append(
            "By step 1000 the team is banking resources but not turning that bank into carried hearts; "
            "heart acquisition throughput is lagging the economy."
        )
    if mid is not None and mid.effective_heart_spends >= 20 and mid.control_per_heart_spend < 350:
        insights.append(
            "By step 1000 the team is already spending hearts, but each spent heart is producing too little control; "
            "alignment throughput is the bottleneck, not raw heart access."
        )
    if early is not None and early.pressure_oversubscription > 0:
        insights.append(
            "Early pressure roles exceed the budget suggested by the visible heart economy; "
            "the opening is overcommitting heart-dependent jobs."
        )
    if (
        mid is not None
        and late.team_inventory.element_total() > mid.team_inventory.element_total() + 500
        and late.aligned_junction_held < mid.aligned_junction_held + 10_000
    ):
        insights.append(
            "The late game is stagnating: banked resources continue rising while held control grows too slowly."
        )
    if late.control_per_heart_spend > 0 and late.control_per_heart_spend < 400:
        insights.append(
            "Heart-to-control efficiency is low; hearts are being spread across too many "
            "or too-shallow alignment attempts."
        )
    if late.pressure_oversubscription > 0 and late.heart_supply_capacity <= late.pressure_budget:
        insights.append(
            "Late pressure demand still exceeds the economy-backed budget; too many agents are chasing "
            "heart-dependent work for the available heart supply."
        )
    if late.best_frontier_coverage >= 3 and late.control_per_alignment_gain < 500:
        insights.append(
            "Known frontier junctions would open substantially more neutral territory than the current "
            "conversion rate suggests; target selection is still too distance-biased."
        )
    if late.declared_roles.scrambler == 0 and late.enemy_aligned_junction_held > late.aligned_junction_held:
        insights.append(
            "There is no dedicated late-game scramble pressure despite losing the control race; "
            "convert 1-2 agents once the economy is established."
        )
    if late.best_enemy_scramble_block >= 3 and late.declared_roles.scrambler < 1:
        insights.append(
            "Enemy-held junctions are blocking large neutral regions, but there is no dedicated scramble pressure "
            "aimed at those high-leverage targets."
        )
    if late.far_enemy_junctions_seen > 0 and late.declared_roles.scrambler == 0:
        insights.append(
            "Far enemy junctions are being discovered, but no role is dedicated to "
            "turning that map knowledge into scramble pressure."
        )
    if late.declared_roles.scrambler > 0 and late.role_max_hub_distance.scrambler < _FAR_JUNCTION_DISTANCE:
        insights.append(
            "Declared scramblers are not ranging far enough from hub to pressure corners and outer enemy junctions."
        )
    if late.equipped_roles.unknown >= max(4, late.declared_roles.aligner + late.declared_roles.scrambler):
        insights.append(
            "Late-game gear uptime is collapsing; too many agents have a declared job but no equipped role, "
            "so regear/recovery is now part of the control problem."
        )
    if late.max_stationary_streak >= 20:
        insights.append(
            "Long stationary streaks remain a material control issue; "
            "navigation reset / target refresh is still costing control."
        )
    if late.cumulative_risky_low_hp_steps >= 20 and report.avg_deaths_per_agent >= 0.5:
        insights.append(
            "Low-HP agents spend too many steps far from safety; deaths are likely preventable and survival "
            "discipline is leaving control on the table."
        )
    worst_gearless = max((motif.longest_gearless_stretch for motif in report.agent_motifs), default=0)
    total_role_switches = sum(motif.role_switches for motif in report.agent_motifs)
    total_respawns = sum(motif.likely_respawns for motif in report.agent_motifs)
    worst_retreat_resolution = max((motif.avg_retreat_resolution for motif in report.agent_motifs), default=0.0)
    worst_heart_seek_delay = max((motif.avg_heart_seek_delay for motif in report.agent_motifs), default=0.0)
    worst_heart_delay = max((motif.avg_heart_to_use_delay for motif in report.agent_motifs), default=0.0)
    total_target_abandonments = sum(motif.target_abandonments for motif in report.agent_motifs)
    total_target_progress_steps = sum(motif.target_progress_steps for motif in report.agent_motifs)
    total_target_regress_steps = sum(motif.target_regress_steps for motif in report.agent_motifs)
    total_target_stall_steps = sum(motif.target_stall_steps for motif in report.agent_motifs)
    total_gearless_unaffordable_steps = sum(motif.gearless_unaffordable_steps for motif in report.agent_motifs)
    total_heart_starved_steps = sum(motif.heart_starved_steps for motif in report.agent_motifs)
    total_payload_risk_steps = sum(motif.payload_risk_steps for motif in report.agent_motifs)
    total_payload_loss_events = sum(motif.payload_loss_events for motif in report.agent_motifs)
    total_payload_loss_hearts = sum(motif.payload_loss_hearts for motif in report.agent_motifs)
    total_payload_loss_resources = sum(motif.payload_loss_resources for motif in report.agent_motifs)
    worst_aligner_collisions = max(
        (checkpoint.aligner_target_collisions for checkpoint in report.checkpoints),
        default=0,
    )
    worst_hub_queue = max((checkpoint.hub_queue_agents for checkpoint in report.checkpoints), default=0)
    if worst_gearless >= 200:
        insights.append(
            "At least one agent stays gearless for a very long stretch after losing kit; replay motifs point to "
            "regear latency as a major late-game failure mode."
        )
    if late.gearless_unaffordable_agents >= 2 or total_gearless_unaffordable_steps >= 200:
        insights.append(
            "A meaningful share of gearless time is happening while the team cannot afford the intended kit; "
            "the late collapse is supply-blocked, not just a navigation problem."
        )
    elif late.equipped_roles.unknown >= max(4, late.declared_roles.aligner + late.declared_roles.scrambler):
        insights.append(
            "Most late gearlessness happens even when the team can still afford some gear; "
            "the failure mode is recovery/traffic discipline more than pure economy."
        )
    if total_respawns >= 2:
        insights.append(
            "Replay motifs show repeated likely respawns; survival and post-death recovery are still expensive enough "
            "to distort the macro loop."
        )
    if total_role_switches >= 4:
        insights.append(
            "Declared roles are flapping mid-episode; the macro schedule is not stable enough for agents to build "
            "throughput in one job."
        )
    if worst_retreat_resolution >= 40:
        insights.append(
            "Risky low-HP episodes take too long to resolve; retreat intent exists but agents are not getting back to "
            "safe regear positions quickly enough."
        )
    if worst_heart_seek_delay >= 20:
        insights.append(
            "At least one carrier spends a long time in heart-seeking mode before refilling; the policy is losing "
            "tempo to hub refill loops."
        )
    if late.heart_starved_agents >= 2 or total_heart_starved_steps >= 100:
        insights.append(
            "A noticeable slice of heart-seeking time is true supply starvation rather than pathing; "
            "the team is arriving for hearts faster than the economy can replenish them."
        )
    if worst_heart_delay >= 40:
        insights.append(
            "Some carriers hold hearts for too long before spending them; the bottleneck is no longer just heart "
            "production, but conversion latency."
        )
    if total_payload_risk_steps >= 100 or total_payload_loss_events >= 3:
        insights.append(
            "Agents are repeatedly carrying valuable payload through unsafe zones; replay motifs show that "
            "hearts/resources are being risked or lost before conversion."
        )
    if total_payload_loss_hearts >= 4 or total_payload_loss_resources >= 20:
        insights.append(
            "Deaths are wiping meaningful work-in-progress off the board; payload loss is large enough that "
            "survival improvements should translate directly into score."
        )
    if total_target_abandonments >= 8:
        insights.append(
            "Target pursuit is churning: agents are abandoning too many targets before they reach useful range, "
            "so retargeting is leaking conversion tempo."
        )
    if total_target_progress_steps < total_target_regress_steps + total_target_stall_steps:
        insights.append(
            "While targets stay constant, approach steps are not reliably making progress; replay motifs point to "
            "path churn or target-selection instability rather than pure macro shortages."
        )
    if worst_aligner_collisions >= 2:
        insights.append(
            "Multiple aligners repeatedly target the same junction at once; coordination is leaking alignment tempo."
        )
    if early is not None and early.hub_queue_agents >= 4 and early.effective_heart_gains < 20:
        insights.append(
            "The opening is crowding too many agents into the hub queue before enough hearts are being produced; "
            "home-base traffic is choking conversion tempo."
        )
    if worst_hub_queue >= 5:
        insights.append(
            "Too many agents stack in the hub zone at once; replay pressure suggests queueing and local traffic are "
            "wasting productive steps."
        )
    if report.plateau_step is not None and report.plateau_step <= max(report.steps // 3, 1):
        insights.append(
            "Held control reaches its final regime too early and then plateaus; the macro loop is not opening "
            "new territory quickly enough after the first expansion wave."
        )
    if not insights:
        insights.append(
            "Trajectory looks coherent: economy converts into hearts and control "
            "without an obvious phase-shape failure."
        )
    return insights


def _latest_checkpoint_before(
    checkpoints: list[TrajectoryCheckpoint],
    max_step: int,
) -> TrajectoryCheckpoint | None:
    eligible = [checkpoint for checkpoint in checkpoints if checkpoint.step <= max_step]
    if not eligible:
        return None
    return eligible[-1]


def _format_milestone(step: int | None) -> str:
    return "-" if step is None else str(step)


def _hub_position_for_agent(agent_id: int, state) -> tuple[int, int] | None:
    for entity in state.visible_entities:
        if entity.entity_type == "hub" and entity.attributes.get("team") == state.team_summary.team_id:
            return (int(entity.attributes["global_x"]), int(entity.attributes["global_y"]))
    return _BOOTSTRAP_HUB_OFFSETS.get(agent_id)


def _safe_depot_distance(agent_id: int, state) -> int:
    current = (int(state.self_state.attributes["global_x"]), int(state.self_state.attributes["global_y"]))
    team_id = state.team_summary.team_id
    depot_distances = []
    hub_position = _hub_position_for_agent(agent_id, state)
    if hub_position is not None:
        depot_distances.append(_manhattan(current, hub_position))
    for entity in state.visible_entities:
        if entity.entity_type == "junction" and entity.attributes.get("owner") == team_id:
            junction_position = (int(entity.attributes["global_x"]), int(entity.attributes["global_y"]))
            depot_distances.append(_manhattan(current, junction_position))
    if not depot_distances:
        return 0
    return min(depot_distances)


def _current_low_hp_counts(states) -> tuple[int, int]:
    low_hp_agents = 0
    risky_low_hp_agents = 0
    for agent_id, state in enumerate(states):
        role = state.self_state.role if state.self_state.role in _ROLE_HP_THRESHOLDS else "unknown"
        hp = _inventory_amount(state, "hp")
        if hp > _ROLE_HP_THRESHOLDS[role]:
            continue
        low_hp_agents += 1
        if _safe_depot_distance(agent_id, state) > 2:
            risky_low_hp_agents += 1
    return low_hp_agents, risky_low_hp_agents


def _current_payload_risk(agent_id: int, state) -> bool:
    role = state.self_state.role if state.self_state.role in _ROLE_HP_THRESHOLDS else "unknown"
    hp = _inventory_amount(state, "hp")
    if hp > _ROLE_HP_THRESHOLDS[role]:
        return False
    if _safe_depot_distance(agent_id, state) <= 2:
        return False
    return _inventory_amount(state, "heart") > 0 or _carried_resource_total(state) > 0


def _team_can_afford_gear(state, role: str) -> bool:
    if role not in _GEAR_COSTS or state.team_summary is None:
        return False
    inventory = state.team_summary.shared_inventory
    return all(int(inventory.get(resource, 0)) >= amount for resource, amount in _GEAR_COSTS[role].items())


def _team_can_refill_hearts(state) -> bool:
    if state.team_summary is None:
        return False
    inventory = state.team_summary.shared_inventory
    if int(inventory.get("heart", 0)) > 0:
        return True
    return all(int(inventory.get(resource, 0)) >= 7 for resource in _RESOURCE_NAMES)


def _target_signature(policy_info: dict | None) -> tuple[str, str] | None:
    if not policy_info:
        return None
    target_kind = str(policy_info.get("target_kind", "")).strip()
    target_position = str(policy_info.get("target_position", "")).strip()
    if not target_kind and not target_position:
        return None
    return (target_kind, target_position)


def _target_position_from_signature(target_signature: tuple[str, str] | None) -> tuple[int, int] | None:
    if target_signature is None:
        return None
    _, raw_position = target_signature
    x_str, separator, y_str = raw_position.partition(",")
    if separator != ",":
        return None
    try:
        return (int(x_str.strip()), int(y_str.strip()))
    except ValueError:
        return None


def _aligner_target_overlap(policy_infos: dict[int, dict]) -> tuple[int, int]:
    targets = [
        str(policy_info["target_position"])
        for policy_info in policy_infos.values()
        if policy_info.get("role") == "aligner"
        and policy_info.get("summary") == "align_junction"
        and str(policy_info.get("target_position", "")).strip()
    ]
    counts = Counter(targets)
    collisions = sum(count - 1 for count in counts.values() if count > 1)
    return collisions, len(counts)


def _hub_queue_pressure(
    *,
    states,
    policy_infos: dict[int, dict],
    hub_position: tuple[int, int],
) -> tuple[int, int]:
    zone_agents = 0
    queue_agents = 0
    for agent_id, state in enumerate(states):
        position = (int(state.self_state.attributes["global_x"]), int(state.self_state.attributes["global_y"]))
        if _manhattan(position, hub_position) > 2:
            continue
        zone_agents += 1
        phase = str(policy_infos.get(agent_id, {}).get("phase", "")).strip()
        if phase in {"hearts", "deposit", "regear", "retreat"}:
            queue_agents += 1
    return zone_agents, queue_agents


def _near_bootstrap_hub(agent_id: int, position: tuple[int, int]) -> bool:
    bootstrap = _BOOTSTRAP_HUB_OFFSETS.get(agent_id)
    if bootstrap is None:
        return False
    return _manhattan(position, bootstrap) <= 3


def _frontier_metrics(
    *,
    team_id: str,
    enemy_team: str,
    hub_relative_junctions: dict[tuple[int, int], str | None],
) -> tuple[int, int, int]:
    friendly_junctions = {rel for rel, owner in hub_relative_junctions.items() if owner == team_id}
    neutral_junctions = {rel for rel, owner in hub_relative_junctions.items() if owner in {None, "neutral"}}
    enemy_junctions = {rel for rel, owner in hub_relative_junctions.items() if owner == enemy_team}
    sources = {(0, 0), *friendly_junctions}
    frontier_neutrals = {rel for rel in neutral_junctions if _within_relative_alignment_network(rel, sources)}
    unreachable_neutrals = neutral_junctions - frontier_neutrals
    best_frontier_coverage = max(
        (
            sum(
                1
                for neutral in unreachable_neutrals
                if neutral != candidate and _manhattan(candidate, neutral) <= _JUNCTION_ALIGN_DISTANCE
            )
            for candidate in frontier_neutrals
        ),
        default=0,
    )
    best_enemy_scramble_block = max(
        (
            sum(1 for neutral in neutral_junctions if _manhattan(enemy, neutral) <= _JUNCTION_AOE_RANGE)
            for enemy in enemy_junctions
        ),
        default=0,
    )
    return len(frontier_neutrals), best_frontier_coverage, best_enemy_scramble_block


def _within_relative_alignment_network(
    candidate: tuple[int, int],
    sources: set[tuple[int, int]],
) -> bool:
    for source in sources:
        max_distance = _HUB_ALIGN_DISTANCE if source == (0, 0) else _JUNCTION_ALIGN_DISTANCE
        if _manhattan(candidate, source) <= max_distance:
            return True
    return False


def _plateau_step(checkpoints: list[TrajectoryCheckpoint]) -> int | None:
    if not checkpoints:
        return None
    final_held = checkpoints[-1].aligned_junction_held
    if final_held <= 0:
        return None
    threshold = final_held * 0.9
    for checkpoint in checkpoints:
        if checkpoint.aligned_junction_held >= threshold:
            return checkpoint.step
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Cogsguard policy trajectories.")
    parser.add_argument("--mission", default="cogsguard_machina_1.basic")
    parser.add_argument("--policy", action="append", required=True)
    parser.add_argument("--cogs", type=int, default=8)
    parser.add_argument("--steps", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sample-every", type=int, default=250)
    parser.add_argument("--max-action-time-ms", type=int, default=10_000)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    comparison = compare_cogsguard_policies(
        mission_name=args.mission,
        policy_specs=[parse_policy_spec(raw).to_policy_spec() for raw in args.policy],
        cogs=args.cogs,
        steps=args.steps,
        seed=args.seed,
        sample_every=args.sample_every,
        max_action_time_ms=args.max_action_time_ms,
    )
    if args.json:
        print(comparison.model_dump_json(indent=2))
        return
    print(render_trajectory_comparison(comparison))


if __name__ == "__main__":
    main()
