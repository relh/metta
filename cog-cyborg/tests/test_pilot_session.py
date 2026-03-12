from __future__ import annotations

import threading
from pathlib import Path

from cog_cyborg.providers import CodeReviewResponse
from cog_cyborg.runtime import ArtifactStore, LivePolicyBundleSession, PolicyGenerationRecord
from mettagrid_sdk.sdk import (
    ActionCatalog,
    ActionDescriptor,
    GridPosition,
    LogRecord,
    MemoryQuery,
    MemoryRecord,
    MettagridSDK,
    MettagridState,
    RetrievedMemoryRecord,
    ReviewRequest,
    ReviewTrigger,
    SelfState,
    StateHelperCatalog,
    TeamSummary,
)


class _MemoryStub:
    def __init__(self) -> None:
        self._scratchpad = "Hold east."

    def recent_records(self, limit: int = 10) -> list[MemoryRecord]:
        return [MemoryRecord(record_id="evt-1", kind="event", summary="opening")]

    def retrieve(self, query: MemoryQuery, limit: int = 10) -> list[RetrievedMemoryRecord]:
        del query
        return [
            RetrievedMemoryRecord(
                record=MemoryRecord(record_id="evt-1", kind="event", summary="opening"),
                score=1.0,
                relevance_score=1.0,
                recency_score=0.0,
                importance_score=0.0,
            )
        ][:limit]

    def render_prompt_context(self, query: MemoryQuery, limit: int = 6) -> str:
        del query, limit
        return "=== RETRIEVED SEMANTIC MEMORY ===\n  - [event] opening"

    def read_scratchpad(self) -> str:
        return self._scratchpad

    def replace_scratchpad(self, text: str) -> None:
        self._scratchpad = text

    def append_scratchpad(self, text: str) -> None:
        self._scratchpad += text

    def get(self, key: str, default: object = None) -> object:
        prefix = f"{key}: "
        for line in self._scratchpad.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return default

    def setdefault(self, key: str, default: object = None) -> object:
        value = self.get(key, None)
        if value is not None:
            return value
        self._scratchpad += ("" if not self._scratchpad else "\n") + f"{key}: {default}"
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
                lines.append(f"{key}: {value}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"{key}: {value}")
        self._scratchpad = "\n".join(lines)

    def split(self, sep: str | None = None, maxsplit: int = -1) -> list[str]:
        return self._scratchpad.split(sep, maxsplit)

    def splitlines(self, keepends: bool = False) -> list[str]:
        return self._scratchpad.splitlines(keepends)

    def strip(self, chars: str | None = None) -> str:
        return self._scratchpad.strip(chars)


class _LogStub:
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


class _FakeCodeBackend:
    def __init__(self, responses: list[CodeReviewResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls = []

    def review(self, request) -> CodeReviewResponse:
        self.calls.append(request)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _BlockingCodeBackend:
    def __init__(self, response: CodeReviewResponse) -> None:
        self._response = response
        self.calls = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def review(self, request) -> CodeReviewResponse:
        self.calls.append(request)
        self.entered.set()
        assert self.release.wait(timeout=1.0)
        return self._response


def _build_sdk() -> MettagridSDK:
    state = MettagridState(
        game="cogsguard",
        step=5,
        self_state=SelfState(
            entity_id="agent-0",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"agent_id": 0},
        ),
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 4},
            shared_objectives=["missing_resource:oxygen"],
        ),
    )
    return MettagridSDK(
        state=state,
        actions=ActionCatalog([ActionDescriptor(name="return_macro_directive", description="return a directive")]),
        helpers=StateHelperCatalog(state),
        memory=_MemoryStub(),
        log=_LogStub(),
    )


def test_artifact_store_writes_and_reads_generation_records(tmp_path: Path) -> None:
    generation_file = tmp_path / "generation.jsonl"
    store = ArtifactStore(generation_file=generation_file)

    store.append_generation_record(
        PolicyGenerationRecord(
            step=3,
            agent_id=0,
            prompt="write a policy",
            raw_response='{"set_policy":"def step(sdk):\\n    return {}"}',
            policy_source="def step(sdk):\n    return {}",
            success=True,
            metadata={"model": "fake"},
        )
    )

    records = store.read_recent_generation_records(max_entries=2)
    context = store.build_prompt_context()

    assert records[0].step == 3
    assert records[0].metadata == {"model": "fake"}
    assert "SDK GENERATION RECORDS" in context
    assert "success=True" in context


