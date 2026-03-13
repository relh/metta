from __future__ import annotations

import json
import threading
from typing import Any, cast

import cog_cyborg.runtime.execution as execution
import pytest
from cog_cyborg.runtime import (
    BoundedPolicyError,
    PolicyUpdate,
    compile_policy,
    execute_compiled_policy,
    render_sdk_reference,
)
from mettagrid_sdk.sdk import (
    ActionCatalog,
    ActionDescriptor,
    GridPosition,
    HelperCapability,
    HelperCatalog,
    KnownWorldState,
    LogRecord,
    MemoryQuery,
    MemoryRecord,
    MettagridSDK,
    MettagridState,
    RetrievedMemoryRecord,
    ReviewRequest,
    ReviewTrigger,
    SelfState,
    SemanticEntity,
    TeamSummary,
)


class MemoryStub:
    def __init__(self) -> None:
        self._records = [
            MemoryRecord(
                record_id="evt-1",
                kind="event",
                summary="Saw neutral junction.",
                game="cogsguard",
                step=10,
                role_context="aligner",
                tags=["junction", "neutral", "aligner"],
                importance=0.8,
            )
        ]
        self._scratchpad = "Capture neutral junctions with hearts."

    def recent_records(self, limit: int = 10) -> list[MemoryRecord]:
        return self._records[:limit]

    def retrieve(self, query: MemoryQuery, limit: int = 10) -> list[RetrievedMemoryRecord]:
        return [
            RetrievedMemoryRecord(
                record=self._records[0],
                score=0.92,
                relevance_score=0.85,
                recency_score=0.9,
                importance_score=0.8,
            )
        ][:limit]

    def render_prompt_context(self, query: MemoryQuery, limit: int = 6) -> str:
        return "=== RETRIEVED SEMANTIC MEMORY ===\n  - [event] step=10 Saw neutral junction."

    def read_scratchpad(self) -> str:
        return self._scratchpad

    def replace_scratchpad(self, text: str) -> None:
        self._scratchpad = text

    def append_scratchpad(self, text: str) -> None:
        self._scratchpad += text

    def get(self, key: str, default=None):
        prefix = f"{key}: "
        for line in self._scratchpad.splitlines():
            if line.startswith(prefix):
                return _parse_scratchpad_value(line[len(prefix) :])
        return default

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key, None) is not None

    def __getitem__(self, key: str) -> object:
        value = self.get(key, None)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: object) -> None:
        prefix = f"{key}: "
        lines = []
        replaced = False
        for line in self._scratchpad.splitlines():
            if line.startswith(prefix):
                lines.append(f"{key}: {_render_scratchpad_value(value)}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"{key}: {_render_scratchpad_value(value)}")
        self._scratchpad = "\n".join(lines)


class LogStub:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []
        self.triggers: list[ReviewTrigger] = []
        self.requests: list[ReviewRequest] = []

    def write(self, record: LogRecord) -> None:
        self.records.append(record)

    def register_review_trigger(self, trigger: ReviewTrigger) -> None:
        self.triggers.append(trigger)

    def request_review(self, request: ReviewRequest) -> None:
        self.requests.append(request)


def _build_sdk() -> tuple[MettagridSDK, LogStub]:
    log = LogStub()
    sdk = MettagridSDK(
        state=MettagridState(
            game="cogsguard",
            step=12,
            self_state=SelfState(
                entity_id="agent-0",
                entity_type="agent",
                position=GridPosition(x=0, y=0),
                role="aligner",
                inventory={"energy": 90, "heart": 1},
                labels=["friendly"],
                status=["has_heart"],
                attributes={"team": "cogs"},
            ),
            visible_entities=[
                SemanticEntity(
                    entity_id="junction@1,0",
                    entity_type="junction",
                    position=GridPosition(x=1, y=0),
                    labels=["neutral"],
                    attributes={"owner": "neutral"},
                )
            ],
            known_world=KnownWorldState(explored_regions=["spawn"], frontier_regions=["east_lane"]),
            team_summary=TeamSummary(team_id="cogs"),
        ),
        actions=ActionCatalog(
            [
                ActionDescriptor(
                    name="capture_junction",
                    description="Capture a neutral junction when carrying a heart.",
                    preconditions=["adjacent_to_junction", "inventory.heart>0"],
                    terminal_reasons=["success", "missing_heart"],
                )
            ]
        ),
        helpers=cast(
            Any,
            HelperCatalog(
                [
                    HelperCapability(
                        name="select_nearest_junction",
                        description="Return the nearest visible neutral junction.",
                    )
                ]
            ),
        ),
        memory=MemoryStub(),
        log=log,
    )
    return sdk, log


def _parse_scratchpad_value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _render_scratchpad_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _execute_policy_source(
    source: str,
    sdk: MettagridSDK,
    *,
    timeout_seconds: float = execution.DEFAULT_POLICY_TIMEOUT_SECONDS,
) -> execution.PolicyExecutionResult:
    return execute_compiled_policy(compile_policy(PolicyUpdate(source=source)), sdk, timeout_seconds=timeout_seconds)


def test_compile_policy_rejects_old_signature() -> None:
    with pytest.raises(BoundedPolicyError, match="step\\(sdk\\)"):
        compile_policy(PolicyUpdate(source='def step(obs, state):\n    return "noop"'))


def test_compile_policy_rejects_imports() -> None:
    with pytest.raises(BoundedPolicyError, match="imports are not allowed"):
        compile_policy(PolicyUpdate(source='import os\n\ndef step(sdk):\n    return os.getenv("HOME")'))


def test_execute_compiled_policy_captures_logs_and_return_value() -> None:
    sdk, log = _build_sdk()

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            '    sdk.log.write(LogRecord(level="info", message="choosing target", step=sdk.state.step))\n'
            '    return {"action": "capture_junction", "target": sdk.state.visible_entities[0].entity_id}'
        ),
        sdk,
    )

    assert result.success is True
    assert result.return_value == {"action": "capture_junction", "target": "junction@1,0"}
    assert result.logs[0].message == "choosing target"
    assert log.records[0].message == "choosing target"


