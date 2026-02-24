from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from devops.stable.function_checks import cogames_submission as submission
from devops.stable.stable_check_context import StableCheckContext


def test_policy_name_prefix_is_canary_tagged() -> None:
    assert submission.SUBMISSION_POLICY_NAME_PREFIX == "stable.canary.policy"


def test_install_cogames_uses_isolated_venv_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], list[list[str]]]] = []

    def _fake_run_commands_in_isolated_venv(*, packages: list[str], commands: list[list[str]], **_: object):
        calls.append((packages, commands))
        return []

    monkeypatch.setattr(submission, "run_commands_in_isolated_venv", _fake_run_commands_in_isolated_venv)

    submission.install_cogames(StableCheckContext(job_name="runner.stable.example", inputs={}))

    assert calls == [(["cogames"], [["cogames", "version"]])]


def test_ensure_auth_token_prefers_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    saved_calls: list[tuple[str, str]] = []

    class _FakeAuthenticator:
        def __init__(self) -> None:
            def _save_token(token: str, server: str) -> None:
                saved_calls.append((token, server))

            self.config_reader_writer = SimpleNamespace(save_token=_save_token)

        def has_saved_token(self, login_server: str) -> bool:
            _ = login_server
            return True

    monkeypatch.setattr(submission, "CogamesAuthenticator", _FakeAuthenticator)
    monkeypatch.setenv("STABLE_RELEASE_SERVICE_TOKEN", "service-token")

    submission._ensure_cogames_auth_token("https://softmax.com/api")

    assert saved_calls == [("service-token", "https://softmax.com/api")]


def test_ensure_auth_token_falls_back_to_saved_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAuthenticator:
        def __init__(self) -> None:
            self.config_reader_writer = SimpleNamespace(save_token=lambda *_: None)

        def has_saved_token(self, login_server: str) -> bool:
            assert login_server == "https://softmax.com/api"
            return True

    monkeypatch.setattr(submission, "CogamesAuthenticator", _FakeAuthenticator)
    monkeypatch.delenv("STABLE_RELEASE_SERVICE_TOKEN", raising=False)

    submission._ensure_cogames_auth_token("https://softmax.com/api")


def test_ensure_auth_token_raises_without_env_or_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeAuthenticator:
        def __init__(self) -> None:
            self.config_reader_writer = SimpleNamespace(save_token=lambda *_: None)

        def has_saved_token(self, login_server: str) -> bool:
            _ = login_server
            return False

    monkeypatch.setattr(submission, "CogamesAuthenticator", _FakeAuthenticator)
    monkeypatch.delenv("STABLE_RELEASE_SERVICE_TOKEN", raising=False)

    with pytest.raises(AssertionError, match="Missing STABLE_RELEASE_SERVICE_TOKEN"):
        submission._ensure_cogames_auth_token("https://softmax.com/api")


def test_upload_policy_builds_expected_upload_command(monkeypatch: pytest.MonkeyPatch) -> None:
    run_calls: list[list[str]] = []

    @contextmanager
    def _fake_isolated_venv(*, packages: list[str], **_: object):
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

    submission._upload_policy(
        policy_name="stable.canary.policy.bad.20260223T000000Z",
        policy_spec="class=noop",
        skip_validation=True,
        policy_kwargs=["-k", "invalid_param=foo"],
    )

    assert len(run_calls) == 1
    cmd = run_calls[0]
    assert cmd[:4] == ["cogames", "upload", "--skip-validation", "--include-hidden"]
    assert "--policy" in cmd
    assert "class=noop" in cmd
    assert "-k" in cmd
    assert "invalid_param=foo" in cmd


def test_upload_canary_good_policy_writes_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    upload_calls: list[dict[str, object]] = []
    ref_calls: list[Path] = []

    monkeypatch.setattr(submission, "_ensure_cogames_auth_token", lambda: None)
    monkeypatch.setattr(submission, "_submission_policy_name", lambda _kind: "stable.canary.policy.good.fixed")
    monkeypatch.setattr(
        submission,
        "_upload_policy",
        lambda **kwargs: upload_calls.append(kwargs),
    )

    def _fake_ref_path_for_job(job_name: str, template: str) -> Path:
        _ = (job_name, template)
        return tmp_path / "good_ref.json"

    monkeypatch.setattr(submission, "_submission_ref_path_for_job", _fake_ref_path_for_job)

    def _fake_write_submission_ref(*, ref_path: Path, policy_name: str, **_: object):
        ref_calls.append(ref_path)
        ref_path.write_text(json.dumps({"policy_name": policy_name}))

    monkeypatch.setattr(submission, "_write_submission_ref", _fake_write_submission_ref)

    submission.upload_canary_good_policy(StableCheckContext(job_name="runner.stable.example", inputs={}))

    assert upload_calls == [
        {
            "policy_name": "stable.canary.policy.good.fixed",
            "policy_spec": "class=random",
            "skip_validation": True,
        }
    ]
    assert ref_calls == [tmp_path / "good_ref.json"]


