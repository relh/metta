from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

import cog_cyborg.policy.anthropic_pilot as pilot_policy_mod
import cog_cyborg.runtime.anthropic_pilot as pilot_runtime_mod
from cog_cyborg.memory import MemoryStore
from cog_cyborg.policy.anthropic_pilot import (
    AnthropicCyborgPolicy,
    AnthropicPilotAgentPolicy,
    AnthropicPilotSession,
    build_pilot_artifact_store,
    build_pilot_memory_store,
)
from cog_cyborg.runtime import ArtifactStore
from mettagrid_sdk.sdk import (
    GridPosition,
    LogRecord,
    MettagridState,
    ReviewRequest,
    SelfState,
    SemanticEvent,
    TeamSummary,
)

from cogames.games.cogs_vs_clips.missions.machina_1 import make_cogsguard_mission
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator.simulator import Simulation


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessages:
    def __init__(self, texts: str | list[str]) -> None:
        self._texts = [texts] if isinstance(texts, str) else list(texts)
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        assert self._texts
        text = self._texts[0] if len(self._texts) == 1 else self._texts.pop(0)
        return type("FakeResponse", (), {"content": [_FakeTextBlock(text)]})()


class _FakeClient:
    def __init__(self, texts: str | list[str]) -> None:
        self.messages = _FakeMessages(texts)


def _prompt_text(fake_client: _FakeClient, call_index: int) -> str:
    call = cast(dict[str, Any], fake_client.messages.calls[call_index])
    messages = cast(list[dict[str, Any]], call["messages"])
    return cast(str, messages[0]["content"])


class _RecordingPilotSession:
    def __init__(self) -> None:
        self.artifact_store = None
        self.generation_count = 1
        self.last_generation_step: int | None = None
        self.runtime_reviews: list[dict[str, str]] = []

    def schedule_runtime_log(
        self,
        *,
        record: LogRecord,
        extra_context: str,
    ) -> None:
        assert record.review is not None
        self.runtime_reviews.append(
            {
                "trigger_name": record.review.trigger_name,
                "request_summary": record.review.prompt or record.message,
                "extra_context": extra_context,
            }
        )


def _directive_policy_source(
    *,
    role: str = "miner",
    note: str = "opening coverage",
    register_trigger: bool = False,
    trigger_name: str = "enemy_seen",
    trigger_prompt: str = "Replan after contact.",
    review_step: int | None = None,
) -> str:
    lines = [
        "def step(sdk):",
        "    agent_id = sdk.helpers.agent_id()",
        "    objectives = sdk.helpers.shared_objectives()",
        "    current = next(",
        "        (item.split(':', 1)[1] for item in objectives if item.startswith('current_objective:')),",
        "        'resource_coverage',",
        "    )",
        "    resources = ['carbon', 'oxygen', 'germanium', 'silicon']",
    ]
    if register_trigger or review_step is not None:
        lines.extend(
            [
                f'    sdk.log.register_review_trigger("{trigger_name}", "{trigger_prompt}", target="policy")',
            ]
        )
    if review_step is not None:
        lines.extend(
            [
                f"    if sdk.state.step == {review_step}:",
                f'        sdk.log.request_review("{trigger_name}", "Switch roles.", target="policy")',
            ]
        )
    if role == "miner":
        lines.extend(
            [
                "    return {",
                "        'role': 'miner',",
                "        'resource_bias': resources[agent_id % len(resources)],",
                "        'objective': current,",
                f"        'note': {note!r},",
                "    }",
            ]
        )
    else:
        lines.append(f"    return {{'role': {role!r}, 'objective': current, 'note': {note!r}}}")
    return "\n".join(lines)


def _review_response(
    policy_source: str,
    *,
    scratchpad: str = "",
    plan: str = "",
    review_summary: str = "",
) -> str:
    payload = {
        "set_policy": policy_source,
        "review_summary": review_summary,
    }
    if scratchpad:
        payload["replace_scratchpad"] = scratchpad
    if plan:
        payload["replace_plan"] = plan
    return json.dumps(payload)


def _build_state(
    *,
    step: int,
    agent_id: int = 2,
    shared_inventory: dict[str, int] | None = None,
    inventory: dict[str, int] | None = None,
    recent_events: list[SemanticEvent] | None = None,
) -> MettagridState:
    return MettagridState(
        game="cogsguard",
        step=step,
        self_state=SelfState(
            entity_id=f"agent-{agent_id}",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"agent_id": agent_id, "team": "cogs"},
            inventory={} if inventory is None else inventory,
        ),
        team_summary=TeamSummary(team_id="cogs", shared_inventory={} if shared_inventory is None else shared_inventory),
        recent_events=[] if recent_events is None else recent_events,
    )


