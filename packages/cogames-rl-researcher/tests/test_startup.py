from __future__ import annotations

import json
from pathlib import Path

import cogames_rl_researcher.startup as startup_module
from cogames_rl_researcher.startup import StartupConfig, run_startup


def _write_fake_cogames(path: Path) -> None:
    script = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ[\"FAKE_COGAMES_STATE\"])
if state_path.exists():
    state = json.loads(state_path.read_text())
else:
    state = {}

argv = sys.argv[1:]
if not argv:
    print(\"missing command\", file=sys.stderr)
    sys.exit(1)

cmd = argv[0]
args = argv[1:]

state.setdefault(\"commands\", []).append(cmd)
state[\"last_args\"] = args

if cmd == \"login\":
    state[\"login_count\"] = state.get(\"login_count\", 0) + 1
    if \"--force\" in args:
        state[\"forced_login_count\"] = state.get(\"forced_login_count\", 0) + 1
    state_path.write_text(json.dumps(state))
    print(\"Authentication successful!\")
    sys.exit(0)

if cmd == \"scrimmage\":
    state[\"scrimmage_count\"] = state.get(\"scrimmage_count\", 0) + 1
    state_path.write_text(json.dumps(state))
    if os.environ.get(\"FAKE_AUTH_FAIL_ONCE\") == \"1\" and state[\"scrimmage_count\"] == 1:
        print(\"authentication failed\", file=sys.stderr)
        sys.exit(1)

    payload = {
        \"missions\": [
            {
                \"mission_summary\": {
                    \"avg_game_stats\": {
                        \"junction.held\": 8.0,
                        \"junction.gained\": 2.0,
                    },
                    \"policy_summaries\": [
                        {
                            \"avg_agent_metrics\": {
                                \"heart.gained\": 3.0,
                                \"heart.lost\": 1.0,
                            },
                            \"action_timeouts\": 0.0,
                            \"per_episode_per_policy_avg_rewards\": {
                                \"episode_0\": 11.0,
                                \"episode_1\": 13.0,
                            },
                        }
                    ],
                }
            }
        ]
    }
    print(json.dumps(payload))
    sys.exit(0)

if cmd == \"upload\":
    state[\"upload_count\"] = state.get(\"upload_count\", 0) + 1
    state_path.write_text(json.dumps(state))
    if \"--dry-run\" in args:
        print(\"dry-run validation passed\")
    else:
        print(\"Upload complete\")
    sys.exit(0)

if cmd == \"submit\":
    state[\"submit_count\"] = state.get(\"submit_count\", 0) + 1
    state_path.write_text(json.dumps(state))
    print(\"Submitted\")
    sys.exit(0)

if cmd == \"leaderboard\":
    state[\"leaderboard_count\"] = state.get(\"leaderboard_count\", 0) + 1
    state_path.write_text(json.dumps(state))
    payload = [
        {
            \"rank\": 1,
            \"policy\": {\"name\": \"test-policy\", \"version\": 3},
            \"score\": 99.5,
            \"matches\": 12,
        }
    ]
    print(json.dumps(payload))
    sys.exit(0)

print(f\"unknown command: {cmd}\", file=sys.stderr)
sys.exit(1)
"""
    path.write_text(script)
    path.chmod(0o755)


def test_startup_workflow_success(tmp_path: Path, monkeypatch) -> None:
    fake_cogames = tmp_path / "fake_cogames.py"
    _write_fake_cogames(fake_cogames)

    state_path = tmp_path / "state.json"
    monkeypatch.setenv("FAKE_COGAMES_STATE", str(state_path))

    bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=2,
            steps=100,
            output_root=tmp_path / "artifacts",
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
        )
    )

    assert bundle.status == "success"
    assert bundle.leaderboard_rank == 1
    assert bundle.leaderboard_score == 99.5
    assert bundle.scrimmage_metrics.reward == 12.0
    assert bundle.reaper_slo.detect_slo_met is True
    assert bundle.reaper_slo.recovery_slo_met is True
    assert bundle.gates is not None
    assert bundle.gates.overall_status == "pass"
    assert bundle.escalation_plan is not None
    assert bundle.escalation_plan.should_escalate is False
    assert (Path(bundle.run_dir) / "audit_bundle.json").exists()
    assert (Path(bundle.run_dir) / "docs_digest.json").exists()
    assert (Path(bundle.run_dir) / "daily_report.md").exists()
    assert any(step.step_name == "docs_readthrough" and step.status == "success" for step in bundle.steps)
    history_path = Path(bundle.run_dir) / "history_comparison.json"
    assert history_path.exists()
    history_payload = json.loads(history_path.read_text())
    assert history_payload["current_run_id"] == bundle.run_id
    gates_path = Path(bundle.run_dir) / "gates_evaluation.json"
    assert gates_path.exists()
    gates_payload = json.loads(gates_path.read_text())
    assert gates_payload["overall_status"] == "pass"
    escalation_path = Path(bundle.run_dir) / "escalation_plan.json"
    assert escalation_path.exists()
    escalation_payload = json.loads(escalation_path.read_text())
    assert escalation_payload["should_escalate"] is False

    state = json.loads(state_path.read_text())
    assert state["login_count"] == 1
    assert state["upload_count"] == 2
    assert state["submit_count"] == 1
    assert state["leaderboard_count"] == 1


def test_startup_recovers_auth_failure(tmp_path: Path, monkeypatch) -> None:
    fake_cogames = tmp_path / "fake_cogames.py"
    _write_fake_cogames(fake_cogames)

    state_path = tmp_path / "state.json"
    monkeypatch.setenv("FAKE_COGAMES_STATE", str(state_path))
    monkeypatch.setenv("FAKE_AUTH_FAIL_ONCE", "1")

    bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=tmp_path / "artifacts",
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
            max_recoveries=2,
            allow_interactive_login=True,
        )
    )

    assert bundle.status == "success"
    assert any(incident.incident_type == "auth_expired" for incident in bundle.incidents)
    assert bundle.reaper_slo.recovery_attempts >= 1
    assert any(item.category == "setup/auth" for item in bundle.diagnosis.friction_items)

    state = json.loads(state_path.read_text())
    assert state["scrimmage_count"] == 2
    assert state["login_count"] >= 2
    assert state.get("forced_login_count", 0) >= 1


def test_startup_fails_when_run_fails(tmp_path: Path, monkeypatch) -> None:
    fake_cogames = tmp_path / "fake_cogames.py"
    _write_fake_cogames(fake_cogames)

    state_path = tmp_path / "state.json"
    monkeypatch.setenv("FAKE_COGAMES_STATE", str(state_path))
    monkeypatch.setenv("FAKE_AUTH_FAIL_ONCE", "1")

    bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=tmp_path / "artifacts",
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
            max_recoveries=0,
        )
    )

    assert bundle.status == "failed"
    assert bundle.gates is not None
    assert bundle.gates.overall_status == "fail"
    full_loop = next(check for check in bundle.gates.checks if check.gate_id == "full_loop_success")
    assert full_loop.status == "fail"
    gates_path = Path(bundle.run_dir) / "gates_evaluation.json"
    assert gates_path.exists()


def test_startup_neophyte_profile_applies_stricter_gate_budgets(tmp_path: Path, monkeypatch) -> None:
    fake_cogames = tmp_path / "fake_cogames.py"
    _write_fake_cogames(fake_cogames)

    state_path = tmp_path / "state.json"
    monkeypatch.setenv("FAKE_COGAMES_STATE", str(state_path))
    monkeypatch.setenv("FAKE_AUTH_FAIL_ONCE", "1")

    bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=tmp_path / "artifacts",
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
            max_recoveries=2,
            researcher_profile="neophyte",
            allow_interactive_login=True,
        )
    )

    assert bundle.status == "success"
    assert bundle.gates is not None
    assert bundle.gates.overall_status == "fail"
    failed_budget = next(check for check in bundle.gates.checks if check.gate_id == "failed_invocations_budget")
    assert failed_budget.status == "fail"
    assert bundle.escalation_plan is not None
    assert bundle.escalation_plan.should_escalate is False


def test_startup_escalates_after_consecutive_failed_gate_runs(tmp_path: Path, monkeypatch) -> None:
    fake_cogames = tmp_path / "fake_cogames.py"
    _write_fake_cogames(fake_cogames)

    output_root = tmp_path / "artifacts"
    monkeypatch.setenv("FAKE_AUTH_FAIL_ONCE", "1")

    monkeypatch.setenv("FAKE_COGAMES_STATE", str(tmp_path / "state_first.json"))
    first_bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=output_root,
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
            max_recoveries=2,
            researcher_profile="neophyte",
            allow_interactive_login=True,
        )
    )
    assert first_bundle.gates is not None
    assert first_bundle.gates.overall_status == "fail"

    monkeypatch.setenv("FAKE_COGAMES_STATE", str(tmp_path / "state_second.json"))
    second_bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=output_root,
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
            max_recoveries=2,
            researcher_profile="neophyte",
            allow_interactive_login=True,
        )
    )

    assert second_bundle.gates is not None
    assert second_bundle.gates.overall_status == "fail"
    assert second_bundle.escalation_plan is not None
    assert second_bundle.escalation_plan.consecutive_failed_gate_runs == 2
    assert second_bundle.escalation_plan.escalation_threshold == 2
    assert second_bundle.escalation_plan.should_escalate is True


def test_startup_tracks_experiment_family_breadth_across_runs(tmp_path: Path, monkeypatch) -> None:
    fake_cogames = tmp_path / "fake_cogames.py"
    _write_fake_cogames(fake_cogames)

    output_root = tmp_path / "artifacts"

    monkeypatch.setenv("FAKE_COGAMES_STATE", str(tmp_path / "state_a.json"))
    first_bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="family-a-v1",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=output_root,
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
        )
    )

    monkeypatch.setenv("FAKE_COGAMES_STATE", str(tmp_path / "state_b.json"))
    second_bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="family-b-v1",
            season="beta-cogsguard",
            mission="cogsguard_arena.basic",
            episodes=1,
            steps=50,
            output_root=output_root,
            cogames_bin=str(fake_cogames),
            detect_idle_seconds=10,
            max_step_seconds=30,
        )
    )

    assert first_bundle.submit_coverage_index.experiment_family_breadth == 1
    assert second_bundle.submit_coverage_index.experiment_family_breadth >= 2


def test_startup_noninteractive_mode_fails_without_saved_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(startup_module, "_has_saved_auth_token", lambda *_: False)

    bundle = run_startup(
        StartupConfig(
            policy="metta://policy/role_py",
            policy_name="test-policy",
            output_root=tmp_path / "artifacts",
            cogames_bin="cogames",
            detect_idle_seconds=10,
            max_step_seconds=30,
            allow_interactive_login=False,
        )
    )

    assert bundle.status == "failed"
    login_step = next(step for step in bundle.steps if step.step_name == "login_auth_check")
    assert login_step.status == "failed"
    assert "No saved CoGames login token found for non-interactive mode" in login_step.stderr_tail