def test_upload_canary_bad_policy_writes_ref(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    upload_calls: list[dict[str, object]] = []
    ref_calls: list[Path] = []

    monkeypatch.setattr(submission, "_ensure_cogames_auth_token", lambda: None)
    monkeypatch.setattr(submission, "_submission_policy_name", lambda _kind: "stable.canary.policy.bad.fixed")
    monkeypatch.setattr(
        submission,
        "_upload_policy",
        lambda **kwargs: upload_calls.append(kwargs),
    )

    def _fake_ref_path_for_job(job_name: str, template: str) -> Path:
        _ = (job_name, template)
        return tmp_path / "bad_ref.json"

    monkeypatch.setattr(submission, "_submission_ref_path_for_job", _fake_ref_path_for_job)

    def _fake_write_submission_ref(*, ref_path: Path, policy_name: str, **_: object):
        ref_calls.append(ref_path)
        ref_path.write_text(json.dumps({"policy_name": policy_name}))

    monkeypatch.setattr(submission, "_write_submission_ref", _fake_write_submission_ref)

    submission.upload_canary_bad_policy(StableCheckContext(job_name="runner.stable.example", inputs={}))

    assert upload_calls == [
        {
            "policy_name": "stable.canary.policy.bad.fixed",
            "policy_spec": "class=noop",
            "skip_validation": True,
            "policy_kwargs": ["-k", "invalid_param=foo"],
        }
    ]
    assert ref_calls == [tmp_path / "bad_ref.json"]


def test_wait_for_submission_status_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(submission.time, "sleep", lambda _seconds: None)

    @contextmanager
    def _fake_isolated_venv(*, packages: list[str], **_: object):
        assert packages == ["cogames"]
        yield Path("/tmp/fake-venv/bin")

    responses = iter(
        [
            [{"pools": [{"completed": 0, "failed": 0, "pending": 1}]}],
            [{"pools": [{"completed": 1, "failed": 2, "pending": 3}]}],
        ]
    )

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = (bin_dir, check, capture_output, text)
        assert command[:2] == ["cogames", "submissions"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(next(responses)), stderr="")

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    submission._wait_for_submission_status(
        ref_payload={
            "policy_name": "stable.canary.policy.good.fixed",
            "season": submission.SUBMISSION_SEASON,
            "server_url": submission.PROD_STATS_SERVER_URI,
            "login_server": submission.OBSERVATORY_AUTH_SERVER_URL,
        },
        expected_status="completed",
    )


def test_wait_for_submission_status_completed_allows_failed_before_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(submission.time, "sleep", lambda _seconds: None)

    @contextmanager
    def _fake_isolated_venv(*, packages: list[str], **_: object):
        assert packages == ["cogames"]
        yield Path("/tmp/fake-venv/bin")

    responses = iter(
        [
            [{"pools": [{"completed": 0, "failed": 1, "pending": 2}]}],
            [{"pools": [{"completed": 1, "failed": 1, "pending": 1}]}],
        ]
    )

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = (bin_dir, check, capture_output, text)
        assert command[:2] == ["cogames", "submissions"]
        return SimpleNamespace(returncode=0, stdout=json.dumps(next(responses)), stderr="")

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    submission._wait_for_submission_status(
        ref_payload={
            "policy_name": "stable.canary.policy.good.fixed",
            "season": submission.SUBMISSION_SEASON,
            "server_url": submission.PROD_STATS_SERVER_URI,
            "login_server": submission.OBSERVATORY_AUTH_SERVER_URL,
        },
        expected_status="completed",
    )


def test_wait_for_submission_status_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(submission.time, "sleep", lambda _seconds: None)

    @contextmanager
    def _fake_isolated_venv(*, packages: list[str], **_: object):
        assert packages == ["cogames"]
        yield Path("/tmp/fake-venv/bin")

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = (bin_dir, command, check, capture_output, text)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"pools": [{"completed": 0, "failed": 1, "pending": 0}]}]),
            stderr="",
        )

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    submission._wait_for_submission_status(
        ref_payload={
            "policy_name": "stable.canary.policy.bad.fixed",
            "season": submission.SUBMISSION_SEASON,
            "server_url": submission.PROD_STATS_SERVER_URI,
            "login_server": submission.OBSERVATORY_AUTH_SERVER_URL,
        },
        expected_status="failed",
    )


def test_wait_for_submission_status_raises_when_bad_policy_completes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(submission.time, "sleep", lambda _seconds: None)

    @contextmanager
    def _fake_isolated_venv(*, packages: list[str], **_: object):
        _ = packages
        yield Path("/tmp/fake-venv/bin")

    def _fake_run_in_venv(*, bin_dir: Path, command: list[str], check: bool, capture_output: bool, text: bool = True):
        _ = (bin_dir, command, check, capture_output, text)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps([{"pools": [{"completed": 1, "failed": 0, "pending": 0}]}]),
            stderr="",
        )

    monkeypatch.setattr(submission, "isolated_venv", _fake_isolated_venv)
    monkeypatch.setattr(submission, "run_command_in_venv", _fake_run_in_venv)

    with pytest.raises(AssertionError, match="unexpectedly completed"):
        submission._wait_for_submission_status(
            ref_payload={
                "policy_name": "stable.canary.policy.bad.fixed",
                "season": submission.SUBMISSION_SEASON,
                "server_url": submission.PROD_STATS_SERVER_URI,
                "login_server": submission.OBSERVATORY_AUTH_SERVER_URL,
            },
            expected_status="failed",
        )
