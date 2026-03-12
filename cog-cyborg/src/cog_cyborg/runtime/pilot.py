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
        self._pending_review: dict[str, str | int] | None = None
        self._lock = threading.Lock()

    @property
    def policy_source(self) -> str:
        return self._policy_source

    def debug_snapshot(self) -> dict[str, object]:
        with self._lock:
            snapshot: dict[str, object] = {"registered_triggers": sorted(self._registered_trigger_names)}
            if self._pending_review is not None:
                snapshot["pending_review"] = dict(self._pending_review)
            return snapshot

    def reset(self) -> None:
        self._compiled_policy = None
        self._policy_source = ""
        with self._lock:
            self._registered_trigger_names.clear()
            self._pending_review = None

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
        review_request = self._select_review_request(result)
        if (
            review_request is not None
            and self._should_process_review_request is not None
            and not self._should_process_review_request(review_request, step=step)
        ):
            review_request = None
        if review_request is not None:
            self.review(
                prompt=f"{prompt}\n\nReview request: {review_request.prompt or review_request.trigger_name}",
                step=step,
                agent_id=agent_id,
                trigger_name=review_request.trigger_name,
                goal=goal,
                metadata=execution_metadata,
                request_summary=review_request.prompt or review_request.trigger_name,
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
        request_summary: str | None = None,
    ) -> CodeReviewResponse:
        response = self._perform_review(
            request=self._build_review_request(
                prompt=prompt,
                step=step,
                agent_id=agent_id,
                trigger_name=trigger_name,
                goal=goal,
                metadata=metadata,
            ),
            step=step,
            agent_id=agent_id,
            trigger_name=trigger_name,
            request_source="sdk.log.request_review",
            request_summary=request_summary or trigger_name,
        )
        policy_updated = False
        scratchpad_updated = False
        plan_updated = False
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
            self._set_policy_source(
                response.set_policy,
                step=step,
                agent_id=agent_id,
                prompt=prompt,
                raw_response=response.model_dump_json(),
                metadata=metadata,
            )
            policy_updated = True
        self._register_trigger_names(trigger.name for trigger in response.triggers)
        if self._artifact_store is not None:
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
                    metadata=_merge_review_metadata(
                        metadata,
                        (response.metadata if isinstance(response.metadata, dict) else None),
                    ),
                )
            )
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
            request_source="initial_generation",
            request_summary="Generate the initial policy.",
        )
        if response.replace_plan is not None and self._artifact_store is not None:
            self._artifact_store.replace_plan(response.replace_plan)
        if response.replace_scratchpad is not None and self._artifact_store is not None:
            self._artifact_store.replace_scratchpad(response.replace_scratchpad)
        if not response.set_policy:
            raise ValueError("Live policy backend did not return set_policy for initial generation")
        self._register_trigger_names(trigger.name for trigger in response.triggers)
        self._set_policy_source(
            response.set_policy,
            step=step,
            agent_id=agent_id,
            prompt=prompt,
            raw_response=response.model_dump_json(),
            metadata=metadata,
        )

    def _perform_review(
        self,
        *,
        request: CodeReviewRequest,
        step: int,
        agent_id: int,
        trigger_name: str,
        request_source: str,
        request_summary: str,
    ) -> CodeReviewResponse:
        with self._lock:
            self._pending_review = {
                "step": step,
                "agent_id": agent_id,
                "trigger_name": trigger_name,
                "request_source": request_source,
                "request_summary": request_summary,
            }
        try:
            return self._backend.review(request)
        except Exception as exc:
            review_error = f"{type(exc).__name__}: {exc}"
            return CodeReviewResponse(
                action="none",
                review_summary=f"Review failed: {review_error}",
                metadata={"review_error": review_error},
            )
        finally:
            with self._lock:
                self._pending_review = None

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
            experience_tail=("" if self._artifact_store is None else self._artifact_store.build_prompt_context()),
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
                return review_request
        if result.review_requests:
            return result.review_requests[0]
        return None

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
