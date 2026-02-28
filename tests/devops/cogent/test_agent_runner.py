from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def _load_agent_runner_module():
    module_path = Path(__file__).resolve().parents[3] / "devops" / "cogent" / "agent-runner.py"
    # Replicate sys.path[0] that Python sets when running a script directly —
    # agent-runner.py uses bare imports for sibling modules (credentials, etc.)
    cogent_dir = str(module_path.parent)
    if cogent_dir not in sys.path:
        sys.path.insert(0, cogent_dir)
    spec = importlib.util.spec_from_file_location("cogent_agent_runner", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_main_returns_nonzero_when_push_fails(monkeypatch, tmp_path) -> None:
    runner = _load_agent_runner_module()

    metta_dir = tmp_path / "metta"
    cogents_dir = tmp_path / "cogents"
    worktree_base = tmp_path / "worktrees"
    log_dir = tmp_path / "logs"
    for path in (metta_dir, cogents_dir, worktree_base, log_dir):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(runner, "METTA_DIR", metta_dir)
    monkeypatch.setattr(runner, "COGENTS_DIR", cogents_dir)
    monkeypatch.setattr(runner, "WORKTREE_BASE", worktree_base)
    monkeypatch.setattr(runner, "LOG_DIR", log_dir)
    monkeypatch.setattr(runner, "prune_worktrees", lambda: None)
    monkeypatch.setattr(runner, "load_credentials", lambda: None)
    monkeypatch.setattr(runner, "generate_github_token", lambda: "token")
    monkeypatch.setattr(runner, "configure_git", lambda token: None)  # noqa: ARG005
    monkeypatch.setattr(runner, "resolve_branch", lambda repo_dir, branch: branch)  # noqa: ARG005
    monkeypatch.setattr(
        runner,
        "create_worktree",
        lambda repo_dir, branch, run_dir, name: (run_dir / name),  # noqa: ARG005
    )
    monkeypatch.setattr(runner, "remove_worktree", lambda repo_dir, wt_path: None)  # noqa: ARG005
    monkeypatch.setattr(runner, "read_content", lambda *args, **kwargs: ("prompt", "label"))  # noqa: ARG005
    monkeypatch.setattr(
        runner,
        "run_agent",
        lambda content, timeout_min, agent, cwd: subprocess.CompletedProcess(  # noqa: ARG005
            args=["agent"],
            returncode=0,
            stdout="ok",
            stderr="",
        ),
    )

    def fake_subprocess_run(cmd, **kwargs):  # noqa: ANN001
        if cmd[:2] == ["git", "log"]:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="a1b2c3\n", stderr="")
        if cmd[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="push rejected")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(sys, "argv", ["agent-runner.py", "--branch", "main", "--prompt-text", "hello"])

    with __import__("pytest").raises(SystemExit) as exc_info:
        runner.main()

    assert exc_info.value.code == 1
