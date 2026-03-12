from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterable
from typing import Any, Protocol

from mettagrid_sdk.sdk import LogRecord, MettagridSDK, ReviewRequest

from cog_cyborg.providers.models import (
    CodeModeBackend,
    CodeReviewRequest,
    CodeReviewResponse,
)
from cog_cyborg.runtime.artifacts import ArtifactStore
from cog_cyborg.runtime.execution import (
    DEFAULT_POLICY_TIMEOUT_SECONDS,
    PolicyExecutionRecord,
    PolicyExecutionResult,
    PolicyUpdate,
    compile_policy,
    execute_compiled_policy,
    render_sdk_reference,
)
from cog_cyborg.runtime.models import (
    ExperienceTraceRecord,
    PolicyGenerationRecord,
    ReviewDecisionRecord,
)

_MAX_DEBUG_EVENTS = 24
_MAX_RAW_RESPONSE_CHARS = 4000
_MAX_DEBUG_TRANSCRIPT_CHARS = 200_000
_SCRATCHPAD_LINE_RE = re.compile(r"^(?P<prefix>\s*(?:-\s*)?)(?P<key>[A-Za-z0-9_.-]+)\s*(?P<sep>:|=)\s*(?P<value>.*)$")
_PROTECTED_SCRATCHPAD_KEYS = frozenset({"review_hooks_ready", "hooks_ready"})


class ReviewRequestFilter(Protocol):
    def __call__(self, request: ReviewRequest, *, step: int) -> bool: ...


def _merge_protected_scratchpad_keys(current_text: str, updated_text: str) -> str:
    current_values = _scratchpad_key_lines(current_text.splitlines())
    updated_values = _scratchpad_key_lines(updated_text.splitlines())
    preserved_by_key = {
        key: current_values[key]
        for key in sorted(_PROTECTED_SCRATCHPAD_KEYS)
        if key in current_values and key not in updated_values
    }
    for key, current_line in current_values.items():
        updated_line = updated_values.get(key)
        if updated_line is None:
            continue
        if _should_preserve_typed_scratchpad_line(current_line, updated_line):
            preserved_by_key[key] = current_line
    if not preserved_by_key:
        return updated_text
    if not updated_text:
        return "\n".join(preserved_by_key[key] for key in sorted(preserved_by_key))

    merged_lines: list[str] = []
    restored_keys: set[str] = set()
    for line in updated_text.splitlines():
        match = _SCRATCHPAD_LINE_RE.match(line)
        if match is None:
            merged_lines.append(line)
            continue
        key = match.group("key")
        restored_line = preserved_by_key.get(key)
        if restored_line is None:
            merged_lines.append(line)
            continue
        merged_lines.append(restored_line)
        restored_keys.add(key)
    for key in sorted(preserved_by_key):
        if key not in restored_keys:
            merged_lines.append(preserved_by_key[key])
    return "\n".join(merged_lines)


def _scratchpad_key_lines(lines: list[str]) -> dict[str, str]:
    keyed_lines: dict[str, str] = {}
    for line in lines:
        match = _SCRATCHPAD_LINE_RE.match(line)
        if match is None:
            continue
        keyed_lines[match.group("key")] = line
    return keyed_lines


def _should_preserve_typed_scratchpad_line(current_line: str, updated_line: str) -> bool:
    current_value = _scratchpad_line_value(current_line)
    updated_value = _scratchpad_line_value(updated_line)
    return not isinstance(current_value, str) and isinstance(updated_value, str)


def _scratchpad_line_value(line: str) -> Any:
    match = _SCRATCHPAD_LINE_RE.match(line)
    if match is None:
        return ""
    candidate = match.group("value").strip()
    if not candidate:
        return ""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return candidate


def _merge_review_metadata(
    metadata: dict[str, str | int | float | bool] | None,
    extra: dict[str, str | int | float | bool] | None = None,
) -> dict[str, str | int | float | bool]:
    merged = {} if metadata is None else dict(metadata)
    if extra is not None:
        merged.update(extra)
    return merged


def _metadata_from_return_value(
    return_value: Any,
) -> dict[str, str | int | float | bool]:
    if not isinstance(return_value, dict):
        return {}
    return {
        key: value
        for key in (
            "objective",
            "role",
            "target_entity_id",
            "target_region",
            "resource_bias",
        )
        if isinstance((value := return_value.get(key)), (str, int, float, bool))
    }