def test_policy_anthropic_pilot_reexports_runtime_surface() -> None:
    assert pilot_policy_mod.AnthropicPilotSession is pilot_runtime_mod.AnthropicPilotSession
    assert pilot_policy_mod.DEFAULT_GOAL == pilot_runtime_mod.DEFAULT_GOAL
    assert pilot_policy_mod.DEFAULT_MAX_TOKENS == pilot_runtime_mod.DEFAULT_MAX_TOKENS
    assert (
        pilot_policy_mod.DEFAULT_PILOT_POLICY_TIMEOUT_SECONDS == pilot_runtime_mod.DEFAULT_PILOT_POLICY_TIMEOUT_SECONDS
    )
    assert pilot_policy_mod.DEFAULT_POLICY_TIMEOUT_SECONDS == pilot_runtime_mod.DEFAULT_POLICY_TIMEOUT_SECONDS
    assert pilot_policy_mod.DEFAULT_TEMPERATURE == pilot_runtime_mod.DEFAULT_TEMPERATURE
    assert pilot_policy_mod.SharedPilotContext is pilot_runtime_mod.SharedPilotContext
    assert pilot_policy_mod.build_pilot_artifact_store is pilot_runtime_mod.build_pilot_artifact_store
    assert pilot_policy_mod.build_pilot_memory_store is pilot_runtime_mod.build_pilot_memory_store
    assert pilot_policy_mod.coerce_bool_arg is pilot_runtime_mod.coerce_bool_arg


def test_anthropic_pilot_session_generates_typed_directives() -> None:
    session = AnthropicPilotSession(
        client=_FakeClient(_review_response(_directive_policy_source(note="opening coverage"))),
        model="fake",
    )
    memory = MemoryStore()

    directive = session.directive_for_state(_build_state(step=1), memory=memory)

    assert directive.role == "miner"
    assert directive.resource_bias == "germanium"
    assert directive.objective == "resource_coverage"
    assert directive.note == "opening coverage"
    assert session.generation_count == 1

    bootstrap_directive = session.directive_for_state(
        _build_state(
            step=20,
            shared_inventory={"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 1},
        ),
        memory=memory,
    )

    assert bootstrap_directive.role == "miner"
    assert bootstrap_directive.objective == "economy_bootstrap"
    assert bootstrap_directive.note == "opening coverage"
    assert session.generation_count == 1


def test_anthropic_pilot_session_tracks_live_returned_objective() -> None:
    session = AnthropicPilotSession(
        client=_FakeClient(
            _review_response(
                "def step(sdk):\n"
                '    return {"role": "aligner", "objective": "aligner_pressure", "note": "force pressure"}'
            )
        ),
        model="fake",
    )
    memory = MemoryStore()

    directive = session.directive_for_state(_build_state(step=1), memory=memory)

    assert directive.objective == "aligner_pressure"
    assert session.current_objective == "aligner_pressure"


def test_anthropic_pilot_review_prompt_warns_against_rotation_after_many_rewrites() -> None:
    session = AnthropicPilotSession(
        client=_FakeClient(_review_response(_directive_policy_source(note="opening coverage"))),
        model="fake",
    )
    memory = MemoryStore()
    session.directive_for_state(_build_state(step=1), memory=memory)
    session._generation_count = 5

    sdk = session._build_sdk(_build_state(step=240), memory=memory)
    prompt = session._build_review_prompt(sdk, memory=memory)

    assert "High rewrite churn warning:" in prompt
    assert "do not add another miner/aligner/scrambler rotation" in prompt
    assert "simplify instead of adding more role rotations" in prompt


def test_anthropic_pilot_build_sdk_surfaces_objective_and_resource_context() -> None:
    session = AnthropicPilotSession(
        client=_FakeClient(_review_response(_directive_policy_source(note="opening coverage"))),
        model="fake",
    )
    memory = MemoryStore()
    session.directive_for_state(_build_state(step=1), memory=memory)

    sdk = session._build_sdk(
        _build_state(
            step=2,
            shared_inventory={"oxygen": 1},
            inventory={"carbon": 1},
        ),
        memory=memory,
    )

    assert "current_objective:resource_coverage" in sdk.helpers.shared_objectives()
    assert "seen_resource:carbon" in sdk.helpers.shared_objectives()
    assert "missing_resource:germanium" in sdk.helpers.shared_objectives()
    assert "missing_resource:silicon" in sdk.helpers.shared_objectives()


def test_anthropic_cyborg_policy_parses_record_step_traces_false_string() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=20)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())

    policy = AnthropicCyborgPolicy(
        env_info,
        model="fake",
        client=_FakeClient(""),
        record_step_traces="false",
    )

    assert cast(Any, policy)._pilot_session_kwargs["record_step_traces"] is False


def test_anthropic_pilot_session_does_not_outer_replan_on_local_events_without_review_logs() -> None:
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    session.directive_for_state(_build_state(step=1), memory=memory)

    directive = session.directive_for_state(
        _build_state(
            step=2,
            recent_events=[
                SemanticEvent(
                    event_id="heart_acquired:2",
                    event_type="heart_acquired",
                    step=2,
                    location=GridPosition(x=0, y=0),
                    importance=0.9,
                    summary="Agent acquired a heart.",
                    evidence=["heart=1"],
                )
            ],
        ),
        memory=memory,
    )

    assert directive.role == "miner"
    assert directive.note == "opening coverage"
    assert session.generation_count == 1
    assert len(fake_client.messages.calls) == 1


