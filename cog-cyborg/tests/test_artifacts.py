from __future__ import annotations

import gc
from pathlib import Path

from cog_cyborg.runtime.artifacts import ArtifactStore
from cog_cyborg.runtime.execution import PolicyExecutionRecord, PolicyExecutionResult
from cog_cyborg.runtime.models import ExperienceTraceRecord, ReviewDecisionRecord
from mettagrid_sdk.sdk import LogRecord


def test_artifact_store_strategy_and_prompt_context(tmp_path: Path) -> None:
    strategy_file = tmp_path / "plan.md"
    policy_file = tmp_path / "policy.md"
    log_file = tmp_path / "fastpolicy.log"
    execution_file = tmp_path / "execution.jsonl"
    store = ArtifactStore(
        strategy_file=strategy_file,
        policy_file=policy_file,
        log_file=log_file,
        execution_file=execution_file,
    )

    store.replace_plan("# Plan\n- Prioritize junction control over extractor loops.")
    store.append_policy_update(step=7, agent_id=0, policy_source="def step(sdk):\n    return 'noop'")
    store.append_execution_record(
        PolicyExecutionRecord(
            step=8,
            agent_id=0,
            policy_source="def step(sdk):\n    return 'noop'",
            result=PolicyExecutionResult(
                success=True,
                return_value="noop",
                return_repr="noop",
                logs=[LogRecord(level="info", message="selected noop", step=8)],
            ),
        )
    )
    log_file.write_text("step=7 reward=1.0\nstep=8 reward=0.0")

    context = store.build_prompt_context(max_memory_entries=3, max_strategy_chars=2000)
    assert "CROSS-SESSION POLICY DOC" in context
    assert "def step(sdk):" in context
    assert "LIVE PLAN.MD" in context
    assert "Prioritize junction control" in context
    assert "REVIEW TRANSCRIPT LOG" in context
    assert "step=8 reward=0.0" in context
    assert "SDK EXECUTION RECORDS" in context
    assert "selected noop" in context


def test_artifact_store_tail_reads_only_recent_plan_entries(tmp_path: Path) -> None:
    strategy_file = tmp_path / "plan.md"
    store = ArtifactStore(strategy_file=strategy_file)
    strategy_file.write_text("\n".join(f"line-{index:03d}" for index in range(200)))

    strategy_tail = store.read_strategy(max_chars=40)
    assert "line-199" in strategy_tail


def test_artifact_store_reads_recent_execution_records(tmp_path: Path) -> None:
    execution_file = tmp_path / "execution.jsonl"
    store = ArtifactStore(execution_file=execution_file)

    for step in range(1, 4):
        store.append_execution_record(
            PolicyExecutionRecord(
                step=step,
                agent_id=0,
                policy_source=f"def step(sdk):\n    return {step}",
                result=PolicyExecutionResult(
                    success=True,
                    return_value=step,
                    return_repr=str(step),
                ),
            )
        )

    records = store.read_recent_execution_records(max_entries=2)

    assert [record.step for record in records] == [2, 3]
    assert records[-1].result.return_repr == "3"


def test_artifact_store_supports_live_bundle_files(tmp_path: Path) -> None:
    main_file = tmp_path / "main.py"
    plan_file = tmp_path / "plan.md"
    scratchpad_file = tmp_path / "memory.md"
    experience_file = tmp_path / "experience.jsonl"
    decision_file = tmp_path / "decisions.jsonl"
    store = ArtifactStore(
        main_file=main_file,
        strategy_file=plan_file,
        scratchpad_file=scratchpad_file,
        experience_file=experience_file,
        decision_file=decision_file,
    )

    store.write_main_source('def step(sdk):\n    return {"role": "miner"}')
    store.replace_plan("# Plan\n- Open with miners")
    store.replace_scratchpad("Open with mining coverage.")
    store.append_scratchpad("\nShift to aligners on contact.")
    store.append_experience_record(
        ExperienceTraceRecord(
            step=3,
            agent_id=0,
            summary="Enemy spotted east.",
            policy_source="main.py",
            return_repr='{"role":"miner"}',
            logs=["info:opening coverage"],
        )
    )
    store.append_decision_record(
        ReviewDecisionRecord(
            step=3,
            agent_id=0,
            trigger_name="enemy_seen",
            action="memory_and_policy",
            request_summary="Enemy contact triggered a rewrite.",
            summary="Swapped to aligner pressure.",
            append_log="Rotate toward pressure lanes.",
            policy_updated=True,
            scratchpad_updated=True,
            plan_updated=True,
        )
    )

    context = store.build_prompt_context()

    assert 'return {"role": "miner"}' in store.read_main_source()
    assert store.read_plan().startswith("# Plan")
    assert "aligners on contact" in store.read_scratchpad()
    assert store.read_recent_experience_records(max_entries=1)[0].summary == "Enemy spotted east."
    assert store.read_recent_decision_records(max_entries=1)[0].trigger_name == "enemy_seen"
    assert "LIVE MAIN.PY" in context
    assert "LIVE PLAN.MD" in context
    assert "PRIVATE SCRATCHPAD" in context
    assert "EXPERIENCE TRACE" in context
    assert "REVIEW DECISIONS" in context


def test_artifact_store_exposes_code_mode_bundle_layout(tmp_path: Path) -> None:
    store = ArtifactStore.for_code_mode_bundle(tmp_path, log_file_name="pilot_transcript.log")

    store.write_main_source('def step(sdk):\n    return {"objective": "resource_coverage"}')

    assert store.main_file == tmp_path / "main.py"
    assert store.strategy_file == tmp_path / "plan.md"
    assert store.scratchpad_file == tmp_path / "memory.md"
    assert store.experience_file == tmp_path / "experience_trace.jsonl"
    assert store.decision_file == tmp_path / "decision_log.jsonl"
    assert store.log_file == tmp_path / "pilot_transcript.log"
    assert store.main_file is not None
    assert store.main_file.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")
    assert store.read_main_source().startswith("def step(sdk):")


def test_artifact_store_ignores_missing_main_file_during_chmod(tmp_path: Path, monkeypatch) -> None:
    store = ArtifactStore(main_file=tmp_path / "main.py")
    original_stat = Path.stat

    def flaky_stat(path: Path):
        if path == store.main_file:
            raise FileNotFoundError
        return original_stat(path)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    store.write_main_source('def step(sdk):\n    return {"role": "miner"}')

    assert store.main_file is not None
    assert store.main_file.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")


def test_artifact_store_append_lock_cache_does_not_retain_completed_paths(tmp_path: Path) -> None:
    log_file = tmp_path / "pilot_transcript.log"
    ArtifactStore(log_file=log_file)

    ArtifactStore._append_text_atomic(log_file, "step=1 compiled\n")
    gc.collect()

    assert log_file.read_text(encoding="utf-8") == "step=1 compiled\n"
    assert log_file.resolve() not in ArtifactStore._append_locks