class LivePolicyBundleSession:
    def __init__(
        self,
        *,
        backend: CodeModeBackend,
        artifact_store: ArtifactStore | None = None,
        timeout_seconds: float = DEFAULT_POLICY_TIMEOUT_SECONDS,
        record_step_traces: bool = True,
        should_process_review_request: ReviewRequestFilter | None = None,
    ) -> None:
        self._backend = backend
        self._artifact_store = artifact_store
        self._timeout_seconds = timeout_seconds
        self._record_step_traces = record_step_traces
        self._should_process_review_request = should_process_review_request
        self._compiled_policy = None
        self._policy_source = ""
        self._registered_trigger_names: set[str] = set()
        self._lock = threading.Lock()
        self._debug_events: list[dict[str, Any]] = []
        self._next_debug_event_id = 1
        self._debug_transcript_tail = ""
        self._last_return_signature = ""

    @property
    def policy_source(self) -> str:
        return self._policy_source

    def debug_snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot: dict[str, Any] = {
                "last_event_id": (self._debug_events[-1]["event_id"] if self._debug_events else 0),
                "registered_triggers": sorted(self._registered_trigger_names),
                "events": list(self._debug_events),
            }
            if self._debug_transcript_tail:
                snapshot["transcript_tail"] = self._debug_transcript_tail
            return snapshot

    def reset(self) -> None:
        self._compiled_policy = None
        self._policy_source = ""
        with self._lock:
            self._registered_trigger_names.clear()
        self._debug_events.clear()
        self._next_debug_event_id = 1
        self._debug_transcript_tail = ""
        self._last_return_signature = ""

    def execute(
        self,
        *,
        sdk: MettagridSDK,
        prompt: str,
        step: int,
        agent_id: int,
        goal: str = "",
        metadata: dict[str, str | int | float | bool] | None = None,
    ) -> PolicyExecutionResult:
        self._ensure_policy(
            sdk=sdk,
            prompt=prompt,
            step=step,
            agent_id=agent_id,
            goal=goal,
            metadata=metadata,
        )
        assert self._compiled_policy is not None

        result = execute_compiled_policy(self._compiled_policy, sdk, timeout_seconds=self._timeout_seconds)
        execution_metadata = _merge_review_metadata(metadata, _metadata_from_return_value(result.return_value))
        current_source = self._policy_source
        if self._artifact_store is not None and self._record_step_traces:
            self._artifact_store.append_execution_record(
                PolicyExecutionRecord(
                    step=step,
                    agent_id=agent_id,
                    policy_source=current_source,
                    result=result,
                )
            )
            self._artifact_store.append_experience_record(
                ExperienceTraceRecord(
                    step=step,
                    agent_id=agent_id,
                    summary=render_sdk_reference(sdk),
                    policy_source=current_source,
                    return_repr=result.return_repr,
                    logs=[f"{record.level}:{record.message}" for record in result.logs],
                    metadata=execution_metadata,
                )
            )
        self._register_trigger_names(trigger.name for trigger in result.review_triggers)
        review_request, triggering_log, review_source = self._select_review_request(result)
        if (
            review_request is not None
            and self._should_process_review_request is not None
            and not self._should_process_review_request(review_request, step=step)
        ):
            review_request = None
            triggering_log = None
            review_source = None
        current_return_signature = _stable_return_signature(result.return_value, result.return_repr)
        should_record_runtime = (
            step == 1
            or result.success is False
            or bool(result.logs)
            or bool(result.review_triggers)
            or bool(result.review_requests)
            or review_request is not None
            or current_return_signature != self._last_return_signature
        )
        if should_record_runtime:
            self._append_debug_event(
                {
                    "kind": "policy_step",
                    "step": step,
                    "agent_id": agent_id,
                    "success": result.success,
                    "return_repr": result.return_repr,
                    "error_type": result.error_type,
                    "error_message": result.error_message,
                    "logs": [_serialize_log_record(record) for record in result.logs],
                    "review_triggers": [_serialize_review_trigger(trigger) for trigger in result.review_triggers],
                    "review_requests": [_serialize_review_request(request) for request in result.review_requests],
                    "selected_review_request": (
                        None if review_request is None else _serialize_review_request(review_request)
                    ),
                    "selected_review_source": review_source,
                    "triggering_log": (None if triggering_log is None else _serialize_log_record(triggering_log)),
                }
            )
            self._append_execution_transcript(
                step=step,
                agent_id=agent_id,
                result=result,
                review_request=review_request,
                triggering_log=triggering_log,
                review_source=review_source,
            )
        self._last_return_signature = current_return_signature
        if review_request is not None:
            self.review(
                prompt=f"{prompt}\n\nReview request: {review_request.prompt or review_request.trigger_name}",
                step=step,
                agent_id=agent_id,
                trigger_name=review_request.trigger_name,
                goal=goal,
                metadata=execution_metadata,
                request_source=review_source or "sdk.log.request_review",
                request_summary=review_request.prompt or review_request.trigger_name,
                triggering_log=triggering_log,
            )
        return result

    def review(
        self,
        *,
        prompt: str,
        step: int,
        agent_id: int,
        trigger_name: str,
        goal: str = "",
        metadata: dict[str, str | int | float | bool] | None = None,
        request_source: str = "manual_review",
        request_summary: str | None = None,
        triggering_log=None,
    ) -> CodeReviewResponse:
        request = self._build_review_request(
            prompt=prompt,
            step=step,
            agent_id=agent_id,
            trigger_name=trigger_name,
            goal=goal,
            metadata=metadata,
        )
        return self._perform_review(
            request=request,
            step=step,
            agent_id=agent_id,
            trigger_name=trigger_name,
            metadata=metadata,
            request_source=request_source,
            request_summary=request_summary or trigger_name,
            triggering_log=triggering_log,
        )

    def _perform_review(
        self,
        *,
        request: CodeReviewRequest,
        step: int,
        agent_id: int,
        trigger_name: str,
        metadata: dict[str, str | int | float | bool] | None,
        request_source: str,
        request_summary: str | None,
        triggering_log,
    ) -> CodeReviewResponse:
        review_error: str | None = None
        try:
            response = self._backend.review(request)
        except Exception as exc:
            review_error = f"{type(exc).__name__}: {exc}"
            response = CodeReviewResponse(
                action="none",
                review_summary=f"Review failed: {review_error}",
                metadata={"review_error": review_error},
            )
        policy_updated = False
        scratchpad_updated = False
        plan_updated = False
        policy_update_error: str | None = None
        policy_update_exception: Exception | None = None
        if response.replace_scratchpad is not None and self._artifact_store is not None:
            self._artifact_store.replace_scratchpad(
                _merge_protected_scratchpad_keys(
                    self._artifact_store.read_scratchpad(),
                    response.replace_scratchpad,
                )
            )
            scratchpad_updated = True
        if response.replace_plan is not None and self._artifact_store is not None:
            self._artifact_store.replace_plan(response.replace_plan)
            plan_updated = True
        if response.set_policy:
            try:
                self._set_policy_source(
                    response.set_policy,
                    step=step,
                    agent_id=agent_id,
                    prompt=request.prompt,
                    raw_response=_raw_response_text(response),
                    metadata=_merge_record_metadata(metadata, response.metadata),
                )
                policy_updated = True
            except Exception as exc:
                policy_update_exception = exc
                self._append_failed_generation_record(
                    step=step,
                    agent_id=agent_id,
                    prompt=request.prompt,
                    raw_response=_raw_response_text(response),
                    policy_source=response.set_policy,
                    error_message=f"{type(exc).__name__}: {exc}",
                    metadata=_merge_record_metadata(metadata, response.metadata),
                )
        self._register_trigger_names(trigger.name for trigger in response.triggers)
        if self._artifact_store is not None:
            policy_update_error = (
                None
                if policy_update_exception is None
                else f"{type(policy_update_exception).__name__}: {policy_update_exception}"
            )
            self._artifact_store.append_decision_record(
                ReviewDecisionRecord(
                    step=step,
                    agent_id=agent_id,
                    trigger_name=trigger_name,
                    action=response.action,
                    request_summary=request_summary or trigger_name,
                    summary=response.review_summary or response.append_log,
                    append_log=response.append_log,
                    policy_updated=policy_updated,
                    scratchpad_updated=scratchpad_updated,
                    plan_updated=plan_updated,
                    metadata=_merge_record_metadata(
                        metadata,
                        response.metadata,
                        (None if review_error is None else {"review_error": review_error}),
                        (None if policy_update_error is None else {"policy_update_error": policy_update_error}),
                    ),
                )
            )
        response_metadata = response.metadata if isinstance(response.metadata, dict) else {}
        self._append_debug_event(
            {
                "kind": "llm_review",
                "step": step,
                "agent_id": agent_id,
                "trigger_name": trigger_name,
                "source": request_source,
                "request_summary": request_summary or trigger_name,
                "triggering_log": (None if triggering_log is None else _serialize_log_record(triggering_log)),
                "action": response.action,
                "review_summary": response.review_summary,
                "append_log": response.append_log,
                "policy_updated": policy_updated,
                "policy_update_error": policy_update_error,
                "review_error": review_error,
                "scratchpad_updated": scratchpad_updated,
                "plan_updated": plan_updated,
                "registered_triggers": [_serialize_review_trigger(trigger) for trigger in response.triggers],
                "raw_response_text": _raw_response_text(response),
                "stop_reason": _string_or_none(response_metadata.get("stop_reason")),
                "input_tokens": _int_or_none(response_metadata.get("input_tokens")),
                "output_tokens": _int_or_none(response_metadata.get("output_tokens")),
                "api_latency_ms": _float_or_none(response_metadata.get("api_latency_ms")),
            }
        )
        self._append_review_transcript(
            step=step,
            agent_id=agent_id,
            trigger_name=trigger_name,
            request_source=request_source,
            request_summary=request_summary or trigger_name,
            triggering_log=triggering_log,
            response=response,
            policy_updated=policy_updated,
            policy_update_error=policy_update_error,
            review_error=review_error,
            scratchpad_updated=scratchpad_updated,
            plan_updated=plan_updated,
        )
        if policy_update_exception is not None:
            raise policy_update_exception
        return response

    def _ensure_policy(
        self,
        *,
        sdk: MettagridSDK,
        prompt: str,
        step: int,
        agent_id: int,
        goal: str,
        metadata: dict[str, str | int | float | bool] | None,
    ) -> None:
        if self._compiled_policy is not None:
            return
        response = self._perform_review(
            request=CodeReviewRequest(
                agent_id=agent_id,
                step=step,
                goal=goal,
                trigger_name="initial_generation",
                prompt=prompt,
                current_main_source=self._policy_source,
                current_plan=("" if self._artifact_store is None else self._artifact_store.read_plan()),
                current_scratchpad=("" if self._artifact_store is None else self._artifact_store.read_scratchpad()),
                experience_tail="",
                decision_log_tail="",
                metadata={} if metadata is None else dict(metadata),
            ),
            step=step,
            agent_id=agent_id,
            trigger_name="initial_generation",
            metadata=metadata,
            request_source="initial_generation",
            request_summary="Generate the initial policy.",
            triggering_log=None,
        )
        if not response.set_policy:
            raise ValueError("Live policy backend did not return set_policy for initial generation")
        self._register_trigger_names(trigger.name for trigger in response.triggers)
        try:
            self._set_policy_source(
                response.set_policy,
                step=step,
                agent_id=agent_id,
                prompt=prompt,
                raw_response=_raw_response_text(response),
                metadata=_merge_record_metadata(metadata, response.metadata),
            )
        except Exception as exc:
            self._append_failed_generation_record(
                step=step,
                agent_id=agent_id,
                prompt=prompt,
                raw_response=_raw_response_text(response),
                policy_source=response.set_policy,
                error_message=f"{type(exc).__name__}: {exc}",
                metadata=_merge_record_metadata(metadata, response.metadata),
            )
            raise

    def _set_policy_source(
        self,
        policy_source: str,
        *,
        step: int,
        agent_id: int,
        prompt: str,
        raw_response: str,
        metadata: dict[str, str | int | float | bool] | None,
    ) -> None:
        compiled = compile_policy(PolicyUpdate(source=policy_source))
        self._compiled_policy = compiled
        self._policy_source = policy_source
        if self._artifact_store is not None:
            self._artifact_store.write_main_source(policy_source)
            self._artifact_store.append_generation_record(
                PolicyGenerationRecord(
                    step=step,
                    agent_id=agent_id,
                    prompt=prompt,
                    raw_response=raw_response,
                    policy_source=policy_source,
                    success=True,
                    metadata={} if metadata is None else metadata,
                )
            )
            self._artifact_store.append_policy_update(step=step, agent_id=agent_id, policy_source=policy_source)

    def _append_failed_generation_record(
        self,
        *,
        step: int,
        agent_id: int,
        prompt: str,
        raw_response: str,
        policy_source: str | None,
        error_message: str,
        metadata: dict[str, str | int | float | bool] | None,
    ) -> None:
        if self._artifact_store is None:
            return
        self._artifact_store.append_generation_record(
            PolicyGenerationRecord(
                step=step,
                agent_id=agent_id,
                prompt=prompt,
                raw_response=raw_response,
                policy_source=policy_source,
                success=False,
                error_message=error_message,
                metadata={} if metadata is None else metadata,
            )
        )

    def _build_review_request(
        self,
        *,
        prompt: str,
        step: int,
        agent_id: int,
        trigger_name: str,
        goal: str,
        metadata: dict[str, str | int | float | bool] | None,
    ) -> CodeReviewRequest:
        return CodeReviewRequest(
            agent_id=agent_id,
            step=step,
            goal=goal,
            trigger_name=trigger_name,
            prompt=prompt,
            current_main_source=self._policy_source,
            current_plan=("" if self._artifact_store is None else self._artifact_store.read_plan()),
            current_scratchpad=("" if self._artifact_store is None else self._artifact_store.read_scratchpad()),
            experience_tail=(
                ""
                if self._artifact_store is None
                else self._artifact_store.build_prompt_context(
                    include_main_source=False,
                    include_plan=False,
                    include_scratchpad=False,
                )
            ),
            decision_log_tail=("" if self._artifact_store is None else self._decision_log_tail()),
            metadata={} if metadata is None else dict(metadata),
        )

    def _decision_log_tail(self, max_entries: int = 6) -> str:
        if self._artifact_store is None:
            return ""
        records = self._artifact_store.read_recent_decision_records(max_entries=max_entries)
        if not records:
            return ""
        return "\n".join(
            f"- step {record.step}: trigger={record.trigger_name or 'none'} action={record.action} "
            f"request={record.request_summary or 'none'} {record.summary or record.append_log}"
            for record in records
        )

    def _select_review_request(self, result: PolicyExecutionResult):
        registered_trigger_names = self._registered_trigger_names_snapshot()
        for record in result.logs:
            review_request = _review_request_from_log_record(record, registered_trigger_names)
            if review_request is not None:
                review_source = "sdk.log.write(review=...)"
                if record.review is None:
                    review_source = "sdk.log.write(data.trigger)"
                return review_request, record, review_source
        if result.review_requests:
            return result.review_requests[0], None, "sdk.log.request_review"
        return None, None, None

    def _append_debug_event(self, event: dict[str, Any]) -> None:
        self._debug_events.append({"event_id": self._next_debug_event_id, **event})
        self._next_debug_event_id += 1
        if len(self._debug_events) > _MAX_DEBUG_EVENTS:
            self._debug_events = self._debug_events[-_MAX_DEBUG_EVENTS:]

    def _append_execution_transcript(
        self,
        *,
        step: int,
        agent_id: int,
        result: PolicyExecutionResult,
        review_request: ReviewRequest | None,
        triggering_log,
        review_source: str | None,
    ) -> None:
        lines = [f"## Step {step} Agent {agent_id} runtime -> llm"]
        if result.return_repr:
            lines.append(f"return: {result.return_repr}")
        if result.success is False:
            error_type = result.error_type or "PolicyError"
            error_message = result.error_message or "unknown"
            lines.append(f"error: {error_type}: {error_message}")
        if result.review_triggers:
            lines.append("registered_triggers:")
            lines.extend(f"- {_render_trigger_line(trigger)}" for trigger in result.review_triggers)
        if result.logs:
            lines.append("sdk.log:")
            lines.extend(f"- {_render_log_line(record)}" for record in result.logs)
        if review_request is not None:
            lines.append("review_request:")
            if review_source:
                lines.append(f"- source: {review_source}")
            lines.append(f"- details: {_render_review_request_line(review_request)}")
            if triggering_log is not None:
                lines.append(f"- triggering_log: {_render_log_line(triggering_log)}")
        if len(lines) == 1:
            return
        self._append_transcript_lines(lines)

    def _append_review_transcript(
        self,
        *,
        step: int,
        agent_id: int,
        trigger_name: str,
        request_source: str,
        request_summary: str,
        triggering_log,
        response: CodeReviewResponse,
        policy_updated: bool,
        policy_update_error: str | None,
        review_error: str | None,
        scratchpad_updated: bool,
        plan_updated: bool,
    ) -> None:
        lines = [f"## Step {step} Agent {agent_id} llm -> runtime"]
        lines.append("review_request:")
        lines.append(f"- source: {request_source}")
        lines.append(f"- trigger: {trigger_name}")
        lines.append(f"- request: {request_summary}")
        if triggering_log is not None:
            lines.append(f"- triggering_log: {_render_log_line(triggering_log)}")
        outcome_bits = [f"action={response.action}"]
        if policy_updated:
            outcome_bits.append("policy_updated=yes")
        if scratchpad_updated:
            outcome_bits.append("scratchpad_updated=yes")
        if plan_updated:
            outcome_bits.append("plan_updated=yes")
        lines.append(f"review_outcome: {', '.join(outcome_bits)}")
        if policy_update_error:
            lines.append(f"policy_update_error: {policy_update_error}")
        if review_error:
            lines.append(f"review_error: {review_error}")
        if response.review_summary:
            lines.append(f"summary: {response.review_summary}")
        if response.append_log:
            lines.append(f"append_log: {response.append_log}")
        if response.triggers:
            lines.append("next_review_triggers:")
            lines.extend(f"- {_render_trigger_line(trigger)}" for trigger in response.triggers)
        api_line = _format_api_metadata(response.metadata if isinstance(response.metadata, dict) else {})
        if api_line:
            lines.append(f"api: {api_line}")
        raw_response = _raw_response_text(response)
        if raw_response:
            lines.append("llm_response:")
            lines.extend(_render_text_block(_pretty_json_or_text(raw_response), indent="  "))
        self._append_transcript_lines(lines)

    def _append_transcript_lines(self, lines: list[str]) -> None:
        appended = "\n".join([*lines, ""]) + "\n"
        self._debug_transcript_tail = (self._debug_transcript_tail + appended)[-_MAX_DEBUG_TRANSCRIPT_CHARS:]
        if self._artifact_store is None:
            return
        self._artifact_store.append_log_text(appended)

    def _register_trigger_names(self, trigger_names: Iterable[str]) -> None:
        names = {name for name in trigger_names if name}
        if not names:
            return
        with self._lock:
            self._registered_trigger_names.update(names)

    def _registered_trigger_names_snapshot(self) -> set[str]:
        with self._lock:
            return set(self._registered_trigger_names)


