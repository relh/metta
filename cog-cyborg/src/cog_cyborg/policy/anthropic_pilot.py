from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mettagrid_sdk.sdk import (
    LogRecord,
    MacroDirective,
    MettagridState,
    ReviewRequest,
)

from cog_cyborg.policy.semantic_cog import MettagridSemanticPolicy, SemanticCogAgentPolicy, SharedWorldModel
from cog_cyborg.runtime.anthropic_pilot import (
    DEFAULT_GOAL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_PILOT_POLICY_TIMEOUT_SECONDS,
    DEFAULT_TEMPERATURE,
    AnthropicPilotSession,
    SharedPilotContext,
    build_pilot_artifact_store,
    build_pilot_memory_store,
    coerce_bool_arg,
)
from mettagrid.policy.policy import AgentPolicy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

DEFAULT_POLICY_TIMEOUT_SECONDS = DEFAULT_PILOT_POLICY_TIMEOUT_SECONDS

__all__ = [
    "AnthropicCyborgPolicy",
    "AnthropicPilotAgentPolicy",
    "AnthropicPilotSession",
    "DEFAULT_GOAL",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_PILOT_POLICY_TIMEOUT_SECONDS",
    "DEFAULT_POLICY_TIMEOUT_SECONDS",
    "DEFAULT_TEMPERATURE",
    "SharedPilotContext",
    "build_pilot_artifact_store",
    "build_pilot_memory_store",
    "coerce_bool_arg",
]

_ELEMENTS = ("carbon", "oxygen", "germanium", "silicon")
_OSCILLATION_HISTORY_STEPS = 6
_RUNTIME_OBSERVATION_WINDOW = 12
_OSCILLATION_REVIEW_COOLDOWN_STEPS = 24
_TARGET_FIXATION_HISTORY_STEPS = 10
_TARGET_FIXATION_REVIEW_MIN_STEP = 24
_TARGET_FIXATION_REVIEW_COOLDOWN_STEPS = 96
_BIAS_MISMATCH_HISTORY_STEPS = 8
_BIAS_MISMATCH_REVIEW_MIN_STEP = 24
_BIAS_MISMATCH_REVIEW_COOLDOWN_STEPS = 96
_STAGNATION_HISTORY_STEPS = 12
_STAGNATION_REVIEW_MIN_STEP = 96
_STAGNATION_REVIEW_COOLDOWN_STEPS = 192
_BOOTSTRAP_STAGNATION_HISTORY_STEPS = 12
_BOOTSTRAP_STAGNATION_REVIEW_MIN_STEP = 160
_BOOTSTRAP_STAGNATION_REVIEW_COOLDOWN_STEPS = 192
_PRESSURE_STAGNATION_HISTORY_STEPS = 12
_PRESSURE_STAGNATION_REVIEW_MIN_STEP = 220
_PRESSURE_STAGNATION_REVIEW_COOLDOWN_STEPS = 96
_POST_REWRITE_RUNTIME_REVIEW_QUIET_STEPS = 96
_HIGH_CHURN_POST_REWRITE_RUNTIME_REVIEW_QUIET_STEPS = 128
_HIGH_CHURN_GLOBAL_STAGNATION_MIN_GENERATION_COUNT = 6


@dataclass(slots=True)
class _RuntimeObservation:
    step: int
    position: tuple[int, int]
    subtask: str
    target_position: str
    target_kind: str
    objective: str
    directive_resource_bias: str
    heart: int


