from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mettagrid_sdk.games.cogsguard import CogsguardPromptAdapter
from mettagrid_sdk.sdk import (
    ActionCatalog,
    ActionDescriptor,
    LogRecord,
    MacroDirective,
    MemoryQuery,
    MettagridSDK,
    MettagridState,
    ReviewRequest,
    SemanticEvent,
    StateHelperCatalog,
    TeamSummary,
)

from cog_cyborg.memory import MemoryStore
from cog_cyborg.policy.semantic_cog import MettagridSemanticPolicy, SemanticCogAgentPolicy, SharedWorldModel
from cog_cyborg.provider_utils import get_default_anthropic_model, should_use_anthropic_bedrock
from cog_cyborg.providers import CodeReviewRequest, CodeReviewResponse, coerce_code_review_response
from cog_cyborg.providers.anthropic import build_anthropic_client
from cog_cyborg.runtime import ArtifactStore, LivePolicyBundleSession, render_sdk_reference
from cog_cyborg.secret_utils import resolve_api_key
from mettagrid.policy.policy import AgentPolicy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

_ELEMENTS = ("carbon", "oxygen", "germanium", "silicon")
_DEFAULT_GOAL = (
    "Resource coverage first, then bootstrap heart production, then convert the economy into aligner pressure."
)
_DEFAULT_MAX_TOKENS = 2200
_DEFAULT_TEMPERATURE = 0.0
_DEFAULT_POLICY_TIMEOUT_SECONDS = 0.05
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
_HIGH_CHURN_PHASE_SHIFT_QUIET_STEPS = 192
_HIGH_CHURN_GLOBAL_STAGNATION_MIN_GENERATION_COUNT = 6
_OBJECTIVE_ORDER = {
    "resource_coverage": 0,
    "economy_bootstrap": 1,
    "aligner_pressure": 2,
}
_COGSGUARD_PROMPT_ADAPTER = CogsguardPromptAdapter()


class _PilotLogSink:
    def __init__(self) -> None:
        self.records = []
        self.triggers = []
        self.requests = []

    def write(self, record) -> None:
        self.records.append(record)

    def register_review_trigger(self, trigger) -> None:
        self.triggers.append(trigger)

    def request_review(self, request) -> None:
        self.requests.append(request)