def test_anthropic_pilot_session_does_not_outer_replan_on_objective_change_without_review_logs() -> None:
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    opening = session.directive_for_state(_build_state(step=1), memory=memory)
    steady = session.directive_for_state(
        _build_state(
            step=2,
            shared_inventory={"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 1},
        ),
        memory=memory,
    )

    assert opening.note == "opening coverage"
    assert steady.note == "opening coverage"
    assert steady.objective == "economy_bootstrap"
    assert session.generation_count == 1
    assert len(fake_client.messages.calls) == 1


def test_anthropic_pilot_session_does_not_regress_objective_after_aligner_pressure() -> None:
    fake_client = _FakeClient(
        _review_response(
            "def step(sdk):\n"
            '    return {"role": "aligner", "objective": "aligner_pressure", "note": "pressure rewrite"}'
        )
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    pressure = session.directive_for_state(
        _build_state(
            step=1,
            shared_inventory={"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 1, "heart": 1},
        ),
        memory=memory,
    )
    pressure = session.directive_for_state(
        _build_state(
            step=2,
            shared_inventory={"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 1, "heart": 1},
        ),
        memory=memory,
    )
    steady = session.directive_for_state(
        _build_state(
            step=3,
            shared_inventory={"carbon": 1, "oxygen": 1, "germanium": 1, "silicon": 1, "heart": 0},
        ),
        memory=memory,
    )

    assert pressure.objective == "aligner_pressure"
    assert steady.objective == "aligner_pressure"
    assert session.last_generation_reason == "initial_generation"
    assert len(fake_client.messages.calls) == 1


def test_anthropic_pilot_session_applies_runtime_review_requests() -> None:
    fake_client = _FakeClient(
        [
            _review_response(_directive_policy_source(note="opening coverage", review_step=2)),
            _review_response(_directive_policy_source(role="aligner", note="requested rewrite")),
        ]
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    first = session.directive_for_state(_build_state(step=1), memory=memory)
    second = session.directive_for_state(_build_state(step=2), memory=memory)
    third = session.directive_for_state(_build_state(step=3), memory=memory)

    assert first.role == "miner"
    assert second.role == "miner"
    assert third.role == "aligner"
    assert session.generation_count == 2
    assert session.last_generation_reason == "enemy_seen"
    assert len(fake_client.messages.calls) == 2


def test_anthropic_pilot_session_defers_late_phase_shift_after_high_churn() -> None:
    fake_client = _FakeClient(
        _review_response(
            _directive_policy_source(
                note="opening coverage",
                trigger_name="phase_shift",
                trigger_prompt="Phase transition milestone.",
                review_step=450,
            )
        )
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    opening = session.directive_for_state(_build_state(step=1), memory=memory)
    session._generation_count = 6
    session._last_generation_step = 390

    steady = session.directive_for_state(_build_state(step=450), memory=memory)

    assert opening.note == "opening coverage"
    assert steady.note == "opening coverage"
    assert session.generation_count == 6
    assert len(fake_client.messages.calls) == 1


def test_anthropic_pilot_session_applies_pending_runtime_reviews() -> None:
    fake_client = _FakeClient(
        [
            _review_response(
                _directive_policy_source(
                    note="opening coverage",
                    register_trigger=True,
                    trigger_name="runtime_oscillation",
                    trigger_prompt="Rewrite after extractor oscillation.",
                )
            ),
            _review_response(_directive_policy_source(role="aligner", note="broke silicon loop")),
        ]
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    opening = session.directive_for_state(_build_state(step=1), memory=memory)
    session.schedule_runtime_log(
        record=LogRecord(
            level="warning",
            message="Two-cell extractor oscillation detected.",
            step=2,
            review=ReviewRequest(
                trigger_name="runtime_oscillation",
                prompt="Detected a two-cell mining loop around silicon.",
            ),
        ),
        extra_context=(
            "Recent low-level telemetry:\n"
            "- positions: 10,10 -> 10,11 -> 10,10 -> 10,11\n"
            "- subtask: mine_silicon\n"
            "- target_position: 12,10"
        ),
    )
    after_review = session.directive_for_state(_build_state(step=2), memory=memory)

    assert opening.role == "miner"
    assert after_review.role == "aligner"
    assert after_review.note == "broke silicon loop"
    assert session.generation_count == 2
    assert session.last_generation_reason == "runtime_oscillation"
    prompt = _prompt_text(fake_client, 1)
    assert "Detected a two-cell mining loop around silicon." in prompt
    assert "Recent low-level telemetry:" in prompt


def test_anthropic_pilot_session_ignores_runtime_logs_for_unregistered_triggers() -> None:
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    opening = session.directive_for_state(_build_state(step=1), memory=memory)
    session.schedule_runtime_log(
        record=LogRecord(
            level="warning",
            message="Two-cell extractor oscillation detected.",
            step=2,
            review=ReviewRequest(
                trigger_name="runtime_oscillation",
                prompt="Detected a two-cell mining loop around silicon.",
            ),
        ),
        extra_context="Recent low-level telemetry:\n- positions: 10,10 -> 10,11",
    )
    steady = session.directive_for_state(_build_state(step=2), memory=memory)

    assert opening.note == "opening coverage"
    assert steady.note == "opening coverage"
    assert session.generation_count == 1
    assert len(fake_client.messages.calls) == 1


def test_anthropic_pilot_session_supports_targeted_macro_directives() -> None:
    fake_client = _FakeClient(
        _review_response(
            "\n".join(
                [
                    "def step(sdk):",
                    "    return {",
                    "        'role': 'aligner',",
                    "        'target_entity_id': 'junction@6,0',",
                    "        'target_region': 'west_lane',",
                    "        'objective': 'aligner_pressure',",
                    "        'note': 'lock west lane',",
                    "    }",
                ]
            )
        )
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")

    directive = session.directive_for_state(_build_state(step=1), memory=MemoryStore())

    assert directive.role == "aligner"
    assert directive.target_entity_id == "junction@6,0"
    assert directive.target_region == "west_lane"
    assert directive.objective == "aligner_pressure"
    assert directive.note == "lock west lane"


def test_anthropic_pilot_prompt_mentions_shorthand_review_guidance() -> None:
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))
    session = AnthropicPilotSession(client=fake_client, model="fake")

    session.directive_for_state(_build_state(step=1), memory=MemoryStore())

    prompt = _prompt_text(fake_client, 0)
    assert 'sdk.log.register_review_trigger("enemy_seen", "Replan after contact.", target="policy")' in prompt
    assert 'sdk.log.request_review("enemy_seen", "Enemy on east lane.", target="policy")' in prompt
    assert 'review=ReviewRequest(trigger_name="enemy_seen", prompt="Replan after contact.")' in prompt
    assert "never write import or from ... import lines" in prompt
    assert "LogRecord, ReviewRequest, and ReviewTrigger are already available by name" in prompt
    assert "sdk.scratchpad or sdk.read_scratchpad()" in prompt
    assert "sdk.replace_scratchpad(...)" in prompt
    assert "do not wipe hook flags" in prompt
    assert "sdk.read_plan()" in prompt
    assert "sdk.replace_plan(...)" in prompt
    assert "sdk.append_plan(...)" in prompt
    assert "Do not treat sdk.memory itself as a raw string" in prompt
    assert "do not skip phases from totals alone" in prompt
    assert "keep the review hooks you still need" in prompt
    assert "move trigger registration behind a durable memory guard" in prompt
    assert "do not fire a phase_shift self-review on step 1" in prompt
    assert "prefer reviews triggered by sdk.log.write" in prompt
    assert "runtime_oscillation, runtime_target_fixation, runtime_bias_mismatch, or runtime_stagnation" in prompt
    assert (
        "register runtime_oscillation, runtime_target_fixation, runtime_bias_mismatch, and runtime_stagnation" in prompt
    )
    assert "register phase_shift / enemy_seen first" in prompt
    assert "preserve those runtime_* triggers so the LLM can keep revising the opening" in prompt
    assert "keep runtime_stagnation registered so the LLM can revisit a bad pressure pivot too" in prompt
    assert "keep it current with sdk.replace_plan(...)" in prompt
    assert "emit one concise sdk.log.write(LogRecord(...)) startup line at step 1" in prompt
    assert "memory.md" in prompt
    assert "plan.md" in prompt
    assert "experience_trace.jsonl" in prompt
    assert "review_transcript.log" in prompt
    assert "deposit_cycles: 3" in prompt
    assert "target_entity_id" in prompt
    assert "target_region" in prompt
    assert "use target_entity_id as the strongest control primitive" in prompt
    assert "use resource_bias only to prefer a resource type" in prompt
    assert "prefer target_entity_id over resource_bias" in prompt
    assert "do not reimplement low-level movement or mining loops in main.py" in prompt
    assert '"replace_plan":"<full plan.md text>"' in prompt
    assert 'do not add a redundant top-level "action" key' in prompt
    assert "change target_entity_id, target_region, resource_bias, role, or phase" in prompt
    assert "resource_coverage must have an explicit time/resource escape hatch" in prompt
    assert "bias toward the productive extractor" in prompt


def test_anthropic_pilot_session_retries_non_json_review_response() -> None:
    fake_client = _FakeClient(
        [
            "I would keep mining germanium for now.",
            _review_response(_directive_policy_source(note="opening coverage")),
        ]
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")

    directive = session.directive_for_state(_build_state(step=1), memory=MemoryStore())

    assert directive.note == "opening coverage"
    assert len(fake_client.messages.calls) == 2
    retry_prompt = _prompt_text(fake_client, 1)
    assert "Previous output failed validation" in retry_prompt
    assert "Return only the compact JSON object" in retry_prompt


def test_anthropic_pilot_prompt_includes_current_plan_without_duplication(tmp_path: Path) -> None:
    store = ArtifactStore(
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        main_file=tmp_path / "main.py",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
    )
    store.replace_plan("# Plan\n- Open with miners")
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))
    session = AnthropicPilotSession(client=fake_client, model="fake", artifact_store=store)

    session.directive_for_state(_build_state(step=1), memory=MemoryStore())

    prompt = _prompt_text(fake_client, 0)
    assert "Current plan.md:" in prompt
    assert "# Plan\n- Open with miners" in prompt
    assert prompt.count("Workspace files:") == 1


def test_anthropic_pilot_review_prompt_carries_forward_registered_triggers() -> None:
    fake_client = _FakeClient(
        [
            _review_response(_directive_policy_source(note="opening coverage", review_step=2)),
            _review_response(_directive_policy_source(role="aligner", note="requested rewrite")),
        ]
    )
    session = AnthropicPilotSession(client=fake_client, model="fake")
    memory = MemoryStore()

    session.directive_for_state(_build_state(step=1), memory=memory)
    session.directive_for_state(_build_state(step=2), memory=memory)

    review_prompt = _prompt_text(fake_client, 1)
    assert "Current registered review triggers:" in review_prompt
    assert "- enemy_seen" in review_prompt
    assert "Compact helper capabilities:" in review_prompt
    assert "Available Cogsguard tactical skills:" in review_prompt
    assert "prefer keyed sdk.memory[...] updates" in review_prompt
    assert "preserve or re-register any trigger hooks" in review_prompt
    assert "prefer milestone logs with LogRecord(..., review=ReviewRequest(...))" in review_prompt
    assert "use target_entity_id for one exact extractor or junction" in review_prompt
    assert "do not describe resource_bias as a lock" in review_prompt
    assert "change target_entity_id, target_region, resource_bias, or phase" in review_prompt
    assert "change the opening policy itself" in review_prompt


def test_anthropic_pilot_session_persists_per_agent_artifacts(tmp_path: Path) -> None:
    policy = AnthropicCyborgPolicy(
        PolicyEnvInterface.from_mg_cfg(make_cogsguard_mission(num_agents=8, max_steps=20).make_env()),
        model="fake",
        client=_FakeClient(
            _review_response(
                _directive_policy_source(note="opening coverage"),
                scratchpad="Open with mining coverage.",
                plan="# Plan\n- Open with miners",
            )
        ),
        artifact_dir=tmp_path,
    )
    mission = make_cogsguard_mission(num_agents=8, max_steps=20)
    sim = Simulation(mission.make_env())

    policy.agent_policy(0).step(sim.agent(0).observation)

    agent_root = tmp_path / "agent-0"
    main_file = agent_root / "main.py"
    assert main_file.exists()
    assert os.access(main_file, os.X_OK)
    assert (agent_root / "memory.md").exists()
    assert (agent_root / "plan.md").exists()
    assert (agent_root / "experience_trace.jsonl").exists()
    assert (agent_root / "pilot_generation.jsonl").exists()
    assert (agent_root / "pilot_execution.jsonl").exists()
    assert (agent_root / "review_transcript.log").exists()
    assert "initial_generation" in (agent_root / "review_transcript.log").read_text(encoding="utf-8")


def test_anthropic_pilot_session_exposes_live_plan_helpers_to_generated_policy(tmp_path: Path) -> None:
    store = ArtifactStore(
        strategy_file=tmp_path / "plan.md",
        scratchpad_file=tmp_path / "memory.md",
        main_file=tmp_path / "main.py",
        experience_file=tmp_path / "experience.jsonl",
        decision_file=tmp_path / "decisions.jsonl",
        generation_file=tmp_path / "generation.jsonl",
        execution_file=tmp_path / "execution.jsonl",
    )
    fake_client = _FakeClient(
        _review_response(
            "\n".join(
                [
                    "def step(sdk):",
                    "    plan = sdk.read_plan()",
                    "    if not plan:",
                    "        sdk.replace_plan('# Plan\\n- Hold east lane')",
                    "        plan = sdk.read_plan()",
                    "    return {'role': 'miner', 'objective': 'resource_coverage', 'note': plan.splitlines()[-1]}",
                ]
            )
        )
    )
    session = AnthropicPilotSession(client=fake_client, model="fake", artifact_store=store)

    directive = session.directive_for_state(_build_state(step=1), memory=MemoryStore())

    assert directive.note == "- Hold east lane"
    assert store.read_plan() == "# Plan\n- Hold east lane"


def test_build_memory_store_reloads_persisted_semantic_memory(tmp_path: Path) -> None:
    artifact_store = build_pilot_artifact_store(tmp_path, agent_id=0)
    assert artifact_store is not None
    memory = build_pilot_memory_store(artifact_store)
    memory.append_event(
        record_id="evt-1",
        event_type="enemy_seen",
        summary="Enemy spotted east.",
        game="cogsguard",
        step=3,
        role_context="aligner",
    )

    reloaded = build_pilot_memory_store(artifact_store)

    assert [record.summary for record in reloaded.recent_records(limit=1)] == ["Enemy spotted east."]


def test_anthropic_cyborg_policy_uses_per_agent_pilots_to_steer_semantic_baseline() -> None:
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))

    mission = make_cogsguard_mission(num_agents=8, max_steps=20)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    sim = Simulation(mission.make_env())
    policy = AnthropicCyborgPolicy(env_info, model="fake", client=fake_client)

    action_zero = policy.agent_policy(0).step(sim.agent(0).observation)
    infos_zero = policy.agent_policy(0).infos
    action_one = policy.agent_policy(1).step(sim.agent(1).observation)
    infos_one = policy.agent_policy(1).infos

    assert action_zero.name in env_info.action_names
    assert action_one.name in env_info.action_names
    assert infos_zero["directive_role"] == "miner"
    assert infos_zero["directive_resource_bias"] == "carbon"
    assert infos_zero["directive_objective"] == "resource_coverage"
    assert infos_zero["pilot_generation_count"] == 1
    assert infos_zero["__sidecar_debug__"]["events"][0]["kind"] == "llm_review"
    assert infos_zero["__sidecar_debug__"]["events"][0]["raw_response_text"]
    assert infos_one["directive_role"] == "miner"
    assert infos_one["directive_resource_bias"] == "oxygen"
    assert infos_one["pilot_generation_count"] == 1
    assert len(fake_client.messages.calls) == 2


def test_anthropic_agent_policy_requests_review_for_two_cell_oscillation() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=20)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 10), (10, 11), (10, 10), (10, 11)]
    for step, position in enumerate(positions, start=1):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_silicon",
            "summary": "mine_silicon",
            "target_kind": "silicon_extractor",
            "target_position": "12,10",
            "directive_objective": "resource_coverage",
            "oscillation_steps": 6,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_oscillation"
    assert "two-cell loop" in review["request_summary"]
    assert "change target, resource_bias, or phase" in review["request_summary"]
    assert "mine_silicon" in review["extra_context"]
    assert "12,10" in review["extra_context"]
    assert "oscillation_steps: 6" in review["extra_context"]