def _review_request_from_log_record(
    record: LogRecord,
    registered_trigger_names: set[str],
) -> ReviewRequest | None:
    if record.review is not None:
        if record.review.trigger_name not in registered_trigger_names:
            return None
        return record.review
    trigger_name = record.data.get("trigger")
    if not isinstance(trigger_name, str):
        return None
    if trigger_name not in registered_trigger_names:
        return None
    prompt = record.message
    prompt_override = record.data.get("prompt")
    if isinstance(prompt_override, str) and prompt_override:
        prompt = prompt_override
    target = "policy"
    if record.data.get("target") in {"memory", "policy"}:
        target = record.data["target"]
    metadata = {}
    if isinstance(record.data.get("metadata"), dict):
        metadata = record.data["metadata"]
    return ReviewRequest(
        trigger_name=trigger_name,
        prompt=prompt,
        target=target,
        step=record.step,
        metadata=metadata,
    )


def _merge_record_metadata(
    *sources: dict[str, str | int | float | bool] | dict[str, Any] | None,
) -> dict[str, str | int | float | bool]:
    merged: dict[str, str | int | float | bool] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            if key == "raw_response_text":
                continue
            if isinstance(value, (str, int, float, bool)):
                merged[key] = value
    return merged


def _stable_return_signature(return_value: Any, return_repr: str) -> str:
    if isinstance(return_value, dict):
        stable_payload = {key: value for key, value in return_value.items() if key not in {"note", "metadata"}}
        return _compact_json(stable_payload)
    return return_repr or repr(return_value)


