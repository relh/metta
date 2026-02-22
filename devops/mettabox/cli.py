#!/usr/bin/env -S uv run
from __future__ import annotations

import os
import shlex
import subprocess
from typing import Annotated, Optional

import typer
from typer import rich_utils

DEFAULT_BOXES = ("metta0", "metta1", "metta2", "metta3", "metta4")
LOCAL_BOX = "local"
DEFAULT_CONTAINER = "metta"
WORKSPACE = "/workspace/metta"
TRAIN_DIR = "/workspace/metta/train_dir"
HOST_HELP = "Mettabox host (metta0..metta4) or local."
FORWARDED_AWS_ENV_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
)
NVML_TROUBLESHOOT = (
    "If tmux shows 'cannot initialize NVML', the NVIDIA driver is broken inside the container. "
    "Kill/restart the container on the host (docker ps; docker kill metta; docker start metta) and retry the run."
)

app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
)

rich_utils.STYLE_HELPTEXT = ""  # don't gray out help text - https://github.com/fastapi/typer/issues/437


def _host_cmd(host: str, remote_cmd: str, *, tty: bool = False) -> list[str]:
    if host == LOCAL_BOX:
        return ["bash", "-lc", remote_cmd]
    cmd = ["ssh"]
    if tty:
        cmd.append("-t")
    cmd.append(host)
    cmd.append(remote_cmd)
    return cmd


def _ssh(host: str, remote_cmd: str, *, tty: bool) -> int:
    return subprocess.run(_host_cmd(host, remote_cmd, tty=tty)).returncode


def _docker_exec(
    container: str,
    command: str,
    *,
    tty: bool,
    use_repo: bool,
    env_file: Optional[str] = None,
) -> str:
    if use_repo:
        command = f"cd {WORKSPACE} && {command}"
    flags = "-it" if tty else "-i"
    env_file_arg = f"--env-file {shlex.quote(env_file)} " if env_file else ""
    return f"docker exec {flags} {env_file_arg}{shlex.quote(container)} bash -lc {shlex.quote(command)}"