def test_anthropic_agent_policy_requests_review_for_extractor_target_fixation() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=200)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11), (10, 10)] * 2
    for step, position in enumerate(positions, start=24):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_germanium",
            "summary": "mine_germanium",
            "target_kind": "germanium_extractor",
            "target_position": "-8,10",
            "directive_objective": "resource_coverage",
            "oscillation_steps": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_target_fixation"
    assert "prolonged fixation on one extractor" in review["request_summary"]
    assert "change target, resource_bias, or phase" in review["request_summary"]
    assert "germanium_extractor" in review["extra_context"]
    assert "-8,10" in review["extra_context"]


def test_anthropic_agent_policy_requests_review_for_productive_bias_mismatch() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=200)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11), (10, 10), (10, 9), (10, 10), (10, 11)]
    for step, position in enumerate(positions, start=24):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_germanium",
            "summary": "mine_germanium",
            "target_kind": "germanium_extractor",
            "target_position": "-8,10",
            "directive_objective": "resource_coverage",
            "directive_resource_bias": "carbon",
            "oscillation_steps": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_bias_mismatch"
    assert "productive mining on one extractor type" in review["request_summary"]
    assert "favor the productive extractor" in review["request_summary"]
    assert "directive_resource_bias: carbon" in review["extra_context"]
    assert "productive_target_resource: germanium" in review["extra_context"]