def _serialize_log_record(record: Any) -> dict[str, Any]:
    payload = {
        "level": _string_or_none(getattr(record, "level", None)) or "info",
        "message": _string_or_none(getattr(record, "message", None)) or "",
        "step": _int_or_none(getattr(record, "step", None)),
    }
    review = getattr(record, "review", None)
    if review is not None:
        payload["review"] = _serialize_review_request(review)
    data = getattr(record, "data", None)
    if isinstance(data, dict) and data:
        payload["data"] = dict(data)
    return payload


def _serialize_review_request(request: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"trigger_name": _string_or_none(getattr(request, "trigger_name", None)) or ""}
    prompt = _string_or_none(getattr(request, "prompt", None))
    if prompt:
        payload["prompt"] = prompt
    target = _string_or_none(getattr(request, "target", None))
    if target:
        payload["target"] = target
    step = _int_or_none(getattr(request, "step", None))
    if step is not None:
        payload["step"] = step
    metadata = getattr(request, "metadata", None)
    if isinstance(metadata, dict) and metadata:
        payload["metadata"] = dict(metadata)
    return payload


def _serialize_review_trigger(trigger: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"name": _string_or_none(getattr(trigger, "name", None)) or ""}
    prompt = _string_or_none(getattr(trigger, "prompt", None))
    if prompt:
        payload["prompt"] = prompt
    target = _string_or_none(getattr(trigger, "target", None))
    if target:
        payload["target"] = target
    once = getattr(trigger, "once", None)
    if isinstance(once, bool):
        payload["once"] = once
    metadata = getattr(trigger, "metadata", None)
    if isinstance(metadata, dict) and metadata:
        payload["metadata"] = dict(metadata)
    return payload


