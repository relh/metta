from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from devops.runners.metta_constants import OBSERVATORY_AUTH_SERVER_URL, PROD_STATS_SERVER_URI
from devops.stable.cogames_login import CogamesAuthenticator
from devops.stable.function_checks._helpers.isolated_venv import (
    isolated_venv,
    run_command_in_venv,
    run_commands_in_isolated_venv,
)
from devops.stable.stable_check_context import StableCheckContext
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_function_check_registry import stable_function_check

SUBMISSION_SEASON = "test-season"
GOOD_SUBMISSION_REF_PATH_TEMPLATE = "devops/stable/state/{job_name}/cogames_canary_good_submission_ref.json"
BAD_SUBMISSION_REF_PATH_TEMPLATE = "devops/stable/state/{job_name}/cogames_canary_bad_submission_ref.json"
SUBMISSION_POLICY_NAME_PREFIX = "stable.canary.policy"
SUBMISSION_POLL_TIMEOUT_S = 1200
SUBMISSION_POLL_INTERVAL_S = 20


def _submission_ref_path_for_job(job_name: str, template: str) -> Path:
    return Path(template.format(job_name=job_name))


def _submission_policy_name(kind: str) -> str:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{SUBMISSION_POLICY_NAME_PREFIX}.{kind}.{suffix}"


def _ensure_cogames_auth_token(login_server: str = OBSERVATORY_AUTH_SERVER_URL) -> None:
    authenticator = CogamesAuthenticator()
    token = os.environ.get("STABLE_RELEASE_SERVICE_TOKEN")
    if token:
        authenticator.config_reader_writer.save_token(token, login_server)
        return

    if authenticator.has_saved_token(login_server):
        return

    raise AssertionError(
        "Missing STABLE_RELEASE_SERVICE_TOKEN and no saved cogames login token. "
        "Set STABLE_RELEASE_SERVICE_TOKEN in the environment for submission checks."
    )