def _resolve_github_token() -> Optional[str]:
    for env_var in ("GH_TOKEN", "GITHUB_TOKEN"):
        token = os.environ.get(env_var)
        if token:
            return token.strip()
    try:
        result = subprocess.run(["gh", "auth", "token"], check=True, capture_output=True, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    token = result.stdout.strip()
    return token or None


def _resolve_aws_env() -> tuple[dict[str, str], Optional[str]]:
    resolved: dict[str, str] = {}
    for env_var in FORWARDED_AWS_ENV_VARS:
        value = os.environ.get(env_var)
        if value:
            resolved[env_var] = value.strip()
    export_cmd = ["aws", "configure", "export-credentials", "--format", "env-no-export"]
    profile = os.environ.get("AWS_PROFILE")
    if profile:
        export_cmd.extend(["--profile", profile])
    export_error: Optional[str] = None
    try:
        result = subprocess.run(export_cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        exported = {}
        export_error = "aws CLI not found while resolving forwarded credentials."
    except subprocess.CalledProcessError as exc:
        exported: dict[str, str] = {}
        stderr = (exc.stderr or exc.stdout or "").strip()
        if stderr:
            export_error = stderr.splitlines()[0]
        else:
            export_error = f"aws configure export-credentials exited with {exc.returncode}."
    else:
        exported = {}
        for line in result.stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in FORWARDED_AWS_ENV_VARS:
                exported[key] = value.strip().strip("'").strip('"')
    env_has_pair = "AWS_ACCESS_KEY_ID" in resolved and "AWS_SECRET_ACCESS_KEY" in resolved
    exported_has_pair = "AWS_ACCESS_KEY_ID" in exported and "AWS_SECRET_ACCESS_KEY" in exported

    if (
        env_has_pair
        and exported_has_pair
        and exported.get("AWS_SESSION_TOKEN")
        and not resolved.get("AWS_SESSION_TOKEN")
    ):
        chosen = exported.copy()
    elif env_has_pair:
        chosen = resolved.copy()
    elif exported_has_pair:
        chosen = exported.copy()
    else:
        chosen = {}

    if not chosen:
        problems: list[str] = []
        if profile:
            problems.append(f"AWS_PROFILE={profile!r}")
        if export_error:
            problems.append(export_error)
        if resolved and not env_has_pair:
            missing = [key for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY") if key not in resolved]
            problems.append(f"incomplete AWS env vars (missing {', '.join(missing)})")
        if not problems:
            problems.append("no AWS credential source produced AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY")
        return {}, "; ".join(problems)

    for region_key in ("AWS_REGION", "AWS_DEFAULT_REGION"):
        if region_key not in chosen:
            if region_key in resolved:
                chosen[region_key] = resolved[region_key]
            elif region_key in exported:
                chosen[region_key] = exported[region_key]
    return chosen, None


def _build_forwarded_env(*, forward_gh_token: bool, forward_aws_creds: bool) -> dict[str, str]:
    forwarded_env: dict[str, str] = {}
    if forward_gh_token:
        token = _resolve_github_token()
        if token:
            forwarded_env["GITHUB_TOKEN"] = token
            forwarded_env["GH_TOKEN"] = token
    if forward_aws_creds:
        aws_env, aws_issue = _resolve_aws_env()
        forwarded_env.update(aws_env)
        if not aws_env and aws_issue:
            typer.echo(
                "Warning: --forward-aws-creds is enabled, but no local AWS credentials were forwarded "
                f"({aws_issue}). The container may fall back to stale/expired credentials. "
                "Set a valid AWS_PROFILE (or AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY locally), "
                "or pass --no-forward-aws-creds.",
                err=True,
            )
    return forwarded_env


def _create_remote_env_file(host: str, forwarded_env: dict[str, str]) -> Optional[str]:
    if not forwarded_env:
        return None
    remote_cmd = (
        'tmp=$(mktemp /tmp/mettabox-env.XXXXXX) && cat > "$tmp" && chmod 600 "$tmp" && echo "__ENV_FILE__:$tmp"'
    )
    lines: list[str] = []
    for key, value in sorted(forwarded_env.items()):
        if "\n" in value:
            raise typer.BadParameter(f"Forwarded env var {key} contains a newline and cannot be forwarded safely.")
        lines.append(f"{key}={value}")
    payload = "\n".join(lines) + "\n"
    result = subprocess.run(_host_cmd(host, remote_cmd), check=False, input=payload, text=True, capture_output=True)
    if result.returncode != 0:
        if result.stdout:
            typer.echo(result.stdout, err=True)
        if result.stderr:
            typer.echo(result.stderr, err=True)
        raise typer.Exit(result.returncode)
    for line in result.stdout.splitlines():
        if line.startswith("__ENV_FILE__:"):
            return line.split(":", 1)[1]
    raise typer.BadParameter(f"Failed to create remote env file on {host}.")


def _docker_exec_with_cleanup(
    host: str,
    container: str,
    command: str,
    *,
    tty: bool,
    use_repo: bool,
    forwarded_env: dict[str, str],
) -> int:
    env_file = _create_remote_env_file(host, forwarded_env)
    docker_cmd = _docker_exec(container, command, tty=tty, use_repo=use_repo, env_file=env_file)
    if env_file is None:
        remote_cmd = docker_cmd
    else:
        remote_cmd = f"{docker_cmd}; rc=$?; rm -f {shlex.quote(env_file)}; exit $rc"
    return _ssh(host, remote_cmd, tty=tty)


def _resolve_log_path_cmd(run_id: str) -> str:
    candidates = " ".join(
        shlex.quote(path)
        for path in (
            f"{TRAIN_DIR}/{run_id}.log",
            f"{TRAIN_DIR}/{run_id}/logs/script.log",
            f"{TRAIN_DIR}/{run_id}/logs/monitor.log",
        )
    )
    run_label = shlex.quote(run_id)
    return (
        'LOG_PATH=""; '
        f"for candidate in {candidates}; do "
        'if [ -f "$candidate" ]; then LOG_PATH="$candidate"; break; fi; '
        "done; "
        'if [ -z "$LOG_PATH" ]; then '
        f'echo "No log found for run_id={run_label}" >&2; exit 1; '
        "fi"
    )


def _resolve_hosts(host: Optional[str], all_hosts: bool) -> list[str]:
    if all_hosts:
        return list(DEFAULT_BOXES)
    if host:
        return [host]
    raise typer.BadParameter("Host is required unless --all is set.")


def _tmux_run_cmd(run_cmd: str, session_name: str, *, attach: bool) -> str:
    session_label = shlex.quote(session_name)
    attach_cmd_session = f"tmux attach -t {session_label}"
    create_session_cmd = f"tmux new-session -d -s {session_label} {shlex.quote(run_cmd)}"
    window_name = shlex.quote(session_name)
    has_any_sessions = "tmux list-sessions 2>/dev/null | head -n 1 | grep -q ."
    # Prefer the currently attached tmux session if one exists; otherwise pick the first session.
    pick_base_session = (
        'base=$(tmux list-sessions -F "#{?session_attached,#{session_name},}" 2>/dev/null '
        "| grep -v '^$' | head -n 1 || true); "
        'if [ -z "$base" ]; then base=$(tmux list-sessions -F "#{session_name}" 2>/dev/null | head -n 1); fi'
    )
    window_exists = 'tmux list-windows -t "$base:" -F "#{window_name}" 2>/dev/null | grep -Fxq "$win"'
    window_exists_base = 'tmux list-windows -t "$base:" -F "#{window_name}" 2>/dev/null | grep -Fxq "$win_base"'
    create_window_cmd = f'tmux new-window -t "$base:" -n "$win" {shlex.quote(run_cmd)}'
    select_window_cmd = 'tmux select-window -t "$base:$win"'
    attach_base_cmd = 'tmux attach -t "$base"'

    window_script = (
        f"{pick_base_session}; "
        f"win_base={window_name}; "
        'win="$win_base"; '
        f"if {window_exists_base}; then "
        "i=2; "
        f'while win="$win_base-$i"; {window_exists}; do i=$((i+1)); done; '
        "fi; "
        f"{create_window_cmd}; " + (f"{select_window_cmd} && {attach_base_cmd}" if attach else "true")
    )
    create_script = f"{create_session_cmd} && {attach_cmd_session}" if attach else create_session_cmd
    return f"if {has_any_sessions}; then {window_script}; else {create_script}; fi"


@app.command()
def list_boxes() -> None:
    """List known mettabox hosts."""
    for host in DEFAULT_BOXES:
        typer.echo(host)
    typer.echo(LOCAL_BOX)


@app.command()
def exec(
    host: Annotated[str, typer.Argument(help=HOST_HELP)],
    cmd: Annotated[list[str], typer.Argument(help="Command to run inside the container.")],
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
    tty: Annotated[bool, typer.Option("--tty/--no-tty", help="Allocate a TTY for interactive commands")] = False,
    no_cd: Annotated[bool, typer.Option("--no-cd", help="Skip cd to /workspace/metta before running")] = False,
    forward_gh_token: Annotated[
        bool,
        typer.Option(
            "--forward-gh-token/--no-forward-gh-token",
            help="Forward local GH_TOKEN/GITHUB_TOKEN (or gh auth token) into container env for this command.",
        ),
    ] = True,
    forward_aws_creds: Annotated[
        bool,
        typer.Option(
            "--forward-aws-creds/--no-forward-aws-creds",
            help="Forward local AWS credentials into container env for this command.",
        ),
    ] = True,
) -> None:
    if not cmd:
        raise typer.BadParameter("Command required after '--'.")
    command = shlex.join(cmd)
    forwarded_env = _build_forwarded_env(forward_gh_token=forward_gh_token, forward_aws_creds=forward_aws_creds)
    raise typer.Exit(
        _docker_exec_with_cleanup(
            host,
            container,
            command,
            tty=tty,
            use_repo=not no_cd,
            forwarded_env=forwarded_env,
        )
    )


@app.command()
def run(
    host: Annotated[str, typer.Argument(help=HOST_HELP)],
    tool_args: Annotated[
        list[str],
        typer.Argument(help="Args passed to tools/run.py."),
    ],
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
    tmux: Annotated[bool, typer.Option("--tmux/--no-tmux", help="Run inside tmux")] = True,
    session: Annotated[
        Optional[str],
        typer.Option(
            "--session",
            "-s",
            help="tmux session name override (and window name when tmux is already running).",
        ),
    ] = None,
    attach: Annotated[bool, typer.Option("--attach", help="Attach to tmux after launch")] = False,
    forward_gh_token: Annotated[
        bool,
        typer.Option(
            "--forward-gh-token/--no-forward-gh-token",
            help="Forward local GH_TOKEN/GITHUB_TOKEN (or gh auth token) into container env for this run.",
        ),
    ] = True,
    forward_aws_creds: Annotated[
        bool,
        typer.Option(
            "--forward-aws-creds/--no-forward-aws-creds",
            help="Forward local AWS credentials into container env for this run.",
        ),
    ] = True,
) -> None:
    """Launch a tools/run.py job in tmux.

    Troubleshooting: If tmux shows 'cannot initialize NVML', the NVIDIA driver is broken inside the container.
    Kill/restart the container on the host (docker ps; docker kill metta; docker start metta) and retry the run.
    """
    if not tool_args:
        raise typer.BadParameter("Tools args required after '--'.")
    run_cmd = shlex.join(["uv", "run", "./tools/run.py", *tool_args])
    forwarded_env = _build_forwarded_env(forward_gh_token=forward_gh_token, forward_aws_creds=forward_aws_creds)
    run_id = next((arg.split("=", 1)[1] for arg in tool_args if arg.startswith("run=")), None)
    session_name = session or run_id or "metta-run"
    tty = attach
    if tmux:
        cmd = _tmux_run_cmd(run_cmd, session_name, attach=attach)
    else:
        if attach:
            raise typer.BadParameter("--attach requires --tmux.")
        cmd = run_cmd

    raise typer.Exit(
        _docker_exec_with_cleanup(
            host,
            container,
            cmd,
            tty=tty,
            use_repo=True,
            forwarded_env=forwarded_env,
        )
    )


@app.command()
def runs(
    host: Annotated[Optional[str], typer.Argument(help=HOST_HELP)] = None,
    all_hosts: Annotated[bool, typer.Option("--all", help="List runs on all mettaboxes")] = False,
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
    pattern: Annotated[str, typer.Option("--pattern", "-p", help="Grep pattern for run processes")] = "tools/run.py",
) -> None:
    hosts = _resolve_hosts(host, all_hosts)
    cmd = f"ps -eo pid,etime,command | grep -E {shlex.quote(pattern)} | grep -v grep || true"
    for target in hosts:
        typer.echo(f"\n== {target} ==")
        remote_cmd = _docker_exec(container, cmd, tty=False, use_repo=True)
        exit_code = _ssh(target, remote_cmd, tty=False)
        if exit_code != 0:
            raise typer.Exit(exit_code)


@app.command()
def tmux(
    host: Annotated[str, typer.Argument(help=HOST_HELP)],
    session: Annotated[Optional[str], typer.Argument(help="Session name to attach (optional)")] = None,
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
) -> None:
    if session:
        session_q = shlex.quote(session)
        cmd = f"tmux attach -t {session_q}"
        tty = True
    else:
        cmd = "tmux list-sessions || true"
        tty = False
    remote_cmd = _docker_exec(container, cmd, tty=tty, use_repo=True)
    raise typer.Exit(_ssh(host, remote_cmd, tty=tty))


@app.command()
def instrument(
    host: Annotated[str, typer.Argument(help=HOST_HELP)],
    run_id: Annotated[str, typer.Argument(help="Run ID (used for train_dir/<run_id>.log).")],
    lines: Annotated[int, typer.Option("--lines", "-n", help="Number of log lines to show before following")] = 200,
    follow: Annotated[bool, typer.Option("--follow/--no-follow", help="Follow log output")] = True,
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
    gpu_snapshot: Annotated[bool, typer.Option("--gpu/--no-gpu", help="Show GPU snapshot before logs")] = True,
) -> None:
    """Stream logs and optionally show a GPU snapshot.

    If the GPU snapshot fails with 'cannot initialize NVML', restart the container on the host
    (docker ps; docker kill metta; docker start metta) and retry.
    """
    resolve_cmd = _resolve_log_path_cmd(run_id)
    tail_flag = "-f" if follow else ""
    cmd_parts = []
    if gpu_snapshot:
        cmd_parts.append(
            "if ! nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu "
            "--format=csv,noheader,nounits; then "
            f"echo {shlex.quote('NVML error: ' + NVML_TROUBLESHOOT)} >&2; "
            "fi"
        )
    cmd_parts.append(resolve_cmd)
    cmd_parts.append(f'tail -n {lines} {tail_flag} "$LOG_PATH"')
    cmd = " && ".join(cmd_parts)
    tty = follow
    remote_cmd = _docker_exec(container, cmd, tty=tty, use_repo=True)
    raise typer.Exit(_ssh(host, remote_cmd, tty=tty))


@app.command()
def progress(
    host: Annotated[str, typer.Argument(help=HOST_HELP)],
    run_id: Annotated[str, typer.Argument(help="Run ID (used for train_dir/<run_id> logs).")],
    lines: Annotated[int, typer.Option("--lines", "-n", help="Fallback tail lines if no progress block found")] = 200,
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
) -> None:
    resolve_cmd = _resolve_log_path_cmd(run_id)
    cmd = (
        f"{resolve_cmd}; "
        'last=$(grep -n "Training Progress" "$LOG_PATH" | tail -n 1 | cut -d: -f1 || true); '
        'if [ -z "$last" ]; then tail -n '
        f"{lines} "
        '"$LOG_PATH"; exit 0; fi; '
        'start=$((last-2)); if [ "$start" -lt 1 ]; then start=1; fi; '
        'end=$((last+20)); sed -n "${start},${end}p" "$LOG_PATH"'
    )
    remote_cmd = _docker_exec(container, cmd, tty=False, use_repo=True)
    raise typer.Exit(_ssh(host, remote_cmd, tty=False))


@app.command()
def audit(
    host: Annotated[Optional[str], typer.Argument(help=HOST_HELP)] = None,
    all_hosts: Annotated[bool, typer.Option("--all", help="Audit all mettaboxes")] = False,
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
) -> None:
    hosts = _resolve_hosts(host, all_hosts)
    cmd = " && ".join(
        [
            'echo "[HOST] $(hostname)"',
            f"git -C {WORKSPACE} status -sb",
            'echo "[RUN]"; ps -eo pid,etime,command | grep -E "PID|tools/run.py" || true',
            'echo "[TMUX]"; tmux list-sessions 2>/dev/null || echo "no tmux sessions"',
            'echo "[GPU]"; nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total '
            "--format=csv,noheader,nounits || true",
            f'echo "[DISK]"; df -h {TRAIN_DIR} || true',
        ]
    )
    for target in hosts:
        typer.echo(f"\n== {target} ==")
        remote_cmd = _docker_exec(container, cmd, tty=False, use_repo=True)
        exit_code = _ssh(target, remote_cmd, tty=False)
        if exit_code != 0:
            raise typer.Exit(exit_code)


@app.command()
def profile(
    host: Annotated[str, typer.Argument(help=HOST_HELP)],
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
) -> None:
    cmd = " && ".join(
        [
            'echo "[GPU]"; nvidia-smi || true',
            'echo "[CPU]"; ps -eo pid,pcpu,pmem,etime,command --sort=-pcpu | head -n 15',
            'echo "[MEM]"; ps -eo pid,pcpu,pmem,etime,command --sort=-pmem | head -n 15',
        ]
    )
    remote_cmd = _docker_exec(container, cmd, tty=False, use_repo=True)
    raise typer.Exit(_ssh(host, remote_cmd, tty=False))


@app.command("sky-status")
def sky_status() -> None:
    """Show SkyPilot sandboxes (local command)."""
    raise typer.Exit(subprocess.run(["uv", "run", "sky", "status"]).returncode)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