def test_execute_compiled_policy_captures_review_requests() -> None:
    sdk, log = _build_sdk()

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            '    sdk.log.register_review_trigger(ReviewTrigger(name="enemy_seen", prompt="Change plan."))\n'
            '    sdk.log.request_review(ReviewRequest(trigger_name="enemy_seen", prompt="Enemy in lane."))\n'
            '    return {"action": "hold"}'
        ),
        sdk,
    )

    assert result.success is True
    assert result.review_triggers[0].name == "enemy_seen"
    assert result.review_requests[0].trigger_name == "enemy_seen"
    assert log.triggers[0].prompt == "Change plan."
    assert log.requests[0].prompt == "Enemy in lane."


def test_execute_compiled_policy_supports_review_api_shorthand() -> None:
    sdk, log = _build_sdk()

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            '    sdk.log.register_review_trigger("enemy_seen", "Change plan.", target="policy")\n'
            '    sdk.log.request_review("enemy_seen", "Enemy in lane.", target="memory")\n'
            '    return {"action": "hold"}'
        ),
        sdk,
    )

    assert result.success is True
    assert result.review_triggers[0].name == "enemy_seen"
    assert result.review_triggers[0].target == "policy"
    assert result.review_requests[0].trigger_name == "enemy_seen"
    assert result.review_requests[0].target == "memory"
    assert log.triggers[0].prompt == "Change plan."
    assert log.requests[0].prompt == "Enemy in lane."


def test_execute_compiled_policy_allows_keyword_review_trigger_shorthand() -> None:
    sdk, log = _build_sdk()

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            '    sdk.log.register_review_trigger(name="enemy_seen", prompt="Change plan.", target="policy")\n'
            '    return {"action": "hold"}'
        ),
        sdk,
    )

    assert result.success is True
    assert result.review_triggers[0].name == "enemy_seen"
    assert log.triggers[0].target == "policy"


def test_execute_compiled_policy_supports_sdk_scratchpad_helpers() -> None:
    sdk, _log = _build_sdk()
    sdk.memory.replace_scratchpad("phase: resource_coverage\nstep: 12")

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            '    previous = sdk.scratchpad.split("\\n")[0]\n'
            '    if "resource_coverage" in sdk.scratchpad:\n'
            '        sdk.replace_scratchpad("phase: aligner_pressure\\nstep: 12")\n'
            '        sdk.append_scratchpad("\\nlock: junction@1,0")\n'
            '    return {"previous": previous, "phase": sdk.memory.get("phase", "missing")}'
        ),
        sdk,
    )

    assert result.success is True
    assert result.return_value == {"previous": "phase: resource_coverage", "phase": "aligner_pressure"}
    assert sdk.memory.read_scratchpad().endswith("lock: junction@1,0")