def _coerce_bool_arg(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


class _AnthropicCodeModeBackend:
    def __init__(self, *, client: Any, model: str, max_tokens: int, temperature: float) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    def review(self, request: CodeReviewRequest) -> CodeReviewResponse:
        prompt = self._build_prompt(request)
        raw_text, response, latency_ms = self._request_review(prompt)
        retry_validation_error: str | None = None
        validation_retry_count = 0
        try:
            coerced = coerce_code_review_response(raw_text)
        except ValueError as exc:
            retry_validation_error = str(exc)
            validation_retry_count = 1
            retry_prompt = _append_validation_retry_feedback(prompt, retry_validation_error)
            raw_text, response, retry_latency_ms = self._request_review(retry_prompt)
            latency_ms += retry_latency_ms
            coerced = coerce_code_review_response(raw_text)
        metadata = dict(coerced.metadata)
        metadata.setdefault("raw_response_text", raw_text)
        metadata.setdefault("api_latency_ms", round(latency_ms, 1))
        stop_reason = getattr(response, "stop_reason", None)
        if isinstance(stop_reason, str) and stop_reason:
            metadata.setdefault("stop_reason", stop_reason)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "input_tokens", None)
        output_tokens = getattr(usage, "output_tokens", None)
        if isinstance(input_tokens, int):
            metadata.setdefault("input_tokens", input_tokens)
        if isinstance(output_tokens, int):
            metadata.setdefault("output_tokens", output_tokens)
        if retry_validation_error is not None:
            metadata.setdefault("validation_retry_count", validation_retry_count)
            metadata.setdefault("retry_validation_error", retry_validation_error)
        return coerced.model_copy(update={"metadata": metadata})

    def _request_review(self, prompt: str) -> tuple[str, Any, float]:
        start = time.perf_counter()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return _response_text(response), response, (time.perf_counter() - start) * 1000

    def _build_prompt(self, request: CodeReviewRequest) -> str:
        sections = [
            "You are maintaining an executable live workspace for one individual Cogsguard cyborg.",
            (
                "The low-level semantic baseline already handles movement, pathing, mining, deposits, retreating, "
                "gear acquisition, heart handling, junction alignment, and scrambling."
            ),
            "This cog only makes strategic choices by returning a MacroDirective-shaped dict from step(sdk).",
            "You control exactly one cog. Do not assume a shared team planner exists.",
            "Workspace files:",
            "- main.py: executable Python entrypoint; it may define tiny helpers, but it must define step(sdk).",
            "- memory.md: the sdk.memory scratchpad; use it for the current world model, hypotheses, and short notes.",
            "- plan.md: the durable plan; rewrite it when goals, helper functions, or priorities change.",
            "- experience_trace.jsonl: append-only observation and execution trace.",
            "- review_transcript.log: append-only review transcript with API replies and rewrite outcomes.",
            "In review responses, use replace_scratchpad to rewrite memory.md and replace_plan to rewrite plan.md.",
            (
                "Inside step(sdk), prefer sdk.memory.get('phase') / sdk.memory['phase'] for compact key-value state, "
                "sdk.scratchpad or sdk.read_scratchpad() to read the whole file, and sdk.replace_scratchpad(...) to "
                "rewrite the whole file."
            ),
            (
                "For routine per-step state, prefer sdk.memory[...] updates over sdk.replace_scratchpad(...); do not "
                "wipe hook flags such as review_hooks_ready or hooks_ready every step."
            ),
            (
                "Keyed sdk.memory values are JSON-parsed scalars. If step(sdk) later increments or compares a key, "
                "keep that memory.md line machine-readable, e.g. deposit_cycles: 3, not deposit_cycles: tracked."
            ),
            (
                "Inside step(sdk), use sdk.read_plan() to inspect plan.md, sdk.replace_plan(...) to rewrite it, "
                "and sdk.append_plan(...) only for a short new bullet."
            ),
            "Do not treat sdk.memory itself as a raw string; it is a memory interface, not plain text.",
            (
                "For future pause-and-review behavior, register meaningful triggers with "
                "sdk.log.register_review_trigger(...), then emit a LogRecord with review=ReviewRequest(...). "
                "Treat sdk.log.request_review(...) only as shorthand."
            ),
            "There is no hidden outer replan loop. If you want later LLM involvement, register and emit review logs.",
            "Canonical review pattern:",
            '- sdk.log.register_review_trigger("enemy_seen", "Replan after contact.", target="policy")',
            (
                '- sdk.log.write(LogRecord(level="info", message="Enemy on east lane.", step=sdk.state.step, '
                'review=ReviewRequest(trigger_name="enemy_seen", prompt="Replan after contact."), '
                'data={"objective": current}))'
            ),
            "Shorthand still allowed when necessary:",
            '- sdk.log.request_review("enemy_seen", "Enemy on east lane.", target="policy")',
            "Use sdk.log.write(LogRecord(...)) for high-signal observations that should show up in the transcript.",
            "Allowed directive keys:",
            '- role: "miner", "aligner", or "scrambler"',
            '- target_entity_id: exact entity id such as "junction@6,0" when you need a specific target',
            '- target_region: a lane or region label such as "west_lane" when you need a broader tactical bias',
            '- resource_bias: "carbon", "oxygen", "germanium", or "silicon"',
            '- objective: "resource_coverage", "economy_bootstrap", or "aligner_pressure"',
            "- note: short string",
            "Directive semantics:",
            "- use target_entity_id as the strongest control primitive when one exact extractor or junction "
            "should stay pinned",
            "- use target_region when lane pressure or exploration should stay broad instead of pinning one entity",
            "- use resource_bias only to prefer a resource type among viable extractors; it does not lock "
            "one extractor",
            "- if telemetry shows extractor oscillation or one productive extractor, prefer "
            "target_entity_id over resource_bias",
            "Constraints:",
            "- never write import or from ... import lines; bounded main.py rejects them",
            "- LogRecord, ReviewRequest, and ReviewTrigger are already available by name inside main.py",
            "- prefer a single short step(sdk) function; only add helpers if they are truly needed",
            "- return only dicts, never low-level moves",
            "- prefer short deterministic code",
            "- main.py is executed directly, so keep helper code small and self-contained",
            "- sdk.helpers.agent_id() returns an int",
            "- sdk.helpers.shared_inventory() returns dict[str, int]",
            "- treat sdk.helpers and the Cogsguard skill library as compact capability hints; do not "
            "reimplement low-level movement or mining loops in main.py",
            "- maintain a compact memory.md with the current world model, phase, and blockers",
            "- keep plan.md focused on goals, helper strategy, and what should trigger rewrites",
            "- keep memory.md under 10 short lines and keep plan.md under 8 short bullets",
            "- keep main.py concise; avoid long comments and repeated helper code",
            (
                "- if step(sdk) reads back phase or counters from memory.md, keep those key lines plain and "
                "machine-readable"
            ),
            "- sdk.helpers.shared_inventory() may already be non-zero at step 1; do not skip phases from totals alone",
            "- if missing resources remain or hearts are zero, stay conservative before jumping to aligner_pressure",
            (
                "- for single-cog or sparse-team openings, resource_coverage must have an explicit time/resource "
                "escape hatch; do not wait forever for sdk.helpers.missing_resources() to become empty"
            ),
            (
                "- if the current extractor is productive but the requested missing resource is unavailable, bias "
                "toward the productive extractor or leave resource_bias unset instead of insisting on an "
                "impossible bias"
            ),
            "- register 2-4 high-signal triggers during initial generation; do not spam logs every step",
            (
                "- if you want runtime telemetry from the semantic baseline, register exact triggers such as "
                "runtime_oscillation, runtime_target_fixation, runtime_bias_mismatch, or runtime_stagnation"
            ),
            (
                "- for single-cog or sparse-team openings that start in resource_coverage, register "
                "runtime_oscillation, runtime_target_fixation, runtime_bias_mismatch, and runtime_stagnation "
                "during initial generation unless the opening truly skips mining"
            ),
            (
                "- if your code emits ReviewRequest(trigger_name='phase_shift', ...) or "
                "ReviewRequest(trigger_name='enemy_seen', ...), register phase_shift / enemy_seen first so those "
                "milestone logs can actually trigger a review"
            ),
            (
                "- after every rewrite, keep the review hooks you still need by calling "
                "sdk.log.register_review_trigger(...) in the new main.py"
            ),
            (
                "- after a runtime rewrite, if the opening still mines or stays in resource_coverage / "
                "economy_bootstrap, preserve those runtime_* triggers so the LLM can keep revising the opening"
            ),
            (
                "- if you pivot into aligner_pressure, keep runtime_stagnation registered so the LLM can revisit "
                "a bad pressure pivot too"
            ),
            (
                "- if you remove the step-1 init block after a rewrite, move trigger registration behind a durable "
                "memory guard such as review_hooks_ready in sdk.memory"
            ),
            "- do not fire a phase_shift self-review on step 1 unless the previous plan was genuinely wrong",
            (
                "- prefer LogRecord(..., review=ReviewRequest(...)) for milestone reviews; "
                "avoid custom wrappers or imports"
            ),
            (
                "- emit one concise sdk.log.write(LogRecord(...)) startup line at step 1 summarizing the opening "
                "phase/bias"
            ),
            "- prefer one or two decisive sdk.log.write(...) calls over verbose per-step chatter",
            "- after startup, only log again on real milestones such as phase shifts, heart changes, or enemy contact",
            (
                "- prefer reviews triggered by sdk.log.write(... review=ReviewRequest(...)) for milestones; reserve "
                "sdk.log.request_review(...) for immediate contradictions or phase flips"
            ),
            (
                "- if helper choice, goals, or phase logic depend on the durable plan, read it from sdk.read_plan() "
                "and keep it current with sdk.replace_plan(...)"
            ),
            (
                "- if telemetry shows extractor oscillation or repeated unstick_action, do not only relax a phase "
                "threshold; explicitly change target_entity_id, target_region, resource_bias, role, or phase"
            ),
            "- if you emit logs, call sdk.log.write(LogRecord(...)), not sdk.log.write({...})",
            "Return only compact JSON with this schema:",
            (
                '{"action":"policy|memory|memory_and_policy|none",'
                '"set_policy":"<full main.py source defining step(sdk)>",'
                '"replace_scratchpad":"<full memory.md text>",'
                '"replace_plan":"<full plan.md text>",'
                '"review_summary":"<short summary>",'
                '"triggers":[{"name":"enemy_seen","prompt":"Replan after contact.","target":"policy"}]}'
            ),
            'Do not return a top-level "main.py" key.',
            'Do not put objects inside "set_policy"; it must be a single Python source string.',
            'If you only update memory.md or plan.md, omit "set_policy" and set action to "memory".',
            f"Goal: {request.goal or 'unspecified'}",
            f"Trigger: {request.trigger_name or 'manual'}",
            "Operator request:",
            request.prompt,
        ]
        if request.current_main_source:
            sections.extend(["Current main.py:", request.current_main_source])
        if request.current_plan:
            sections.extend(["Current plan.md:", request.current_plan])
        if request.current_scratchpad:
            sections.extend(["Current memory.md:", request.current_scratchpad])
        if request.experience_tail:
            sections.extend(["Recent artifacts:", request.experience_tail])
        if request.decision_log_tail:
            sections.extend(["Recent review decisions:", request.decision_log_tail])
        return "\n".join(sections)