def test_anthropic_agent_policy_does_not_review_when_bias_matches_productive_extractor() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=200)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11), (10, 10), (10, 9), (10, 10), (10, 11)]
    for step, position in enumerate(positions, start=24):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_germanium",
            "summary": "mine_germanium",
            "target_kind": "germanium_extractor",
            "target_position": "-8,10",
            "directive_objective": "resource_coverage",
            "directive_resource_bias": "germanium",
            "oscillation_steps": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert recording_session.runtime_reviews == []


def test_anthropic_agent_policy_requests_review_for_resource_coverage_stagnation() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=200)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
    targets = ["12,10", "13,10"] * 6
    for step, (position, target_position) in enumerate(zip(positions, targets, strict=True), start=96):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_carbon",
            "summary": "mine_carbon",
            "target_kind": "carbon_extractor",
            "target_position": target_position,
            "directive_objective": "resource_coverage",
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_stagnation"
    assert "resource_coverage" in review["request_summary"]
    assert "generation_count: 1" in review["extra_context"]
    assert "mine_carbon" in review["extra_context"]


def test_anthropic_agent_policy_can_revisit_resource_coverage_stagnation_after_a_rewrite() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=400)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 2
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
    targets = ["12,10", "13,10"] * 6
    for step, (position, target_position) in enumerate(zip(positions, targets, strict=True), start=320):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_germanium",
            "summary": "mine_germanium",
            "target_kind": "germanium_extractor",
            "target_position": target_position,
            "directive_objective": "resource_coverage",
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_stagnation"
    assert "escape hatch" in review["request_summary"]
    assert "generation_count: 2" in review["extra_context"]