class AnthropicPilotAgentPolicy(SemanticCogAgentPolicy):
    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        *,
        agent_id: int,
        world_model: SharedWorldModel,
        shared_claims: dict[tuple[int, int], tuple[int, int]],
        shared_junctions: dict[tuple[int, int], tuple[str | None, int]],
        pilot_session: AnthropicPilotSession,
    ) -> None:
        super().__init__(
            policy_env_info,
            agent_id=agent_id,
            world_model=world_model,
            shared_claims=shared_claims,
            shared_junctions=shared_junctions,
        )
        self._pilot_session = pilot_session
        self._memory = build_pilot_memory_store(pilot_session.artifact_store)
        self._recent_runtime_observations: deque[_RuntimeObservation] = deque(maxlen=_RUNTIME_OBSERVATION_WINDOW)
        self._last_runtime_review_step: int | None = None
        self._last_target_fixation_review_step: int | None = None
        self._last_bias_mismatch_review_step: int | None = None
        self._last_stagnation_review_step: int | None = None
        self._last_bootstrap_stagnation_review_step: int | None = None
        self._last_pressure_stagnation_review_step: int | None = None
        self._last_any_stagnation_review_step: int | None = None

    def _macro_directive(self, state: MettagridState) -> MacroDirective:
        return self._pilot_session.directive_for_state(state, memory=self._memory)

    @property
    def infos(self) -> dict[str, Any]:
        infos = dict(self._infos)
        infos.update(self._pilot_info_fields())
        return infos

    def step(self, obs) -> Any:
        action = super().step(obs)
        self._maybe_schedule_runtime_review()
        self._infos.update(self._pilot_info_fields())
        return action

    def reset(self, simulation=None) -> None:
        super().reset(simulation=simulation)
        self._memory = build_pilot_memory_store(self._pilot_session.artifact_store)
        self._recent_runtime_observations.clear()
        self._last_runtime_review_step = None
        self._last_target_fixation_review_step = None
        self._last_bias_mismatch_review_step = None
        self._last_stagnation_review_step = None
        self._last_bootstrap_stagnation_review_step = None
        self._last_pressure_stagnation_review_step = None
        self._last_any_stagnation_review_step = None

    def _pilot_info_fields(self) -> dict[str, Any]:
        return {
            "pilot_generation_count": self._pilot_session.generation_count,
            "pilot_objective": self._pilot_session.current_objective,
            "pilot_generation_reason": self._pilot_session.last_generation_reason,
            "__sidecar_debug__": self._pilot_session.debug_snapshot(),
        }

    def _schedule_runtime_review(
        self,
        *,
        message: str,
        trigger_name: str,
        request_summary: str,
        data: dict[str, str | int | float | bool],
        extra_lines: list[str],
    ) -> None:
        self._pilot_session.schedule_runtime_log(
            record=LogRecord(
                level="warning",
                message=message,
                step=self._step_index,
                review=ReviewRequest(
                    trigger_name=trigger_name,
                    prompt=request_summary,
                ),
                data=data,
            ),
            extra_context="\n".join(["Recent low-level telemetry:", self._runtime_positions_line(), *extra_lines]),
        )

    def _runtime_positions_line(self) -> str:
        return "- positions: " + " -> ".join(
            _format_runtime_position(item.position) for item in self._recent_runtime_observations
        )

    def _runtime_subtasks_line(self) -> str:
        return "- subtasks: " + " | ".join(item.subtask for item in self._recent_runtime_observations)

    def _runtime_targets_line(self) -> str:
        return "- targets: " + " | ".join(item.target_position or "-" for item in self._recent_runtime_observations)

    def _runtime_hearts_line(self) -> str:
        return "- hearts: " + " | ".join(str(item.heart) for item in self._recent_runtime_observations)

    def _maybe_schedule_runtime_review(self) -> None:
        current_position = self._last_global_pos
        if current_position is None:
            return
        observation = _RuntimeObservation(
            step=self._step_index,
            position=current_position,
            subtask=str(self._infos["subtask"]),
            target_position=str(self._infos["target_position"]),
            target_kind=str(self._infos["target_kind"]),
            objective=str(self._infos["directive_objective"]),
            directive_resource_bias=str(self._infos.get("directive_resource_bias", "")),
            heart=int(self._infos.get("heart", 0)),
        )
        self._recent_runtime_observations.append(observation)
        if self._is_two_cell_extractor_oscillation():
            if (
                self._last_runtime_review_step is not None
                and self._step_index - self._last_runtime_review_step < _OSCILLATION_REVIEW_COOLDOWN_STEPS
            ):
                return
            self._last_runtime_review_step = self._step_index
            latest = self._recent_runtime_observations[-1]
            request_summary = (
                "Detected a two-cell loop while following the same extractor target. "
                "Rewrite the local policy to change target, resource_bias, or phase so the semantic baseline "
                "can break the loop."
            )
            self._schedule_runtime_review(
                message="Two-cell extractor oscillation detected.",
                trigger_name="runtime_oscillation",
                request_summary=request_summary,
                data={
                    "subtask": latest.subtask,
                    "target_kind": latest.target_kind,
                    "target_position": latest.target_position,
                    "objective": latest.objective or "resource_coverage",
                    "oscillation_steps": self._infos.get("oscillation_steps", 0),
                },
                extra_lines=[
                    f"- subtask: {latest.subtask}",
                    f"- target_kind: {latest.target_kind}",
                    f"- target_position: {latest.target_position}",
                    f"- objective: {latest.objective or 'resource_coverage'}",
                    f"- oscillation_steps: {self._infos.get('oscillation_steps', 0)}",
                ],
            )
            return
        productive_resource = self._productive_bias_mismatch_resource()
        if productive_resource is not None:
            if (
                self._last_bias_mismatch_review_step is not None
                and self._step_index - self._last_bias_mismatch_review_step < _BIAS_MISMATCH_REVIEW_COOLDOWN_STEPS
            ):
                return
            self._last_bias_mismatch_review_step = self._step_index
            latest = self._recent_runtime_observations[-1]
            request_summary = (
                "Detected productive mining on one extractor type while the policy keeps requesting a different "
                "resource bias. Rewrite the local policy to favor the productive extractor, clear the impossible "
                "bias, or change phase."
            )
            self._schedule_runtime_review(
                message="Runtime resource bias mismatch detected.",
                trigger_name="runtime_bias_mismatch",
                request_summary=request_summary,
                data={
                    "directive_resource_bias": latest.directive_resource_bias or "-",
                    "productive_target_resource": productive_resource,
                    "target_kind": latest.target_kind,
                    "target_position": latest.target_position,
                    "objective": latest.objective or "resource_coverage",
                },
                extra_lines=[
                    self._runtime_subtasks_line(),
                    self._runtime_targets_line(),
                    f"- directive_resource_bias: {latest.directive_resource_bias or '-'}",
                    f"- productive_target_resource: {productive_resource}",
                    f"- current_target_kind: {latest.target_kind}",
                    f"- current_target_position: {latest.target_position}",
                    f"- objective: {latest.objective or 'resource_coverage'}",
                ],
            )
            return
        if self._within_post_rewrite_runtime_quiet_period():
            return
        if self._is_extractor_target_fixated():
            if (
                self._last_target_fixation_review_step is not None
                and self._step_index - self._last_target_fixation_review_step < _TARGET_FIXATION_REVIEW_COOLDOWN_STEPS
            ):
                return
            self._last_target_fixation_review_step = self._step_index
            latest = self._recent_runtime_observations[-1]
            request_summary = (
                "Detected prolonged fixation on one extractor while still in resource_coverage. "
                "Rewrite the local policy to change target, resource_bias, or phase."
            )
            self._schedule_runtime_review(
                message="Extractor target fixation detected.",
                trigger_name="runtime_target_fixation",
                request_summary=request_summary,
                data={
                    "subtask": latest.subtask,
                    "target_kind": latest.target_kind,
                    "target_position": latest.target_position,
                    "objective": latest.objective or "resource_coverage",
                    "oscillation_steps": self._infos.get("oscillation_steps", 0),
                },
                extra_lines=[
                    self._runtime_subtasks_line(),
                    f"- target_kind: {latest.target_kind}",
                    f"- target_position: {latest.target_position}",
                    f"- objective: {latest.objective or 'resource_coverage'}",
                    f"- oscillation_steps: {self._infos.get('oscillation_steps', 0)}",
                ],
            )
            return
        if self._is_economy_bootstrap_stagnant():
            if not self._can_schedule_stagnation_review(
                self._last_bootstrap_stagnation_review_step,
                self._bootstrap_stagnation_cooldown_steps(),
            ):
                return
            self._last_bootstrap_stagnation_review_step = self._step_index
            self._mark_stagnation_review_step()
            latest = self._recent_runtime_observations[-1]
            request_summary = (
                "Still stuck in economy_bootstrap without producing hearts. "
                "Rewrite the local policy to change target, helper usage, or phase so the cog can make strategic "
                "progress instead of mining the same lane forever."
            )
            self._schedule_runtime_review(
                message="Economy bootstrap stagnation detected.",
                trigger_name="runtime_stagnation",
                request_summary=request_summary,
                data={
                    "subtask": latest.subtask,
                    "target_kind": latest.target_kind,
                    "target_position": latest.target_position,
                    "objective": latest.objective or "economy_bootstrap",
                    "heart": latest.heart,
                    "generation_count": self._pilot_session.generation_count,
                },
                extra_lines=[
                    self._runtime_subtasks_line(),
                    self._runtime_targets_line(),
                    self._runtime_hearts_line(),
                    f"- current_subtask: {latest.subtask}",
                    f"- current_target_kind: {latest.target_kind}",
                    f"- current_target_position: {latest.target_position}",
                    f"- objective: {latest.objective or 'economy_bootstrap'}",
                    f"- heart: {latest.heart}",
                    f"- generation_count: {self._pilot_session.generation_count}",
                ],
            )
            return
        if self._is_aligner_pressure_stagnant():
            if not self._can_schedule_stagnation_review(
                self._last_pressure_stagnation_review_step,
                _PRESSURE_STAGNATION_REVIEW_COOLDOWN_STEPS,
            ):
                return
            self._last_pressure_stagnation_review_step = self._step_index
            self._mark_stagnation_review_step()
            latest = self._recent_runtime_observations[-1]
            request_summary = (
                "Still stuck in aligner_pressure without visible map-control progress. "
                "Rewrite the local policy to change target_region, role, or phase "
                "so the cog stops hovering in one lane."
            )
            self._schedule_runtime_review(
                message="Aligner pressure stagnation detected.",
                trigger_name="runtime_stagnation",
                request_summary=request_summary,
                data={
                    "subtask": latest.subtask,
                    "target_kind": latest.target_kind,
                    "target_position": latest.target_position,
                    "objective": latest.objective or "aligner_pressure",
                    "heart": latest.heart,
                    "generation_count": self._pilot_session.generation_count,
                },
                extra_lines=[
                    self._runtime_subtasks_line(),
                    self._runtime_targets_line(),
                    self._runtime_hearts_line(),
                    f"- current_subtask: {latest.subtask}",
                    f"- current_target_kind: {latest.target_kind}",
                    f"- current_target_position: {latest.target_position}",
                    f"- objective: {latest.objective or 'aligner_pressure'}",
                    f"- heart: {latest.heart}",
                    f"- generation_count: {self._pilot_session.generation_count}",
                ],
            )
            return
        if not self._is_resource_coverage_stagnant():
            return
        if not self._can_schedule_stagnation_review(
            self._last_stagnation_review_step,
            _STAGNATION_REVIEW_COOLDOWN_STEPS,
        ):
            return
        self._last_stagnation_review_step = self._step_index
        self._mark_stagnation_review_step()
        latest = self._recent_runtime_observations[-1]
        request_summary = (
            "Still stuck in resource_coverage without a strategic change. "
            "Rewrite the local policy to add or tighten an explicit escape hatch, or change target, "
            "resource_bias, or phase."
        )
        self._schedule_runtime_review(
            message="Resource coverage stagnation detected.",
            trigger_name="runtime_stagnation",
            request_summary=request_summary,
            data={
                "subtask": latest.subtask,
                "target_kind": latest.target_kind,
                "target_position": latest.target_position,
                "objective": latest.objective or "resource_coverage",
                "generation_count": self._pilot_session.generation_count,
            },
            extra_lines=[
                self._runtime_subtasks_line(),
                self._runtime_targets_line(),
                f"- current_subtask: {latest.subtask}",
                f"- current_target_kind: {latest.target_kind}",
                f"- current_target_position: {latest.target_position}",
                f"- objective: {latest.objective or 'resource_coverage'}",
                f"- generation_count: {self._pilot_session.generation_count}",
            ],
        )

    def _within_post_rewrite_runtime_quiet_period(self) -> bool:
        last_generation_step = self._pilot_session.last_generation_step
        if last_generation_step is None or self._pilot_session.generation_count <= 2:
            return False
        quiet_steps = _POST_REWRITE_RUNTIME_REVIEW_QUIET_STEPS
        if self._pilot_session.generation_count >= 5:
            quiet_steps = _HIGH_CHURN_POST_REWRITE_RUNTIME_REVIEW_QUIET_STEPS
        return self._step_index - last_generation_step < quiet_steps

    def _bootstrap_stagnation_cooldown_steps(self) -> int:
        cooldown_steps = _BOOTSTRAP_STAGNATION_REVIEW_COOLDOWN_STEPS
        if self._pilot_session.generation_count >= 6:
            return cooldown_steps * 2
        return cooldown_steps

    def _stagnation_cooldown_steps(self, base_steps: int) -> int:
        if self._pilot_session.generation_count >= 8:
            return max(base_steps * 2, 1024)
        if self._pilot_session.generation_count >= _HIGH_CHURN_GLOBAL_STAGNATION_MIN_GENERATION_COUNT:
            return max(base_steps * 2, 512)
        return base_steps

    def _can_schedule_stagnation_review(self, last_review_step: int | None, base_steps: int) -> bool:
        cooldown_steps = self._stagnation_cooldown_steps(base_steps)
        if last_review_step is not None and self._step_index - last_review_step < cooldown_steps:
            return False
        if (
            self._pilot_session.generation_count >= _HIGH_CHURN_GLOBAL_STAGNATION_MIN_GENERATION_COUNT
            and self._last_any_stagnation_review_step is not None
            and self._step_index - self._last_any_stagnation_review_step < cooldown_steps
        ):
            return False
        return True

    def _mark_stagnation_review_step(self) -> None:
        if self._pilot_session.generation_count >= _HIGH_CHURN_GLOBAL_STAGNATION_MIN_GENERATION_COUNT:
            self._last_any_stagnation_review_step = self._step_index

    def _is_two_cell_extractor_oscillation(self) -> bool:
        if len(self._recent_runtime_observations) < _OSCILLATION_HISTORY_STEPS:
            return False
        observations = list(self._recent_runtime_observations)[-_OSCILLATION_HISTORY_STEPS:]
        first = observations[0]
        second = observations[1]
        if first.position == second.position:
            return False
        if not first.subtask.startswith("mine_"):
            return False
        if not first.target_kind.endswith("_extractor"):
            return False
        if not first.target_position:
            return False
        for index, observation in enumerate(observations):
            expected_position = first.position if index % 2 == 0 else second.position
            if observation.position != expected_position:
                return False
            if observation.subtask != first.subtask:
                return False
            if observation.target_kind != first.target_kind:
                return False
            if observation.target_position != first.target_position:
                return False
        return True

    def _is_resource_coverage_stagnant(self) -> bool:
        if self._step_index < _STAGNATION_REVIEW_MIN_STEP:
            return False
        if len(self._recent_runtime_observations) < _STAGNATION_HISTORY_STEPS:
            return False
        observations = list(self._recent_runtime_observations)[-_STAGNATION_HISTORY_STEPS:]
        if any(observation.objective != "resource_coverage" for observation in observations):
            return False
        if len({observation.subtask for observation in observations}) > 3:
            return False
        target_positions = {observation.target_position for observation in observations if observation.target_position}
        return len(target_positions) <= 2

    def _productive_bias_mismatch_resource(self) -> str | None:
        if self._step_index < _BIAS_MISMATCH_REVIEW_MIN_STEP:
            return None
        if len(self._recent_runtime_observations) < _BIAS_MISMATCH_HISTORY_STEPS:
            return None
        observations = list(self._recent_runtime_observations)[-_BIAS_MISMATCH_HISTORY_STEPS:]
        latest = observations[-1]
        bias = latest.directive_resource_bias
        if bias not in _ELEMENTS:
            return None
        if any(observation.objective != "resource_coverage" for observation in observations):
            return None
        if any(observation.directive_resource_bias != bias for observation in observations):
            return None
        productive_resources = [
            observation.target_kind.removesuffix("_extractor")
            for observation in observations
            if observation.subtask.startswith("mine_") and observation.target_kind.endswith("_extractor")
        ]
        if len(productive_resources) < 4:
            return None
        dominant_resource = max(set(productive_resources), key=productive_resources.count)
        if dominant_resource == bias:
            return None
        if productive_resources.count(dominant_resource) < len(productive_resources) - 1:
            return None
        return dominant_resource

    def _is_economy_bootstrap_stagnant(self) -> bool:
        if self._step_index < _BOOTSTRAP_STAGNATION_REVIEW_MIN_STEP:
            return False
        if len(self._recent_runtime_observations) < _BOOTSTRAP_STAGNATION_HISTORY_STEPS:
            return False
        observations = list(self._recent_runtime_observations)[-_BOOTSTRAP_STAGNATION_HISTORY_STEPS:]
        if any(observation.objective != "economy_bootstrap" for observation in observations):
            return False
        if any(observation.heart > 0 for observation in observations):
            return False
        if len({observation.subtask for observation in observations}) > 4:
            return False
        target_positions = {observation.target_position for observation in observations if observation.target_position}
        return len(target_positions) <= 2

    def _is_aligner_pressure_stagnant(self) -> bool:
        if self._step_index < _PRESSURE_STAGNATION_REVIEW_MIN_STEP:
            return False
        if len(self._recent_runtime_observations) < _PRESSURE_STAGNATION_HISTORY_STEPS:
            return False
        observations = list(self._recent_runtime_observations)[-_PRESSURE_STAGNATION_HISTORY_STEPS:]
        if any(observation.objective != "aligner_pressure" for observation in observations):
            return False
        if len({observation.subtask for observation in observations}) > 4:
            return False
        target_positions = {observation.target_position for observation in observations if observation.target_position}
        return len(target_positions) <= 2

    def _is_extractor_target_fixated(self) -> bool:
        if self._step_index < _TARGET_FIXATION_REVIEW_MIN_STEP:
            return False
        if len(self._recent_runtime_observations) < _TARGET_FIXATION_HISTORY_STEPS:
            return False
        observations = list(self._recent_runtime_observations)[-_TARGET_FIXATION_HISTORY_STEPS:]
        latest = observations[-1]
        if not latest.subtask.startswith("mine_"):
            return False
        if not latest.target_kind.endswith("_extractor"):
            return False
        if not latest.target_position:
            return False
        if any(observation.objective != "resource_coverage" for observation in observations):
            return False
        if any(not observation.subtask.startswith("mine_") for observation in observations):
            return False
        if len({observation.target_kind for observation in observations}) != 1:
            return False
        if len({observation.target_position for observation in observations}) != 1:
            return False
        positions = {observation.position for observation in observations}
        return len(positions) <= 4


