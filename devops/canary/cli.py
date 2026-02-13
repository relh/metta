#!/usr/bin/env python3

import os
import sys
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from devops.canary.cogames_login import CogamesAuthenticator
from devops.runners.core import Runner
from devops.runners.executors.cogames import CogamesCliExecutor
from devops.runners.executors.local import LocalExecutor
from devops.runners.job import Job
from devops.runners.metta_constants import (
    DEV_STATS_SERVER_URI,
    LOCAL_MACHINE_TOKEN,
    OBSERVATORY_AUTH_SERVER_URL,
    PROD_STATS_SERVER_URI,
)
from devops.runners.reporters.discord import write_discord_summary
from devops.runners.reporters.shared import build_categorized_jobs


class Server(StrEnum):
    DEV = "dev"
    PROD = "prod"


SERVERS = {
    "dev": DEV_STATS_SERVER_URI,
    "prod": PROD_STATS_SERVER_URI,
}

AUTH_SERVERS = {"dev": DEV_STATS_SERVER_URI, "prod": OBSERVATORY_AUTH_SERVER_URL}

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def main(
    server: Annotated[Server, typer.Option(help="Target environment")] = Server.DEV,
):
    authenticator = CogamesAuthenticator()
    state_dir = Path(__file__).parent / "state"
    runner = Runner(state_dir)

    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    good_name = f"canary.good.{suffix}"
    bad_name = f"canary.bad.{suffix}"

    token: str | None = None

    if authenticator.has_saved_token(AUTH_SERVERS[server]):
        token = authenticator.config_reader_writer.load_token(AUTH_SERVERS[server])
    else:
        observatory_token = os.environ.get("OBSERVATORY_TOKEN") if server is Server.PROD else LOCAL_MACHINE_TOKEN
        if observatory_token is not None:
            authenticator.config_reader_writer.save_token(observatory_token, AUTH_SERVERS[server])
            token = observatory_token

    if not token:
        raise ValueError(
            "Observatory authentication token not set, "
            "cannot issue 'cogames login' non-interactively. "
            "Ensure that OBSERVATORY_TOKEN is set in environment."
        )

    login_server_args = ["--login-server", AUTH_SERVERS[server]]
    servers_args = ["--server", SERVERS[server], *login_server_args]

    cogames_exec = CogamesCliExecutor(token=token, login_server=AUTH_SERVERS[server], server_url=SERVERS[server])
    local_exec = LocalExecutor()

    # Ensure cogames authenticated
    login = Job(
        name="login",
        cmd=["cogames", "login", *login_server_args],
        executor=local_exec,
        timeout_s=20,
    )
    runner.add_job(login)

    # Upload good policy (random). Uses a mettagrid built-in so the episode runner's
    # isolated venv can load it without needing cogames installed. Skip local
    # validation because the canary tests server-side validation.
    upload_good = Job(
        name="upload_good",
        cmd=[
            "cogames",
            "upload",
            "--skip-validation",
            "--include-hidden",
            "--policy",
            "class=random",
            "--name",
            good_name,
            "--season",
            "test-season",
            *servers_args,
        ],
        executor=local_exec,
        dependencies=["login"],
        timeout_s=300,
    )
    runner.add_job(upload_good)

    # Upload bad policy: noop with an invalid kwarg that will cause a TypeError
    # in the episode runner, producing a failed submission.
    upload_bad = Job(
        name="upload_bad",
        cmd=[
            "cogames",
            "upload",
            "--skip-validation",
            "--include-hidden",
            "--policy",
            "class=noop",
            "-k",
            "invalid_param=foo",
            "--name",
            bad_name,
            "--season",
            "test-season",
            *servers_args,
        ],
        executor=local_exec,
        dependencies=["login"],
        timeout_s=300,
    )
    runner.add_job(upload_bad)

    # Check failed submissions list for existence of the bad policy
    # Will be polled until a JobStatus is returned before a deadline
    check_failed_submissions = Job(
        name="check_failed_submissions",
        cmd=[
            "cogames",
            "submissions",
            "--policy",
            bad_name,
            "--json",
            *servers_args,
        ],
        executor=cogames_exec,
        dependencies=["upload_bad"],
        metadata={"expected_subjob_status": "failed"},
        timeout_s=2400,
    )
    runner.add_job(check_failed_submissions)

    # Check successful submissions list for existence of good policy
    # Will be polled until a JobStatus is returned before a deadline
    check_successful_submissions = Job(
        name="check_successful_submissions",
        cmd=[
            "cogames",
            "submissions",
            "--policy",
            good_name,
            "--json",
            *servers_args,
        ],
        executor=cogames_exec,
        dependencies=["upload_good"],
        metadata={"expected_subjob_status": "completed"},
        timeout_s=2400,
    )
    runner.add_job(check_successful_submissions)

    # Run
    runner.run_all()

    # Report and exit
    categorized = build_categorized_jobs(runner)
    write_discord_summary(categorized, state_dir)
    sys.exit(0 if not categorized["failed"] else 1)


if __name__ == "__main__":
    app()