def test_anthropic_agent_policy_requests_review_for_economy_bootstrap_stagnation() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=400)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 3
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
    targets = ["-8,10", "-8,10", "-8,10", "-8,10"] * 3
    subtasks = ["mine_germanium", "mine_germanium", "deposit_resources", "find_extractors"] * 3
    for step, (position, target_position, subtask) in enumerate(
        zip(positions, targets, subtasks, strict=True),
        start=160,
    ):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": subtask,
            "summary": subtask,
            "target_kind": "germanium_extractor",
            "target_position": target_position,
            "directive_objective": "economy_bootstrap",
            "heart": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_stagnation"
    assert "economy_bootstrap" in review["request_summary"]
    assert "hearts: 0 | 0 | 0" in review["extra_context"]
    assert "generation_count: 3" in review["extra_context"]


def test_anthropic_agent_policy_waits_before_repeating_stagnation_after_recent_rewrite() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=500)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 3
    recording_session.last_generation_step = 97
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
    targets = ["-8,10", "-8,10", "-8,10", "-8,10"] * 3
    subtasks = ["mine_germanium", "mine_germanium", "deposit_resources", "find_extractors"] * 3
    for step, (position, target_position, subtask) in enumerate(
        zip(positions, targets, subtasks, strict=True),
        start=160,
    ):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": subtask,
            "summary": subtask,
            "target_kind": "germanium_extractor",
            "target_position": target_position,
            "directive_objective": "economy_bootstrap",
            "heart": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert recording_session.runtime_reviews == []