def test_live_policy_bundle_session_rewrites_policy_and_scratchpad(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy=(
                    "def step(sdk):\n"
                    '    sdk.log.request_review(ReviewRequest(trigger_name="enemy_seen", prompt="Switch roles."))\n'
                    '    return {"role": "miner"}'
                ),
                replace_plan="# Plan\n- Open with mining coverage",
                replace_scratchpad="Open with mining coverage.",
            ),
            CodeReviewResponse(
                action="memory_and_policy",
                set_policy='def step(sdk):\n    return {"role": "aligner"}',
                replace_plan="# Plan\n- Transition into aligner pressure",
                replace_scratchpad="Transition into aligner pressure.",
                review_summary="Enemy contact triggered a rewrite.",
            ),
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    result = session.execute(sdk=_build_sdk(), prompt="write live policy", step=5, agent_id=0, goal="pressure")

    assert result.success is True
    assert result.return_value == {"role": "miner"}
    assert store.read_main_source().endswith('return {"role": "aligner"}')
    assert store.read_plan().endswith("aligner pressure")
    assert store.read_scratchpad() == "Transition into aligner pressure."
    decision = store.read_recent_decision_records(max_entries=1)[0]
    assert decision.policy_updated is True
    assert decision.request_summary == "Switch roles."


def test_live_policy_bundle_session_supports_external_review_rewrites(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="memory_and_policy",
                set_policy='def step(sdk):\n    return {"role": "miner"}',
                replace_plan="# Plan\n- Open with miners",
                replace_scratchpad="Open with mining coverage.",
            ),
            CodeReviewResponse(
                action="memory_and_policy",
                set_policy='def step(sdk):\n    return {"role": "aligner"}',
                replace_plan="# Plan\n- Switch to aligner pressure",
                replace_scratchpad="Switch to aligner pressure.",
                review_summary="Objective changed.",
            ),
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    initial = session.execute(sdk=_build_sdk(), prompt="write live policy", step=5, agent_id=0, goal="coverage")
    review = session.review(
        prompt="Objective changed to pressure.",
        step=6,
        agent_id=0,
        trigger_name="objective:aligner_pressure",
        goal="pressure",
    )
    updated = session.execute(sdk=_build_sdk(), prompt="reuse live policy", step=7, agent_id=0, goal="pressure")

    assert initial.return_value == {"role": "miner"}
    assert review.action == "memory_and_policy"
    assert updated.return_value == {"role": "aligner"}
    assert store.read_plan().endswith("aligner pressure")
    assert store.read_scratchpad() == "Switch to aligner pressure."
    assert store.read_recent_decision_records(max_entries=1)[0].trigger_name == "objective:aligner_pressure"


def test_live_policy_bundle_session_can_skip_step_trace_artifacts(tmp_path: Path) -> None:
    execution_file = tmp_path / "execution.jsonl"
    experience_file = tmp_path / "experience.jsonl"
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=experience_file,
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=execution_file,
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy='def step(sdk):\n    return {"role": "miner"}',
            )
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store, record_step_traces=False)

    result = session.execute(sdk=_build_sdk(), prompt="write live policy", step=5, agent_id=0, goal="coverage")

    assert result.success is True
    assert result.return_value == {"role": "miner"}
    assert not execution_file.exists()
    assert not experience_file.exists()
    assert store.read_recent_generation_records(max_entries=1)[0].success is True


def test_live_policy_bundle_session_preserves_review_hook_flags_on_scratchpad_replace(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    store.replace_scratchpad("phase: resource_coverage\nreview_hooks_ready: true\nhooks_ready: true")
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="memory",
                replace_scratchpad="phase: economy_bootstrap\nrole: miner",
                review_summary="Phase transition confirmed.",
            )
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    session.review(
        prompt="Transition to economy_bootstrap.",
        step=97,
        agent_id=0,
        trigger_name="phase_shift",
        goal="pressure",
    )

    assert store.read_scratchpad() == (
        "phase: economy_bootstrap\nrole: miner\nhooks_ready: true\nreview_hooks_ready: true"
    )