@dataclass(slots=True)
class _SharedPilotContext:
    seen_resources: set[str] = field(default_factory=set)
    initial_shared_inventory: dict[str, int] | None = None

    def reset(self) -> None:
        self.seen_resources.clear()
        self.initial_shared_inventory = None


@dataclass(slots=True)
class _PendingRuntimeLog:
    record: LogRecord
    extra_context: str


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


class AnthropicPilotSession:
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        api_key_file: str | None = None,
        anthropic_api_key: str | None = None,
        anthropic_api_key_file: str | None = None,
        client: Any | None = None,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
        goal: str = _DEFAULT_GOAL,
        policy_timeout_seconds: float = _DEFAULT_POLICY_TIMEOUT_SECONDS,
        record_step_traces: bool = True,
        shared_context: _SharedPilotContext | None = None,
        artifact_store: ArtifactStore | None = None,
    ) -> None:
        resolved_api_key = resolve_api_key(
            direct_value=anthropic_api_key or api_key,
            file_path=anthropic_api_key_file or api_key_file,
            env_var="ANTHROPIC_API_KEY",
        )
        use_bedrock = should_use_anthropic_bedrock(resolved_api_key)
        resolved_client = client if client is not None else build_anthropic_client(api_key=resolved_api_key)
        self._backend = _AnthropicCodeModeBackend(
            client=resolved_client,
            model=model or get_default_anthropic_model(use_bedrock=use_bedrock),
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self._goal = goal
        self._artifact_store = artifact_store
        self._live_policy = LivePolicyBundleSession(
            backend=self._backend,
            artifact_store=artifact_store,
            timeout_seconds=policy_timeout_seconds,
            record_step_traces=record_step_traces,
            should_process_review_request=self._should_process_execution_review_request,
        )
        self._shared_context = shared_context or _SharedPilotContext()
        self._current_objective = "resource_coverage"
        self._generation_count = 0
        self._last_generation_step: int | None = None
        self._last_generation_reason = "initial_generation"
        self._pending_runtime_log: _PendingRuntimeLog | None = None
        self._lock = threading.Lock()

    @property
    def artifact_store(self) -> ArtifactStore | None:
        return self._artifact_store

    @property
    def generation_count(self) -> int:
        return self._generation_count

    @property
    def current_objective(self) -> str:
        return self._current_objective

    @property
    def policy_source(self) -> str | None:
        return self._live_policy.policy_source or None

    @property
    def last_generation_reason(self) -> str:
        return self._last_generation_reason

    @property
    def last_generation_step(self) -> int | None:
        return self._last_generation_step

    def debug_snapshot(self) -> dict[str, Any]:
        snapshot = self._live_policy.debug_snapshot()
        snapshot.update(
            {
                "pilot_objective": self._current_objective,
                "pilot_generation_count": self._generation_count,
                "pilot_generation_reason": self._last_generation_reason,
            }
        )
        return snapshot

    def reset(self) -> None:
        self._live_policy.reset()
        self._shared_context.reset()
        self._current_objective = "resource_coverage"
        self._generation_count = 0
        self._last_generation_step = None
        self._last_generation_reason = "initial_generation"
        self._pending_runtime_log = None

    def schedule_runtime_log(
        self,
        *,
        record: LogRecord,
        extra_context: str,
    ) -> None:
        if record.review is None:
            return
        if self._live_policy.policy_source == "":
            return
        registered_triggers = self._live_policy.debug_snapshot()["registered_triggers"]
        if record.review.trigger_name not in registered_triggers:
            return
        pending_log = _PendingRuntimeLog(
            record=record,
            extra_context=extra_context,
        )
        with self._lock:
            if self._pending_runtime_log == pending_log:
                return
            self._pending_runtime_log = pending_log

    def directive_for_state(self, state: MettagridState, *, memory: MemoryStore) -> MacroDirective:
        sdk = self._build_sdk(state, memory=memory)
        prompt = self._build_review_prompt(sdk, memory=memory)
        step = state.step or 0
        agent_id = sdk.helpers.agent_id()
        metadata: dict[str, str | int | float | bool] = {
            "goal": self._goal,
            "objective": self._current_objective,
        }
        with self._lock:
            pending_runtime_log = self._pending_runtime_log
            self._pending_runtime_log = None
            if pending_runtime_log is not None:
                prompt = "\n\n".join(
                    [
                        prompt,
                        "Runtime log that matched a registered review trigger:",
                        _render_runtime_log_record(pending_runtime_log.record),
                        pending_runtime_log.extra_context,
                    ]
                )
            if pending_runtime_log is not None and self._live_policy.policy_source:
                policy_before_review = self._live_policy.policy_source
                assert pending_runtime_log.record.review is not None
                self._live_policy.review(
                    prompt=prompt,
                    step=step,
                    agent_id=agent_id,
                    trigger_name=pending_runtime_log.record.review.trigger_name,
                    goal=self._goal,
                    metadata=metadata,
                    request_source="sdk.log.write(runtime_telemetry)",
                    request_summary=pending_runtime_log.record.review.prompt or pending_runtime_log.record.message,
                    triggering_log=pending_runtime_log.record,
                )
                self._record_policy_update(
                    policy_before=policy_before_review,
                    reason=pending_runtime_log.record.review.trigger_name,
                    step=step,
                )

            policy_before_execute = self._live_policy.policy_source
            result = self._live_policy.execute(
                sdk=sdk,
                prompt=prompt,
                step=step,
                agent_id=agent_id,
                goal=self._goal,
                metadata=metadata,
            )
            self._record_policy_update(
                policy_before=policy_before_execute,
                reason=self._execution_review_reason(result),
                step=step,
            )

        if not result.success:
            error_text = result.error_type or result.error_message or "generation_failed"
            return MacroDirective(objective=self._current_objective, note=f"pilot_unavailable:{error_text}")
        directive = _coerce_macro_directive(result.return_value, default_objective=self._current_objective)
        if directive.objective:
            self._current_objective = directive.objective
        return directive

    def _build_sdk(self, state: MettagridState, *, memory: MemoryStore) -> MettagridSDK:
        self._update_seen_resources(state)
        missing_resources = [resource for resource in _ELEMENTS if resource not in self._shared_context.seen_resources]
        self._current_objective = _advance_objective(
            self._current_objective,
            _current_opening_objective(state, missing_resources=missing_resources),
        )
        team_summary = state.team_summary
        if team_summary is None:
            team_summary = TeamSummary(team_id=str(state.self_state.attributes.get("team", "")))
        augmented_team_summary = team_summary.model_copy(
            update={
                "shared_objectives": _unique(
                    [
                        *team_summary.shared_objectives,
                        f"current_objective:{self._current_objective}",
                        *(f"seen_resource:{resource}" for resource in sorted(self._shared_context.seen_resources)),
                        *(f"missing_resource:{resource}" for resource in missing_resources),
                    ]
                )
            }
        )
        augmented_state = state.model_copy(update={"team_summary": augmented_team_summary})
        return MettagridSDK(
            state=augmented_state,
            actions=ActionCatalog(
                [
                    ActionDescriptor(
                        name="return_macro_directive",
                        description=(
                            "Return a MacroDirective-shaped dict and optionally update scratchpad or review hooks."
                        ),
                    )
                ]
            ),
            helpers=StateHelperCatalog(augmented_state),
            memory=memory,
            log=_PilotLogSink(),
            plan=self._artifact_store,
        )

    def _update_seen_resources(self, state: MettagridState) -> None:
        if state.team_summary is not None:
            if self._shared_context.initial_shared_inventory is None:
                self._shared_context.initial_shared_inventory = {
                    resource: int(state.team_summary.shared_inventory.get(resource, 0)) for resource in _ELEMENTS
                }
            for resource in _ELEMENTS:
                current_amount = int(state.team_summary.shared_inventory.get(resource, 0))
                baseline_amount = (
                    0
                    if self._shared_context.initial_shared_inventory is None
                    else self._shared_context.initial_shared_inventory[resource]
                )
                if current_amount > baseline_amount:
                    self._shared_context.seen_resources.add(resource)
        for resource in _ELEMENTS:
            if int(state.self_state.inventory.get(resource, 0)) > 0:
                self._shared_context.seen_resources.add(resource)

    def _build_review_prompt(self, sdk: MettagridSDK, *, memory: MemoryStore) -> str:
        query = MemoryQuery.from_state(
            sdk.state,
            active_plan=self._current_objective,
            extra_tags=[self._current_objective],
        )
        memory_context = memory.render_prompt_context(query, limit=6)
        sections = [
            "Strategic context for this single Cogsguard cyborg:",
            f"Goal: {self._goal}",
            f"Current objective: {self._current_objective}",
            "Opening phases:",
            "- resource_coverage: miners should cover missing element types quickly.",
            "- economy_bootstrap: keep miners funding hearts while a smaller aligner group starts pressure.",
            "- aligner_pressure: spend the heart economy on aligners and one late scrambler.",
            (
                "Use memory.md for current world-model facts, blockers, and local hypotheses. "
                "Use plan.md for durable priorities, helper structure, and what should trigger rewrites."
            ),
            (
                "If main.py later reads a memory.md key as a counter or boolean, keep that line as a JSON scalar "
                "instead of prose."
            ),
            (
                "Keep sdk.log usage sparse and decisive: log only when the event should appear in the transcript "
                "or trigger a review."
            ),
        ]
        recent_events = _render_recent_events(sdk.state.recent_events)
        if recent_events:
            sections.extend(["Recent semantic events:", recent_events])
        if memory_context:
            sections.extend(["Relevant memory:", memory_context])
        helper_summary = sdk.helpers.render_capability_summary(max_items=12)
        if helper_summary:
            sections.extend(["Compact helper capabilities:", helper_summary])
        sections.extend(
            [
                "Available Cogsguard tactical skills:",
                _COGSGUARD_PROMPT_ADAPTER.render_skill_library(),
            ]
        )
        registered_triggers = self._live_policy.debug_snapshot()["registered_triggers"]
        if registered_triggers:
            sections.extend(
                [
                    "Current registered review triggers:",
                    *[f"- {trigger}" for trigger in registered_triggers],
                ]
            )
        if self._generation_count >= 5:
            sections.extend(
                [
                    "High rewrite churn warning:",
                    f"- generation_count: {self._generation_count}",
                    "- several recent rewrites already failed to break the loop",
                    (
                        "- do not add another miner/aligner/scrambler rotation or timeout ladder unless telemetry "
                        "shows a genuinely new capability"
                    ),
                    (
                        "- prefer one simpler stable directive and let it run long enough to observe whether the "
                        "semantic baseline can actually execute it"
                    ),
                    (
                        "- for single-cog pressure, avoid scrambler unless enemy_seen or a working heart economy "
                        "already exists"
                    ),
                ]
            )
        sections.extend(
            [
                "Review focus:",
                "- keep main.py short and deterministic",
                "- update memory.md when local facts change",
                "- update plan.md when priorities or helper structure change",
                "- trim helpers that no longer matter for the current phase",
                "- use target_entity_id for one exact extractor or junction, and target_region for broader "
                "lane steering",
                "- do not describe resource_bias as a lock; it is only a resource preference over viable "
                "extractor choices",
                "- prefer keyed sdk.memory[...] updates over per-step sdk.replace_scratchpad(...) rewrites",
                "- preserve or re-register any trigger hooks the current policy still relies on",
                "- prefer milestone logs with LogRecord(..., review=ReviewRequest(...)) over manual review requests",
                (
                    "- if telemetry shows extractor oscillation, change target_entity_id, target_region, "
                    "resource_bias, or phase instead of only relaxing an exit threshold"
                ),
                (
                    "- if resource_coverage is still active after productive mining, change the opening policy itself: "
                    "add a time/resource escape hatch or move into economy_bootstrap"
                ),
                (
                    "- if economy_bootstrap has run for many steps with hearts still at zero, change "
                    "target_entity_id, target_region, helper usage, or phase instead of only waiting longer"
                ),
                (
                    "- if aligner_pressure has run for many steps without visible map-control progress, change "
                    "target_region, role, or phase instead of holding one lane forever"
                ),
                (
                    "- if generation_count is already high, simplify instead of adding more role rotations, "
                    "stacked timeouts, or clever phase ladders"
                ),
                (
                    "- after several rewrites, do not rely on chained phase_shift timers alone: keep "
                    "runtime_stagnation registered because late phase_shift self-reviews may be deferred"
                ),
                "Current snapshot:",
                render_sdk_reference(sdk),
            ]
        )
        return "\n".join(sections)

    def _should_process_execution_review_request(self, request: ReviewRequest, *, step: int) -> bool:
        if request.trigger_name != "phase_shift":
            return True
        last_generation_step = self._last_generation_step
        if last_generation_step is None:
            return True
        if step <= last_generation_step:
            return False
        if self._generation_count < 6:
            return True
        return step - last_generation_step >= _HIGH_CHURN_PHASE_SHIFT_QUIET_STEPS

    def _record_policy_update(self, *, policy_before: str, reason: str | None, step: int) -> None:
        if self._live_policy.policy_source == policy_before:
            return
        self._generation_count += 1
        self._last_generation_step = step
        self._last_generation_reason = "initial_generation" if not policy_before else reason or "manual_review"

    @staticmethod
    def _execution_review_reason(result) -> str | None:
        if result.review_requests:
            return result.review_requests[0].trigger_name
        for record in result.logs:
            if record.review is not None:
                return record.review.trigger_name
            trigger_name = record.data.get("trigger")
            if isinstance(trigger_name, str) and trigger_name:
                return trigger_name
        return None


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
        self._memory = _build_memory_store(pilot_session.artifact_store)
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
        self._memory = _build_memory_store(self._pilot_session.artifact_store)
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
            self._pilot_session.schedule_runtime_log(
                record=LogRecord(
                    level="warning",
                    message="Two-cell extractor oscillation detected.",
                    step=self._step_index,
                    review=ReviewRequest(
                        trigger_name="runtime_oscillation",
                        prompt=request_summary,
                    ),
                    data={
                        "subtask": latest.subtask,
                        "target_kind": latest.target_kind,
                        "target_position": latest.target_position,
                        "objective": latest.objective or "resource_coverage",
                        "oscillation_steps": self._infos.get("oscillation_steps", 0),
                    },
                ),
                extra_context="\n".join(
                    [
                        "Recent low-level telemetry:",
                        (
                            "- positions: "
                            + " -> ".join(
                                _format_runtime_position(item.position) for item in self._recent_runtime_observations
                            )
                        ),
                        f"- subtask: {latest.subtask}",
                        f"- target_kind: {latest.target_kind}",
                        f"- target_position: {latest.target_position}",
                        f"- objective: {latest.objective or 'resource_coverage'}",
                        f"- oscillation_steps: {self._infos.get('oscillation_steps', 0)}",
                    ]
                ),
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
            self._pilot_session.schedule_runtime_log(
                record=LogRecord(
                    level="warning",
                    message="Runtime resource bias mismatch detected.",
                    step=self._step_index,
                    review=ReviewRequest(
                        trigger_name="runtime_bias_mismatch",
                        prompt=request_summary,
                    ),
                    data={
                        "directive_resource_bias": latest.directive_resource_bias or "-",
                        "productive_target_resource": productive_resource,
                        "target_kind": latest.target_kind,
                        "target_position": latest.target_position,
                        "objective": latest.objective or "resource_coverage",
                    },
                ),
                extra_context="\n".join(
                    [
                        "Recent low-level telemetry:",
                        (
                            "- positions: "
                            + " -> ".join(
                                _format_runtime_position(item.position) for item in self._recent_runtime_observations
                            )
                        ),
                        "- subtasks: " + " | ".join(item.subtask for item in self._recent_runtime_observations),
                        "- targets: "
                        + " | ".join(item.target_position or "-" for item in self._recent_runtime_observations),
                        f"- directive_resource_bias: {latest.directive_resource_bias or '-'}",
                        f"- productive_target_resource: {productive_resource}",
                        f"- current_target_kind: {latest.target_kind}",
                        f"- current_target_position: {latest.target_position}",
                        f"- objective: {latest.objective or 'resource_coverage'}",
                    ]
                ),
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
            self._pilot_session.schedule_runtime_log(
                record=LogRecord(
                    level="warning",
                    message="Extractor target fixation detected.",
                    step=self._step_index,
                    review=ReviewRequest(
                        trigger_name="runtime_target_fixation",
                        prompt=request_summary,
                    ),
                    data={
                        "subtask": latest.subtask,
                        "target_kind": latest.target_kind,
                        "target_position": latest.target_position,
                        "objective": latest.objective or "resource_coverage",
                        "oscillation_steps": self._infos.get("oscillation_steps", 0),
                    },
                ),
                extra_context="\n".join(
                    [
                        "Recent low-level telemetry:",
                        (
                            "- positions: "
                            + " -> ".join(
                                _format_runtime_position(item.position) for item in self._recent_runtime_observations
                            )
                        ),
                        "- subtasks: " + " | ".join(item.subtask for item in self._recent_runtime_observations),
                        f"- target_kind: {latest.target_kind}",
                        f"- target_position: {latest.target_position}",
                        f"- objective: {latest.objective or 'resource_coverage'}",
                        f"- oscillation_steps: {self._infos.get('oscillation_steps', 0)}",
                    ]
                ),
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
            self._pilot_session.schedule_runtime_log(
                record=LogRecord(
                    level="warning",
                    message="Economy bootstrap stagnation detected.",
                    step=self._step_index,
                    review=ReviewRequest(
                        trigger_name="runtime_stagnation",
                        prompt=request_summary,
                    ),
                    data={
                        "subtask": latest.subtask,
                        "target_kind": latest.target_kind,
                        "target_position": latest.target_position,
                        "objective": latest.objective or "economy_bootstrap",
                        "heart": latest.heart,
                        "generation_count": self._pilot_session.generation_count,
                    },
                ),
                extra_context="\n".join(
                    [
                        "Recent low-level telemetry:",
                        (
                            "- positions: "
                            + " -> ".join(
                                _format_runtime_position(item.position) for item in self._recent_runtime_observations
                            )
                        ),
                        "- subtasks: " + " | ".join(item.subtask for item in self._recent_runtime_observations),
                        "- targets: "
                        + " | ".join(item.target_position or "-" for item in self._recent_runtime_observations),
                        "- hearts: " + " | ".join(str(item.heart) for item in self._recent_runtime_observations),
                        f"- current_subtask: {latest.subtask}",
                        f"- current_target_kind: {latest.target_kind}",
                        f"- current_target_position: {latest.target_position}",
                        f"- objective: {latest.objective or 'economy_bootstrap'}",
                        f"- heart: {latest.heart}",
                        f"- generation_count: {self._pilot_session.generation_count}",
                    ]
                ),
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
            self._pilot_session.schedule_runtime_log(
                record=LogRecord(
                    level="warning",
                    message="Aligner pressure stagnation detected.",
                    step=self._step_index,
                    review=ReviewRequest(
                        trigger_name="runtime_stagnation",
                        prompt=request_summary,
                    ),
                    data={
                        "subtask": latest.subtask,
                        "target_kind": latest.target_kind,
                        "target_position": latest.target_position,
                        "objective": latest.objective or "aligner_pressure",
                        "heart": latest.heart,
                        "generation_count": self._pilot_session.generation_count,
                    },
                ),
                extra_context="\n".join(
                    [
                        "Recent low-level telemetry:",
                        (
                            "- positions: "
                            + " -> ".join(
                                _format_runtime_position(item.position) for item in self._recent_runtime_observations
                            )
                        ),
                        "- subtasks: " + " | ".join(item.subtask for item in self._recent_runtime_observations),
                        "- targets: "
                        + " | ".join(item.target_position or "-" for item in self._recent_runtime_observations),
                        "- hearts: " + " | ".join(str(item.heart) for item in self._recent_runtime_observations),
                        f"- current_subtask: {latest.subtask}",
                        f"- current_target_kind: {latest.target_kind}",
                        f"- current_target_position: {latest.target_position}",
                        f"- objective: {latest.objective or 'aligner_pressure'}",
                        f"- heart: {latest.heart}",
                        f"- generation_count: {self._pilot_session.generation_count}",
                    ]
                ),
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
        self._pilot_session.schedule_runtime_log(
            record=LogRecord(
                level="warning",
                message="Resource coverage stagnation detected.",
                step=self._step_index,
                review=ReviewRequest(
                    trigger_name="runtime_stagnation",
                    prompt=request_summary,
                ),
                data={
                    "subtask": latest.subtask,
                    "target_kind": latest.target_kind,
                    "target_position": latest.target_position,
                    "objective": latest.objective or "resource_coverage",
                    "generation_count": self._pilot_session.generation_count,
                },
            ),
            extra_context="\n".join(
                [
                    "Recent low-level telemetry:",
                    (
                        "- positions: "
                        + " -> ".join(
                            _format_runtime_position(item.position) for item in self._recent_runtime_observations
                        )
                    ),
                    "- subtasks: " + " | ".join(item.subtask for item in self._recent_runtime_observations),
                    "- targets: "
                    + " | ".join(item.target_position or "-" for item in self._recent_runtime_observations),
                    f"- current_subtask: {latest.subtask}",
                    f"- current_target_kind: {latest.target_kind}",
                    f"- current_target_position: {latest.target_position}",
                    f"- objective: {latest.objective or 'resource_coverage'}",
                    f"- generation_count: {self._pilot_session.generation_count}",
                ]
            ),
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
        self._shared_pilot_context = _SharedPilotContext()
        self._pilot_sessions: dict[int, AnthropicPilotSession] = {}
        self._pilot_session_kwargs = {
            "model": kwargs.get("model"),
            "api_key": kwargs.get("api_key"),
            "api_key_file": kwargs.get("api_key_file"),
            "anthropic_api_key": kwargs.get("anthropic_api_key"),
            "anthropic_api_key_file": kwargs.get("anthropic_api_key_file"),
            "client": kwargs.get("client"),
            "max_tokens": int(kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS)),
            "temperature": float(kwargs.get("temperature", _DEFAULT_TEMPERATURE)),
            "goal": str(kwargs.get("goal", _DEFAULT_GOAL)),
            "policy_timeout_seconds": float(kwargs.get("policy_timeout_seconds", _DEFAULT_POLICY_TIMEOUT_SECONDS)),
            "record_step_traces": _coerce_bool_arg(kwargs.get("record_step_traces"), default=True),
            "shared_context": self._shared_pilot_context,
        }

    def agent_policy(self, agent_id: int) -> AgentPolicy:
        if agent_id not in self._agent_policies:
            if agent_id not in self._pilot_sessions:
                self._pilot_sessions[agent_id] = AnthropicPilotSession(
                    **self._pilot_session_kwargs,
                    artifact_store=_build_artifact_store(self._artifact_root, agent_id=agent_id),
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


def _response_text(response: Any) -> str:
    for block in getattr(response, "content", []):
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    raise ValueError("Anthropic response did not include a text block")


def _build_artifact_store(artifact_root: Path | None, *, agent_id: int) -> ArtifactStore | None:
    if artifact_root is None:
        return None
    root = artifact_root / f"agent-{agent_id}"
    store = ArtifactStore.for_code_mode_bundle(root, prefix="pilot")
    store.semantic_memory_file = root / "pilot_semantic_memory.jsonl"
    store.semantic_memory_file.parent.mkdir(parents=True, exist_ok=True)
    return store


def _build_memory_store(artifact_store: ArtifactStore | None) -> MemoryStore:
    if artifact_store is None:
        return MemoryStore()
    return MemoryStore(
        backing_file=artifact_store.semantic_memory_file,
        scratchpad_file=artifact_store.scratchpad_file,
    )


def _current_opening_objective(state: MettagridState, *, missing_resources: list[str]) -> str:
    if missing_resources:
        return "resource_coverage"
    if _heart_economy_online(state):
        return "aligner_pressure"
    return "economy_bootstrap"


def _heart_economy_online(state: MettagridState) -> bool:
    if int(state.self_state.inventory.get("heart", 0)) > 0:
        return True
    if state.team_summary is None:
        return False
    return int(state.team_summary.shared_inventory.get("heart", 0)) > 0


def _advance_objective(current: str, candidate: str) -> str:
    current_rank = _OBJECTIVE_ORDER.get(current, 0)
    candidate_rank = _OBJECTIVE_ORDER.get(candidate, 0)
    if candidate_rank < current_rank:
        return current
    return candidate


def _coerce_macro_directive(raw: Any, *, default_objective: str) -> MacroDirective:
    if not isinstance(raw, dict):
        return MacroDirective(objective=default_objective)
    role = raw["role"] if "role" in raw and isinstance(raw["role"], str) else None
    target_entity_id = (
        raw["target_entity_id"] if "target_entity_id" in raw and isinstance(raw["target_entity_id"], str) else None
    )
    target_region = raw["target_region"] if "target_region" in raw and isinstance(raw["target_region"], str) else None
    resource_bias = raw["resource_bias"] if "resource_bias" in raw and isinstance(raw["resource_bias"], str) else None
    objective = raw["objective"] if "objective" in raw and isinstance(raw["objective"], str) else default_objective
    note = raw["note"] if "note" in raw and isinstance(raw["note"], str) else ""
    return MacroDirective(
        role=role,
        target_entity_id=target_entity_id,
        target_region=target_region,
        resource_bias=resource_bias,
        objective=objective,
        note=note,
    )


def _unique(items: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _render_recent_events(events: list[SemanticEvent]) -> str:
    if not events:
        return ""
    lines = []
    for event in events:
        evidence = ", ".join(event.evidence)
        suffix = f" [{evidence}]" if evidence else ""
        lines.append(f"- {event.event_type}: {event.summary}{suffix}")
    return "\n".join(lines)


def _format_runtime_position(position: tuple[int, int]) -> str:
    return f"{position[0]},{position[1]}"


def _render_runtime_log_record(record: LogRecord) -> str:
    review_text = ""
    if record.review is not None:
        review_text = f" review={record.review.trigger_name}:{record.review.prompt or record.message}"
    data_text = ""
    if record.data:
        data_text = f" data={record.data}"
    return f"[{record.level}] {record.message} (step {record.step}){review_text}{data_text}"


def _append_validation_retry_feedback(prompt: str, error: str) -> str:
    return "\n\n".join(
        [
            prompt,
            f"Previous output failed validation: {error}",
            "Return only the compact JSON object matching the requested schema. Do not add prose before or after it.",
        ]
    )