def test_anthropic_agent_policy_requests_review_for_aligner_pressure_stagnation() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=500)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 5
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(5, 5), (5, 6), (5, 7), (5, 6)] * 3
    targets = ["5,-32", "5,-32", "5,-32", "5,-32"] * 3
    subtasks = ["find_neutral_junction", "align_junction", "align_junction", "retreat_to_hub"] * 3
    for step, (position, target_position, subtask) in enumerate(
        zip(positions, targets, subtasks, strict=True),
        start=220,
    ):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": subtask,
            "summary": subtask,
            "target_kind": "junction",
            "target_position": target_position,
            "directive_objective": "aligner_pressure",
            "heart": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    review = recording_session.runtime_reviews[0]
    assert review["trigger_name"] == "runtime_stagnation"
    assert "aligner_pressure" in review["request_summary"]
    assert "target_region, role, or phase" in review["request_summary"]
    assert "current_target_kind: junction" in review["extra_context"]
    assert "generation_count: 5" in review["extra_context"]


def test_anthropic_agent_policy_extends_quiet_period_after_high_churn_rewrite() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=700)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 5
    recording_session.last_generation_step = 317
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    positions = [(5, 5), (5, 6), (5, 7), (5, 6)] * 3
    targets = ["5,-32", "5,-32", "5,-32", "5,-32"] * 3
    subtasks = ["find_neutral_junction", "align_junction", "align_junction", "retreat_to_hub"] * 3
    for step, (position, target_position, subtask) in enumerate(
        zip(positions, targets, subtasks, strict=True),
        start=413,
    ):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": subtask,
            "summary": subtask,
            "target_kind": "junction",
            "target_position": target_position,
            "directive_objective": "aligner_pressure",
            "heart": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    assert recording_session.runtime_reviews == []


def test_anthropic_agent_policy_slows_bootstrap_stagnation_after_many_rewrites() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=800)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 6
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    def feed_bootstrap_window(*, start_step: int, target_position: str) -> None:
        positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
        subtasks = ["mine_germanium", "mine_germanium", "deposit_resources", "find_extractors"] * 3
        for step, (position, subtask) in enumerate(zip(positions, subtasks, strict=True), start=start_step):
            agent_policy._step_index = step
            agent_policy._last_global_pos = position
            agent_policy._infos = {
                "subtask": subtask,
                "summary": subtask,
                "target_kind": "germanium_extractor",
                "target_position": target_position,
                "directive_objective": "economy_bootstrap",
                "heart": 0,
            }
            agent_policy._maybe_schedule_runtime_review()

    feed_bootstrap_window(start_step=160, target_position="-8,10")
    feed_bootstrap_window(start_step=353, target_position="-16,-2")

    assert len(recording_session.runtime_reviews) == 1
    assert recording_session.runtime_reviews[0]["trigger_name"] == "runtime_stagnation"


def test_anthropic_agent_policy_revisits_aligner_pressure_after_cooldown() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=700)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 5
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    def feed_pressure_window(*, start_step: int, target_position: str) -> None:
        positions = [(5, 5), (5, 6), (5, 7), (5, 6)] * 3
        subtasks = ["find_neutral_junction", "align_junction", "align_junction", "retreat_to_hub"] * 3
        for step, (position, subtask) in enumerate(zip(positions, subtasks, strict=True), start=start_step):
            agent_policy._step_index = step
            agent_policy._last_global_pos = position
            agent_policy._infos = {
                "subtask": subtask,
                "summary": subtask,
                "target_kind": "junction",
                "target_position": target_position,
                "directive_objective": "aligner_pressure",
                "heart": 0,
            }
            agent_policy._maybe_schedule_runtime_review()

    feed_pressure_window(start_step=220, target_position="5,-32")
    feed_pressure_window(start_step=317, target_position="7,-28")

    assert len(recording_session.runtime_reviews) == 2
    assert all(review["trigger_name"] == "runtime_stagnation" for review in recording_session.runtime_reviews)
    assert "current_target_position: 7,-28" in recording_session.runtime_reviews[-1]["extra_context"]