def _raw_response_text(response: CodeReviewResponse) -> str:
    if isinstance(response.metadata, dict):
        raw_response = response.metadata.get("raw_response_text")
        if isinstance(raw_response, str) and raw_response:
            return raw_response
    return response.model_dump_json()


def _render_review_request_line(request: Any) -> str:
    serialized = _serialize_review_request(request)
    bits = []
    trigger_name = serialized.get("trigger_name")
    if isinstance(trigger_name, str) and trigger_name:
        bits.append(f"trigger={trigger_name}")
    target = serialized.get("target")
    if isinstance(target, str) and target:
        bits.append(f"target={target}")
    prompt = serialized.get("prompt")
    if isinstance(prompt, str) and prompt:
        bits.append(f"prompt={prompt}")
    return ", ".join(bits) or _compact_json(serialized)


def _render_trigger_line(trigger: Any) -> str:
    serialized = _serialize_review_trigger(trigger)
    bits = []
    name = serialized.get("name")
    if isinstance(name, str) and name:
        bits.append(name)
    target = serialized.get("target")
    if isinstance(target, str) and target:
        bits.append(f"target={target}")
    prompt = serialized.get("prompt")
    if isinstance(prompt, str) and prompt:
        bits.append(prompt)
    return " | ".join(bits) or _compact_json(serialized)


