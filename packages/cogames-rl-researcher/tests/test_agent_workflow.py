from __future__ import annotations

import subprocess
from pathlib import Path

from cogames_rl_researcher.agent_workflow import (
    _deterministic_fallback_script,
    agent_command,
    prompt_path_for_profile,
    report_path_for_profile,
    run_agent_workflow,
    run_agent_workflow_until_report,
)


def test_prompt_path_for_profile_resolves_expected_file(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "packages" / "cogames-rl-researcher" / "prompts"
    prompts_dir.mkdir(parents=True)
    expected = prompts_dir / "run-neophyte-workflow.md"
    expected.write_text("prompt", encoding="utf-8")
    (prompts_dir / "run-experienced-workflow.md").write_text("prompt2", encoding="utf-8")

    resolved = prompt_path_for_profile("neophyte", repo_root=tmp_path)
    assert resolved == expected


def test_agent_command_for_codex_and_claude() -> None:
    codex_cmd = agent_command("codex")
    claude_cmd = agent_command("claude")
    assert codex_cmd[0] == "codex"
    assert claude_cmd[0] == "claude"


def test_run_agent_workflow_invokes_subprocess_with_prompt(monkeypatch, tmp_path: Path) -> None:
    prompts_dir = tmp_path / "packages" / "cogames-rl-researcher" / "prompts"
    prompts_dir.mkdir(parents=True)
    prompt_text = "run workflow"
    (prompts_dir / "run-neophyte-workflow.md").write_text(prompt_text, encoding="utf-8")
    (prompts_dir / "run-experienced-workflow.md").write_text("unused", encoding="utf-8")

    seen: dict[str, object] = {}

    def _fake_run(command, *, input=None, cwd, capture_output, text, check):
        seen["command"] = command
        seen["input"] = input
        seen["cwd"] = cwd
        seen["capture_output"] = capture_output
        seen["text"] = text
        seen["check"] = check
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr("cogames_rl_researcher.agent_workflow.subprocess.run", _fake_run)

    result = run_agent_workflow(profile="neophyte", agent="codex", repo_root=tmp_path)
    assert result.returncode == 0
    assert seen["command"] == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"]
    assert seen["input"] == prompt_text
    assert seen["cwd"] == tmp_path
    assert seen["capture_output"] is False
    assert seen["text"] is True
    assert seen["check"] is False


def test_report_path_for_profile_resolves_expected_artifact(tmp_path: Path) -> None:
    report_path = report_path_for_profile("neophyte", repo_root=tmp_path)
    assert report_path == tmp_path / "artifacts" / "ai_researcher" / "neophyte_workflow_report.md"


def test_run_agent_workflow_until_report_retries_with_fresh_agent_runs(monkeypatch, tmp_path: Path) -> None:
    prompts_dir = tmp_path / "packages" / "cogames-rl-researcher" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "run-neophyte-workflow.md").write_text("run workflow", encoding="utf-8")
    (prompts_dir / "run-experienced-workflow.md").write_text("unused", encoding="utf-8")

    report_path = tmp_path / "artifacts" / "ai_researcher" / "neophyte_workflow_report.md"
    seen_commands: list[list[str]] = []

    def _fake_run(command, *, input=None, cwd, capture_output, text, check):
        seen_commands.append(command)
        if len(seen_commands) == 2:
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text("done", encoding="utf-8")
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr("cogames_rl_researcher.agent_workflow.subprocess.run", _fake_run)
    exit_code = run_agent_workflow_until_report(profile="neophyte", agent="codex", repo_root=tmp_path, max_attempts=2)
    assert exit_code == 0
    assert seen_commands[0] == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"]
    assert seen_commands[1] == ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"]


def test_run_agent_workflow_until_report_fails_when_report_missing(monkeypatch, tmp_path: Path) -> None:
    prompts_dir = tmp_path / "packages" / "cogames-rl-researcher" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "run-neophyte-workflow.md").write_text("run workflow", encoding="utf-8")
    (prompts_dir / "run-experienced-workflow.md").write_text("unused", encoding="utf-8")

    def _fake_run(command, *, input=None, cwd, capture_output, text, check):
        return subprocess.CompletedProcess(args=command, returncode=0)

    monkeypatch.setattr("cogames_rl_researcher.agent_workflow.subprocess.run", _fake_run)
    exit_code = run_agent_workflow_until_report(profile="neophyte", agent="codex", repo_root=tmp_path, max_attempts=2)
    assert exit_code == 1


def test_deterministic_fallback_script_preserves_startup_exit_on_report_failure() -> None:
    script = _deterministic_fallback_script("neophyte", Path("artifacts/ai_researcher/neophyte_workflow_report.md"))
    startup_exit_idx = script.index('STARTUP_EXIT=${PIPESTATUS[0]}')
    python_idx = script.index("python - <<'PY'")
    report_exit_idx = script.index("REPORT_EXIT=${?}")
    final_exit_idx = script.rindex('exit "$STARTUP_EXIT"')

    assert script.count("set +e") >= 2
    assert startup_exit_idx < python_idx < report_exit_idx < final_exit_idx
    assert "preserving startup exit $STARTUP_EXIT" in script