def test_anthropic_agent_policy_applies_global_stagnation_cooldown_after_high_churn() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=900)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 6
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    pressure_positions = [(5, 5), (5, 6), (5, 7), (5, 6)] * 3
    pressure_subtasks = ["find_neutral_junction", "align_junction", "align_junction", "retreat_to_hub"] * 3
    for step, (position, subtask) in enumerate(zip(pressure_positions, pressure_subtasks, strict=True), start=220):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": subtask,
            "summary": subtask,
            "target_kind": "junction",
            "target_position": "5,-32",
            "directive_objective": "aligner_pressure",
            "heart": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    resource_positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
    resource_targets = ["12,10", "13,10"] * 6
    for step, (position, target_position) in enumerate(
        zip(resource_positions, resource_targets, strict=True),
        start=320,
    ):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_carbon",
            "summary": "mine_carbon",
            "target_kind": "carbon_extractor",
            "target_position": target_position,
            "directive_objective": "resource_coverage",
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    assert "aligner_pressure" in recording_session.runtime_reviews[0]["request_summary"]


def test_anthropic_agent_policy_slows_stagnation_reviews_after_high_churn() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=700)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 8
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    def feed_pressure_window(*, start_step: int, target_position: str) -> None:
        positions = [(5, 5), (5, 6), (5, 7), (5, 6)] * 3
        subtasks = ["find_neutral_junction", "align_junction", "align_junction", "retreat_to_hub"] * 3
        for step, (position, subtask) in enumerate(zip(positions, subtasks, strict=True), start=start_step):
            agent_policy._step_index = step
            agent_policy._last_global_pos = position
            agent_policy._infos = {
                "subtask": subtask,
                "summary": subtask,
                "target_kind": "junction",
                "target_position": target_position,
                "directive_objective": "aligner_pressure",
                "heart": 0,
            }
            agent_policy._maybe_schedule_runtime_review()

    feed_pressure_window(start_step=220, target_position="5,-32")
    feed_pressure_window(start_step=317, target_position="7,-28")

    assert len(recording_session.runtime_reviews) == 1
    assert recording_session.runtime_reviews[0]["trigger_name"] == "runtime_stagnation"


def test_anthropic_agent_policy_applies_global_stagnation_cooldown_after_extreme_churn() -> None:
    mission = make_cogsguard_mission(num_agents=1, max_steps=900)
    env_info = PolicyEnvInterface.from_mg_cfg(mission.make_env())
    recording_session = _RecordingPilotSession()
    recording_session.generation_count = 12
    agent_policy = cast(
        AnthropicPilotAgentPolicy,
        AnthropicCyborgPolicy(env_info, model="fake", client=_FakeClient("")).agent_policy(0),
    )
    cast(Any, agent_policy)._pilot_session = recording_session

    pressure_positions = [(5, 5), (5, 6), (5, 7), (5, 6)] * 3
    pressure_subtasks = ["find_neutral_junction", "align_junction", "align_junction", "retreat_to_hub"] * 3
    for step, (position, subtask) in enumerate(zip(pressure_positions, pressure_subtasks, strict=True), start=220):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": subtask,
            "summary": subtask,
            "target_kind": "junction",
            "target_position": "5,-32",
            "directive_objective": "aligner_pressure",
            "heart": 0,
        }
        agent_policy._maybe_schedule_runtime_review()

    resource_positions = [(10, 10), (10, 11), (10, 12), (10, 11)] * 3
    resource_targets = ["12,10", "13,10"] * 6
    for step, (position, target_position) in enumerate(
        zip(resource_positions, resource_targets, strict=True),
        start=320,
    ):
        agent_policy._step_index = step
        agent_policy._last_global_pos = position
        agent_policy._infos = {
            "subtask": "mine_carbon",
            "summary": "mine_carbon",
            "target_kind": "carbon_extractor",
            "target_position": target_position,
            "directive_objective": "resource_coverage",
        }
        agent_policy._maybe_schedule_runtime_review()

    assert len(recording_session.runtime_reviews) == 1
    assert "aligner_pressure" in recording_session.runtime_reviews[0]["request_summary"]


def test_anthropic_cyborg_policy_collects_resources_in_live_simulation() -> None:
    fake_client = _FakeClient(_review_response(_directive_policy_source(note="opening coverage")))

    mission = make_cogsguard_mission(num_agents=8, max_steps=120)
    env_cfg = mission.make_env()
    env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)
    sim = Simulation(env_cfg, seed=42)
    policy = AnthropicCyborgPolicy(env_info, model="fake", client=fake_client)

    for _step in range(120):
        for agent_id in range(sim.num_agents):
            action = policy.agent_policy(agent_id).step(sim.agent(agent_id).observation)
            sim.agent(agent_id).set_action(action)
        sim.step()

    gained_by_resource = {
        resource: sum(agent_stats.get(f"{resource}.gained", 0.0) for agent_stats in sim.episode_stats["agent"])
        for resource in ("carbon", "oxygen", "germanium", "silicon")
    }

    assert any(amount > 0 for amount in gained_by_resource.values())
    assert sum(gained_by_resource.values()) > 0
    assert len(fake_client.messages.calls) >= sim.num_agents
