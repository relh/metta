from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from devops.stable.function_checks import cogames_submission as submission
from devops.stable.stable_check_context import StableCheckContext


def test_policy_name_is_fixed() -> None:
    assert submission.SUBMISSION_POLICY_NAME == "stable-release-check"


def test_install_cogames_uses_isolated_venv_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], list[list[str]], str]] = []

    def _fake_run_commands_in_isolated_venv(
        *,
        packages: list[str],
        commands: list[list[str]],
        python_executable: str = "python3",
        prefix: str = "stable_check_",
    ) -> list[SimpleNamespace]:
        _ = python_executable
        calls.append((packages, commands, prefix))
        return []

    monkeypatch.setattr(submission, "run_commands_in_isolated_venv", _fake_run_commands_in_isolated_venv)

    submission.install_cogames(StableCheckContext(job_name="runner.stable.example", inputs={}))

    assert calls == [(["cogames"], [["cogames", "version"]], "stable_check_")]


def test_upload_and_submit_policy_runs_upload_and_writes_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run_calls: list[list[str]] = []
    monkeypatch.setattr(submission, "_ensure_cogames_auth_token", lambda: None)
    monkeypatch.setattr(
        submission,
        "_submission_ref_path_for_job",
        lambda _job_name: tmp_path / "submission_ref.json",
    )

    @contextmanager
    def _fake_isolated_venv(
        *,
        packages: list[str],
        prefix: str = "stable_check_",
        python_executable: str = "python3",
    ):  # noqa: ANN001
        _ = (prefix, python_executable)
        assert packages == ["cogames"]
        yield Path("/tmp/fake-venv/bin")

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = bin_dir
        assert check is False
        assert capture_output is True
        assert text is True
        run_calls.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    submission.upload_and_submit_policy(StableCheckContext(job_name="runner.stable.example", inputs={}))

    assert len(run_calls) == 1
    assert run_calls[0][:2] == ["cogames", "upload"]
    assert "--skip-validation" not in run_calls[0]
    payload = json.loads((tmp_path / "submission_ref.json").read_text())
    assert payload["policy_name"] == submission.SUBMISSION_POLICY_NAME
    assert payload["season"] == submission.SUBMISSION_SEASON


def test_check_policy_results_polls_until_completed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ref_path = tmp_path / "submission_ref.json"
    ref_path.write_text(
        json.dumps(
            {
                "policy_name": "stable-release-check",
                "season": submission.SUBMISSION_SEASON,
                "server_url": submission.PROD_STATS_SERVER_URI,
                "login_server": submission.OBSERVATORY_AUTH_SERVER_URL,
            }
        )
    )

    monkeypatch.setattr(submission, "_ensure_cogames_auth_token", lambda: None)
    monkeypatch.setattr(submission.time, "sleep", lambda _seconds: None)

    @contextmanager
    def _fake_isolated_venv(
        *,
        packages: list[str],
        prefix: str = "stable_check_",
        python_executable: str = "python3",
    ):  # noqa: ANN001
        _ = (prefix, python_executable)
        assert packages == ["cogames"]
        yield Path("/tmp/fake-venv/bin")

    responses = iter(
        [
            [{"pools": [{"completed": 0, "failed": 0, "pending": 1}]}],
            [{"pools": [{"completed": 1, "failed": 0, "pending": 0}]}],
        ]
    )

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = (bin_dir, check, capture_output, text)
        assert command[:2] == ["cogames", "submissions"]
        assert "--include-hidden" in command
        assert "--json" in command
        payload = next(responses)
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    submission.check_submission_results(
        StableCheckContext(job_name="runner.stable.example", inputs={"submission_ref_path": str(ref_path)})
    )


def test_check_policy_results_fails_on_terminal_failed_submission(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ref_path = tmp_path / "submission_ref.json"
    ref_path.write_text(
        json.dumps(
            {
                "policy_name": "stable-release-check",
                "season": submission.SUBMISSION_SEASON,
                "server_url": submission.PROD_STATS_SERVER_URI,
                "login_server": submission.OBSERVATORY_AUTH_SERVER_URL,
            }
        )
    )

    monkeypatch.setattr(submission, "_ensure_cogames_auth_token", lambda: None)
    monkeypatch.setattr(submission.time, "sleep", lambda _seconds: None)

    @contextmanager
    def _fake_isolated_venv(
        *,
        packages: list[str],
        prefix: str = "stable_check_",
        python_executable: str = "python3",
    ):  # noqa: ANN001
        _ = (prefix, python_executable)
        assert packages == ["cogames"]
        yield Path("/tmp/fake-venv/bin")

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = (bin_dir, check, capture_output, text)
        assert command[:2] == ["cogames", "submissions"]
        assert "--include-hidden" in command
        assert "--json" in command
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"pools": [{"completed": 0, "failed": 1, "pending": 0}]}]),
            stderr="",
        )

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    with pytest.raises(AssertionError, match="failed before completion"):
        submission.check_submission_results(
            StableCheckContext(job_name="runner.stable.example", inputs={"submission_ref_path": str(ref_path)})
        )