def _render_log_line(record: Any) -> str:
    serialized = _serialize_log_record(record)
    level = serialized.get("level") or "info"
    message = serialized.get("message") or ""
    step = serialized.get("step")
    line = f"[{level}] {message}".rstrip()
    if isinstance(step, int):
        line = f"{line} (step {step})"
    review = serialized.get("review")
    if isinstance(review, dict) and review:
        line = f"{line} review={_compact_json(review)}"
    data = serialized.get("data")
    if isinstance(data, dict) and data:
        line = f"{line} data={_compact_json(data)}"
    return line


def _format_api_metadata(metadata: dict[str, Any]) -> str:
    parts = []
    latency = _float_or_none(metadata.get("api_latency_ms"))
    if latency is not None:
        parts.append(f"latency={latency}ms")
    stop_reason = _string_or_none(metadata.get("stop_reason"))
    if stop_reason:
        parts.append(f"stop_reason={stop_reason}")
    input_tokens = _int_or_none(metadata.get("input_tokens"))
    if input_tokens is not None:
        parts.append(f"input_tokens={input_tokens}")
    output_tokens = _int_or_none(metadata.get("output_tokens"))
    if output_tokens is not None:
        parts.append(f"output_tokens={output_tokens}")
    return ", ".join(parts)


def _pretty_json_or_text(text: str) -> str:
    candidate = text.strip()
    if len(candidate) > _MAX_RAW_RESPONSE_CHARS:
        candidate = f"{candidate[:_MAX_RAW_RESPONSE_CHARS].rstrip()}\n... [truncated]"
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return candidate
    return json.dumps(parsed, indent=2, sort_keys=True)


def _render_text_block(text: str, *, indent: str) -> list[str]:
    return [f"{indent}{line}" for line in text.splitlines() or [""]]


def _compact_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return repr(value)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) else None


def _float_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