def test_live_policy_bundle_session_preserves_typed_runtime_keys_on_scratchpad_replace(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    store.replace_scratchpad("phase: resource_coverage\ndeposit_cycles: 2\nreview_hooks_ready: true")
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="memory",
                replace_scratchpad="phase: economy_bootstrap\ndeposit_cycles: tracked",
                review_summary="Tightened the escape hatch.",
            )
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    session.review(
        prompt="Tighten the coverage escape hatch.",
        step=97,
        agent_id=0,
        trigger_name="runtime_stagnation",
        goal="pressure",
    )

    assert store.read_scratchpad() == ("phase: economy_bootstrap\ndeposit_cycles: 2\nreview_hooks_ready: true")


def test_live_policy_bundle_session_uses_typed_review_requests_inside_log_records(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy=(
                    "def step(sdk):\n"
                    '    sdk.log.register_review_trigger(ReviewTrigger(name="extractor_fixation"))\n'
                    "    sdk.log.write(\n"
                    "        LogRecord(\n"
                    '            level="warning",\n'
                    '            message="Still mining one extractor.",\n'
                    "            step=sdk.state.step,\n"
                    "            review=ReviewRequest(\n"
                    '                trigger_name="extractor_fixation",\n'
                    '                prompt="Rewrite the opening to change target or phase.",\n'
                    "            ),\n"
                    '            data={"subtask": "mine_germanium"},\n'
                    "        )\n"
                    "    )\n"
                    '    return {"role": "miner"}'
                ),
            ),
            CodeReviewResponse(
                action="policy",
                set_policy='def step(sdk):\n    return {"role": "aligner"}',
                review_summary="Switched out of extractor fixation.",
            ),
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    result = session.execute(sdk=_build_sdk(), prompt="write live policy", step=24, agent_id=0, goal="coverage")

    assert result.success is True
    decision = store.read_recent_decision_records(max_entries=1)[0]
    assert decision.trigger_name == "extractor_fixation"
    assert decision.request_summary == "Rewrite the opening to change target or phase."
    assert backend.calls[1].trigger_name == "extractor_fixation"


def test_live_policy_bundle_session_uses_returned_objective_in_same_step_review_metadata(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy=(
                    "def step(sdk):\n"
                    '    sdk.log.register_review_trigger(ReviewTrigger(name="phase_shift"))\n'
                    "    sdk.log.request_review(\n"
                    '        ReviewRequest(trigger_name="phase_shift", prompt="Moved to pressure.")\n'
                    "    )\n"
                    '    return {"role": "aligner", "objective": "aligner_pressure"}'
                ),
            ),
            CodeReviewResponse(
                action="memory",
                review_summary="Phase shift acknowledged.",
            ),
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    result = session.execute(
        sdk=_build_sdk(),
        prompt="write live policy",
        step=97,
        agent_id=0,
        goal="pressure",
        metadata={"objective": "resource_coverage"},
    )

    assert result.success is True
    decision = store.read_recent_decision_records(max_entries=1)[0]
    assert decision.trigger_name == "phase_shift"
    assert decision.metadata["objective"] == "aligner_pressure"
    assert store.read_recent_experience_records(max_entries=1)[0].metadata["objective"] == "aligner_pressure"


def test_live_policy_bundle_session_can_suppress_selected_review_request(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy=(
                    "def step(sdk):\n"
                    '    sdk.log.register_review_trigger(ReviewTrigger(name="phase_shift"))\n'
                    "    sdk.log.request_review(\n"
                    '        ReviewRequest(trigger_name="phase_shift", prompt="Moved to pressure.")\n'
                    "    )\n"
                    '    return {"role": "aligner", "objective": "aligner_pressure"}'
                ),
            ),
            CodeReviewResponse(
                action="memory",
                review_summary="This review should never run.",
            ),
        ]
    )
    session = LivePolicyBundleSession(
        backend=backend,
        artifact_store=store,
        should_process_review_request=lambda request, *, step: request.trigger_name != "phase_shift" or step < 0,
    )

    result = session.execute(
        sdk=_build_sdk(),
        prompt="write live policy",
        step=97,
        agent_id=0,
        goal="pressure",
        metadata={"objective": "resource_coverage"},
    )

    assert result.success is True
    assert len(backend.calls) == 1
    decisions = store.read_recent_decision_records(max_entries=5)
    assert all(decision.trigger_name != "phase_shift" for decision in decisions)
    assert store.read_recent_experience_records(max_entries=1)[0].metadata["objective"] == "aligner_pressure"