def test_execute_compiled_policy_supports_scratchpad_memory_access() -> None:
    sdk, _log = _build_sdk()
    sdk.memory.replace_scratchpad("# World Model\nphase: resource_coverage")
    memory = cast(MemoryStub, sdk.memory)

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            '    previous = sdk.memory.get("phase", "unknown")\n'
            '    sdk.memory["phase"] = "aligner_pressure"\n'
            '    sdk.memory["missing"] = ["oxygen", "silicon"]\n'
            '    return {"previous_phase": previous, "phase": sdk.memory["phase"]}'
        ),
        sdk,
    )

    assert result.success is True
    assert result.return_value == {"previous_phase": "resource_coverage", "phase": "aligner_pressure"}
    assert memory.get("missing") == ["oxygen", "silicon"]
    assert "aligner_pressure" in memory.read_scratchpad()


def test_execute_compiled_policy_returns_structured_failure() -> None:
    sdk, _ = _build_sdk()

    result = _execute_policy_source("def step(sdk):\n    return 1 / 0", sdk)

    assert result.success is False
    assert result.error_type == "ZeroDivisionError"


def test_execute_compiled_policy_allows_next_builtin() -> None:
    sdk, _ = _build_sdk()

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            "    return next(\n"
            "        entity.entity_id\n"
            "        for entity in sdk.state.visible_entities\n"
            "        if entity.entity_type == 'junction'\n"
            "    )"
        ),
        sdk,
    )

    assert result.success is True
    assert result.return_value == "junction@1,0"


def test_execute_compiled_policy_allows_hasattr_builtin() -> None:
    sdk, _ = _build_sdk()

    result = _execute_policy_source(
        'def step(sdk):\n    return {"step": sdk.state.step if hasattr(sdk.state, "step") else -1}',
        sdk,
    )

    assert result.success is True
    assert result.return_value == {"step": 12}


def test_execute_compiled_policy_allows_exception_builtin() -> None:
    sdk, _ = _build_sdk()

    result = _execute_policy_source(
        (
            "def step(sdk):\n"
            "    return {'parsed': _parse_int('not-an-int')}\n\n"
            "def _parse_int(text):\n"
            "    try:\n"
            "        return int(text)\n"
            "    except Exception:\n"
            "        return -1\n"
        ),
        sdk,
    )

    assert result.success is True
    assert result.return_value == {"parsed": -1}


def test_execute_compiled_policy_times_out_infinite_loop() -> None:
    sdk, _ = _build_sdk()

    result = _execute_policy_source("def step(sdk):\n    while True:\n        pass", sdk, timeout_seconds=0.01)

    assert result.success is False
    assert result.error_type == "PolicyExecutionTimeoutError"
    assert "timeout" in (result.error_message or "")


def test_execute_compiled_policy_times_out_infinite_loop_off_main_thread() -> None:
    sdk, _ = _build_sdk()
    result_holder: dict[str, execution.PolicyExecutionResult] = {}

    def _run() -> None:
        result_holder["result"] = _execute_policy_source(
            "def step(sdk):\n    while True:\n        pass",
            sdk,
            timeout_seconds=0.01,
        )

    thread = threading.Thread(target=_run)
    thread.start()
    thread.join(timeout=1.0)

    assert not thread.is_alive()
    result = result_holder["result"]
    assert result.success is False
    assert result.error_type == "PolicyExecutionTimeoutError"
    assert "timeout" in (result.error_message or "")


def test_execute_compiled_policy_times_out_without_signal_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    sdk, _ = _build_sdk()
    monkeypatch.setattr(execution, "_supports_signal_timeout", lambda: False)

    result = _execute_policy_source("def step(sdk):\n    while True:\n        pass", sdk, timeout_seconds=0.01)

    assert result.success is False
    assert result.error_type == "PolicyExecutionTimeoutError"
    assert "timeout" in (result.error_message or "")


def test_render_sdk_reference_includes_actions_helpers_and_memory() -> None:
    sdk, _ = _build_sdk()

    rendered = render_sdk_reference(sdk)

    assert "METTAGRID SDK" in rendered
    assert "game: cogsguard" in rendered
    assert "capture_junction" in rendered
    assert "select_nearest_junction" in rendered
    assert "CONTROL PRIMITIVES" in rendered
    assert "target_entity_id: exact focus lock" in rendered
    assert "resource_bias: resource-type preference only" in rendered
    assert "SCRATCHPAD" in rendered
    assert "Capture neutral junctions with hearts." in rendered
    assert "Saw neutral junction." in rendered