def _run_cogames_cmd(bin_dir: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return run_command_in_venv(
        bin_dir=bin_dir,
        command=["cogames", *args],
        check=False,
        capture_output=True,
    )


def _submission_counts(entries: object) -> tuple[int, int, int]:
    if not isinstance(entries, list):
        raise AssertionError("Expected `cogames submissions --json` to return a list")

    completed = 0
    failed = 0
    pending = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pools = entry.get("pools", [])
        if not isinstance(pools, list):
            continue
        for pool in pools:
            if not isinstance(pool, dict):
                continue
            completed += int(pool.get("completed", 0))
            failed += int(pool.get("failed", 0))
            pending += int(pool.get("pending", 0))
    return completed, failed, pending


def _write_submission_ref(
    *,
    ref_path: Path,
    policy_name: str,
    season: str = SUBMISSION_SEASON,
    server_url: str = PROD_STATS_SERVER_URI,
    login_server: str = OBSERVATORY_AUTH_SERVER_URL,
) -> None:
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(
        json.dumps(
            {
                "policy_name": policy_name,
                "season": season,
                "server_url": server_url,
                "login_server": login_server,
            },
            indent=2,
        )
    )


def _upload_policy(
    *,
    policy_name: str,
    policy_spec: str,
    skip_validation: bool,
    policy_kwargs: list[str] | None = None,
) -> None:
    with isolated_venv(packages=["cogames"]) as bin_dir:
        args = [
            "upload",
            "--include-hidden",
            "--policy",
            policy_spec,
            "--name",
            policy_name,
            "--season",
            SUBMISSION_SEASON,
            "--server",
            PROD_STATS_SERVER_URI,
            "--login-server",
            OBSERVATORY_AUTH_SERVER_URL,
        ]
        if skip_validation:
            args.insert(1, "--skip-validation")
        if policy_kwargs:
            args.extend(policy_kwargs)
        result = _run_cogames_cmd(bin_dir, args)
        if result.returncode != 0:
            raise AssertionError(
                f"cogames upload failed for `{policy_name}`:\n"
                f"stdout:\n{result.stdout.strip()}\n\nstderr:\n{result.stderr.strip()}"
            )


def _wait_for_submission_status(*, ref_payload: dict[str, str], expected_status: str) -> None:
    policy_name = str(ref_payload["policy_name"])
    season = str(ref_payload["season"])
    server_url = str(ref_payload["server_url"])
    login_server = str(ref_payload["login_server"])

    deadline = time.monotonic() + SUBMISSION_POLL_TIMEOUT_S
    last_status = "no submissions found yet"

    with isolated_venv(packages=["cogames"]) as bin_dir:
        while time.monotonic() < deadline:
            result = _run_cogames_cmd(
                bin_dir,
                [
                    "submissions",
                    "--season",
                    season,
                    "--policy",
                    policy_name,
                    "--server",
                    server_url,
                    "--login-server",
                    login_server,
                    "--include-hidden",
                    "--json",
                ],
            )
            if result.returncode != 0:
                last_status = f"submissions command failed: {result.stderr.strip() or result.stdout.strip()}"
                time.sleep(SUBMISSION_POLL_INTERVAL_S)
                continue

            try:
                entries = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                last_status = f"failed to parse submissions JSON: {exc}"
                time.sleep(SUBMISSION_POLL_INTERVAL_S)
                continue

            completed, failed, pending = _submission_counts(entries)
            if expected_status == "completed":
                # `cogames submissions --json` reports aggregate match counters, not a
                # terminal submission state. A healthy submission can have completed
                # matches while others are still pending/failed.
                if completed > 0:
                    return
                if failed > 0 and pending == 0:
                    raise AssertionError(
                        f"Submission `{policy_name}` reached terminal non-success state "
                        f"(completed={completed}, failed={failed}, pending={pending})."
                    )
            elif expected_status == "failed":
                if failed > 0 and completed == 0 and pending == 0:
                    return
                if completed > 0:
                    raise AssertionError(
                        f"Submission `{policy_name}` unexpectedly completed "
                        f"(completed={completed}, failed={failed}, pending={pending})."
                    )
            else:
                raise ValueError(f"Unsupported expected_status: {expected_status}")

            last_status = (
                f"waiting for `{expected_status}`: completed={completed}, failed={failed}, pending={pending}, "
                f"entries={len(entries) if isinstance(entries, list) else 'n/a'}"
            )
            time.sleep(SUBMISSION_POLL_INTERVAL_S)

    raise AssertionError(
        f"Timed out waiting for submission `{policy_name}` to reach `{expected_status}` "
        f"in season `{season}`: {last_status}"
    )


@stable_function_check(
    timeout_s=900,
    check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
)
def install_cogames(_ctx: StableCheckContext) -> None:
    run_commands_in_isolated_venv(
        packages=["cogames"],
        commands=[["cogames", "version"]],
    )


@stable_function_check(
    timeout_s=900,
    check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
    depends_on=install_cogames,
    output_references={"good_submission_ref_path": GOOD_SUBMISSION_REF_PATH_TEMPLATE},
)
def upload_canary_good_policy(ctx: StableCheckContext) -> None:
    _ensure_cogames_auth_token()
    policy_name = _submission_policy_name("good")
    _upload_policy(
        policy_name=policy_name,
        policy_spec="class=random",
        skip_validation=True,
    )
    _write_submission_ref(
        ref_path=_submission_ref_path_for_job(ctx.job_name, GOOD_SUBMISSION_REF_PATH_TEMPLATE),
        policy_name=policy_name,
    )


@stable_function_check(
    timeout_s=900,
    check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
    depends_on=install_cogames,
    output_references={"bad_submission_ref_path": BAD_SUBMISSION_REF_PATH_TEMPLATE},
)
def upload_canary_bad_policy(ctx: StableCheckContext) -> None:
    _ensure_cogames_auth_token()
    policy_name = _submission_policy_name("bad")
    _upload_policy(
        policy_name=policy_name,
        policy_spec="class=noop",
        skip_validation=True,
        policy_kwargs=["-k", "invalid_param=foo"],
    )
    _write_submission_ref(
        ref_path=_submission_ref_path_for_job(ctx.job_name, BAD_SUBMISSION_REF_PATH_TEMPLATE),
        policy_name=policy_name,
    )


@stable_function_check(
    timeout_s=1500,
    check_group=StableCheckGroup.LIVE_TESTS_HEAVY,
    depends_on=upload_canary_bad_policy,
    input_references={"submission_ref_path": "bad_submission_ref_path"},
)
def check_canary_bad_policy_submission_results(ctx: StableCheckContext) -> None:
    _ensure_cogames_auth_token()
    submission_ref_path = Path(ctx.inputs["submission_ref_path"])
    ref_payload = json.loads(submission_ref_path.read_text())
    _wait_for_submission_status(ref_payload=ref_payload, expected_status="failed")


@stable_function_check(
    timeout_s=1500,
    check_group=StableCheckGroup.LIVE_TESTS_HEAVY,
    depends_on=upload_canary_good_policy,
    input_references={"submission_ref_path": "good_submission_ref_path"},
)
def check_canary_good_policy_submission_results(ctx: StableCheckContext) -> None:
    _ensure_cogames_auth_token()
    submission_ref_path = Path(ctx.inputs["submission_ref_path"])
    ref_payload = json.loads(submission_ref_path.read_text())
    _wait_for_submission_status(ref_payload=ref_payload, expected_status="completed")