class AnthropicCyborgPolicy(MettagridSemanticPolicy):
    short_names = ["anthropic-cyborg", "claude-cyborg", "cyborg-anthropic"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        device: str = "cpu",
        **kwargs: Any,
    ) -> None:
        super().__init__(policy_env_info, device=device)
        self._artifact_root = None if kwargs.get("artifact_dir") is None else Path(str(kwargs["artifact_dir"]))
        self._shared_pilot_context = SharedPilotContext()
        self._pilot_sessions: dict[int, AnthropicPilotSession] = {}
        self._pilot_session_kwargs = {
            "model": kwargs.get("model"),
            "api_key": kwargs.get("api_key"),
            "api_key_file": kwargs.get("api_key_file"),
            "anthropic_api_key": kwargs.get("anthropic_api_key"),
            "anthropic_api_key_file": kwargs.get("anthropic_api_key_file"),
            "client": kwargs.get("client"),
            "max_tokens": int(kwargs.get("max_tokens", DEFAULT_MAX_TOKENS)),
            "temperature": float(kwargs.get("temperature", DEFAULT_TEMPERATURE)),
            "goal": str(kwargs.get("goal", DEFAULT_GOAL)),
            "policy_timeout_seconds": float(kwargs.get("policy_timeout_seconds", DEFAULT_PILOT_POLICY_TIMEOUT_SECONDS)),
            "record_step_traces": coerce_bool_arg(kwargs.get("record_step_traces"), default=True),
            "shared_context": self._shared_pilot_context,
        }

    def agent_policy(self, agent_id: int) -> AgentPolicy:
        if agent_id not in self._agent_policies:
            if agent_id not in self._pilot_sessions:
                self._pilot_sessions[agent_id] = AnthropicPilotSession(
                    **self._pilot_session_kwargs,
                    artifact_store=build_pilot_artifact_store(self._artifact_root, agent_id=agent_id),
                )
            self._agent_policies[agent_id] = AnthropicPilotAgentPolicy(
                self.policy_env_info,
                agent_id=agent_id,
                world_model=SharedWorldModel(),
                shared_claims=self._shared_claims,
                shared_junctions=self._shared_junctions,
                pilot_session=self._pilot_sessions[agent_id],
            )
        return self._agent_policies[agent_id]

    def reset(self) -> None:
        self._shared_pilot_context.reset()
        for pilot_session in self._pilot_sessions.values():
            pilot_session.reset()
        super().reset()


def _format_runtime_position(position: tuple[int, int]) -> str:
    return f"{position[0]},{position[1]}"