def test_live_policy_bundle_session_treats_failed_reviews_as_noops(tmp_path: Path) -> None:
    store = ArtifactStore(
        main_file=tmp_path / "main.py",
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        log_file=tmp_path / "transcript.log",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
        policy_file=tmp_path / "policy.md",
    )
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy=(
                    "def step(sdk):\n"
                    '    sdk.log.request_review(ReviewRequest(trigger_name="enemy_seen", prompt="Switch roles."))\n'
                    '    return {"role": "miner"}'
                ),
            ),
            ValueError("Code review response did not contain a JSON object"),
        ]
    )
    session = LivePolicyBundleSession(backend=backend, artifact_store=store)

    result = session.execute(sdk=_build_sdk(), prompt="write live policy", step=5, agent_id=0, goal="coverage")

    assert result.success is True
    assert result.return_value == {"role": "miner"}
    assert store.read_main_source().endswith('return {"role": "miner"}')
    decision = store.read_recent_decision_records(max_entries=1)[0]
    assert decision.trigger_name == "enemy_seen"
    assert decision.action == "none"
    assert decision.metadata["review_error"] == "ValueError: Code review response did not contain a JSON object"


def test_live_policy_bundle_session_debug_snapshot_exposes_inflight_initial_generation() -> None:
    backend = _BlockingCodeBackend(
        CodeReviewResponse(
            action="policy",
            set_policy='def step(sdk):\n    return {"role": "miner"}',
        )
    )
    session = LivePolicyBundleSession(backend=backend)
    ensure_complete = threading.Event()

    def ensure_policy() -> None:
        session._ensure_policy(
            sdk=_build_sdk(),
            prompt="write live policy",
            step=1,
            agent_id=0,
            goal="coverage",
            metadata=None,
        )
        ensure_complete.set()

    thread = threading.Thread(target=ensure_policy)
    thread.start()
    assert backend.entered.wait(timeout=1.0)

    snapshot = session.debug_snapshot()

    assert snapshot["registered_triggers"] == []
    assert snapshot["pending_review"] == {
        "step": 1,
        "agent_id": 0,
        "trigger_name": "initial_generation",
        "request_source": "initial_generation",
        "request_summary": "Generate the initial policy.",
    }

    backend.release.set()
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    assert ensure_complete.is_set()
    assert session.policy_source.endswith('return {"role": "miner"}')
    assert "pending_review" not in session.debug_snapshot()


def test_live_policy_bundle_session_debug_snapshot_tracks_registered_trigger_names() -> None:
    backend = _FakeCodeBackend(
        [
            CodeReviewResponse(
                action="policy",
                set_policy='def step(sdk):\n    return {"role": "miner"}',
                triggers=[ReviewTrigger(name="enemy_seen", prompt="Replan after contact.", target="policy")],
            ),
            CodeReviewResponse(
                action="memory",
                review_summary="Keep the phase-shift hook active.",
                triggers=[ReviewTrigger(name="phase_shift", prompt="Re-evaluate the phase.", target="policy")],
            ),
        ]
    )
    session = LivePolicyBundleSession(backend=backend)

    session.execute(sdk=_build_sdk(), prompt="write live policy", step=5, agent_id=0, goal="coverage")
    session.review(
        prompt="refresh strategic hooks",
        step=6,
        agent_id=0,
        trigger_name="enemy_seen",
        goal="pressure",
        request_summary="Enemy on east lane.",
    )

    assert session.debug_snapshot()["registered_triggers"] == ["enemy_seen", "phase_shift"]
