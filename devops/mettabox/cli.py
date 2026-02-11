#!/usr/bin/env -S uv run
from __future__ import annotations

import shlex
import subprocess
from typing import Annotated, Optional

import typer
from typer import rich_utils

DEFAULT_BOXES = ("metta0", "metta1", "metta2", "metta3", "metta4")
DEFAULT_CONTAINER = "metta"
WORKSPACE = "/workspace/metta"
TRAIN_DIR = "/workspace/metta/train_dir"
NVML_TROUBLESHOOT = (
    "If tmux shows 'cannot initialize NVML', the NVIDIA driver is broken inside the container. "
    "Kill/restart the container on the host (docker ps; docker kill metta; docker start metta) and retry the run."
)

app = typer.Typer(
    rich_markup_mode="rich",
    no_args_is_help=True,
)

rich_utils.STYLE_HELPTEXT = ""  # don't gray out help text - https://github.com/fastapi/typer/issues/437


def _run_local(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode


def _ssh(host: str, remote_cmd: str, *, tty: bool) -> int:
    cmd = ["ssh"]
    if tty:
        cmd.append("-t")
    cmd.append(host)
    cmd.append(remote_cmd)
    return _run_local(cmd)


def _docker_exec(container: str, command: str, *, tty: bool, use_repo: bool) -> str:
    if use_repo:
        command = f"cd {WORKSPACE} && {command}"
    flags = "-it" if tty else "-i"
    return f"docker exec {flags} {shlex.quote(container)} bash -lc {shlex.quote(command)}"


def _log_candidates(run_id: str) -> list[str]:
    return [
        f"{TRAIN_DIR}/{run_id}.log",
        f"{TRAIN_DIR}/{run_id}/logs/script.log",
        f"{TRAIN_DIR}/{run_id}/logs/monitor.log",
    ]


def _resolve_log_path_cmd(run_id: str) -> str:
    candidates = " ".join(shlex.quote(path) for path in _log_candidates(run_id))
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


def _extract_run_id(tool_args: list[str]) -> Optional[str]:
    for arg in tool_args:
        if arg.startswith("run="):
            return arg.split("=", 1)[1]
    return None


def _resolve_hosts(host: Optional[str], all_hosts: bool) -> list[str]:
    if all_hosts:
        return list(DEFAULT_BOXES)
    if host:
        return [host]
    raise typer.BadParameter("Host is required unless --all is set.")


@app.command()
def list_boxes() -> None:
    """List known mettabox hosts."""
    for host in DEFAULT_BOXES:
        typer.echo(host)


@app.command()
def exec(
    host: Annotated[str, typer.Argument(help="Mettabox host (metta0..metta4).")],
    cmd: Annotated[list[str], typer.Argument(help="Command to run inside the container.")],
    container: Annotated[str, typer.Option("--container", "-c", help="Docker container name")] = DEFAULT_CONTAINER,
    tty: Annotated[bool, typer.Option("--tty/--no-tty", help="Allocate a TTY for interactive commands")] = False,
    no_cd: Annotated[bool, typer.Option("--no-cd", help="Skip cd to /workspace/metta before running")] = False,
) -> None:
    if not cmd:
        raise typer.BadParameter("Command required after '--'.")
    command = shlex.join(cmd)
    remote_cmd = _docker_exec(container, command, tty=tty, use_repo=not no_cd)
    raise typer.Exit(_ssh(host, remote_cmd, tty=tty))


@app.command()
def run(
    host: Annotated[str, typer.Argument(help="Mettabox host (metta0..metta4).")],
    tool_args: Annotated[
        list[str],
        typer.Argument(
            help="Args passed to tools/run.py (do not include 'python tools/run.py' or 'uv run ./tools/run.py')."
        ),
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
) -> None:
    """Launch a tools/run.py job in tmux.

    Troubleshooting: If tmux shows 'cannot initialize NVML', the NVIDIA driver is broken inside the container.
    Kill/restart the container on the host (docker ps; docker kill metta; docker start metta) and retry the run.
    """
    prefixes = (
        ("uv", "run", "./tools/run.py"),
        ("uv", "run", "tools/run.py"),
        ("python", "./tools/run.py"),
        ("python", "tools/run.py"),
        ("python3", "./tools/run.py"),
        ("python3", "tools/run.py"),
        ("./tools/run.py",),
        ("tools/run.py",),
    )
    stripped_prefix: Optional[tuple[str, ...]] = None
    for prefix in prefixes:
        if tool_args[: len(prefix)] == list(prefix):
            tool_args = tool_args[len(prefix) :]
            stripped_prefix = prefix
            break
    if stripped_prefix:
        typer.echo(f"Note: stripped leading {' '.join(stripped_prefix)!r}; mettabox CLI already wraps tools/run.py.")
    if not tool_args:
        raise typer.BadParameter("Tools args required after '--'.")
    run_cmd = shlex.join(["uv", "run", "./tools/run.py", *tool_args])
    session_name = session or _extract_run_id(tool_args) or "metta-run"
    tty = attach
    if tmux:
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
        create_window_cmd = f'tmux new-window -t "$base:" -n "$win" {shlex.quote(run_cmd)}'
        select_window_cmd = 'tmux select-window -t "$base:$win"'
        attach_base_cmd = 'tmux attach -t "$base"'

        window_script = (
            f"{pick_base_session}; "
            f"win={window_name}; "
            f"if ! {window_exists}; then {create_window_cmd}; fi; "
            + (f"{select_window_cmd} && {attach_base_cmd}" if attach else "true")
        )

        if attach:
            cmd = f"if {has_any_sessions}; then {window_script}; else {create_session_cmd} && {attach_cmd_session}; fi"
        else:
            cmd = f"if {has_any_sessions}; then {window_script}; else {create_session_cmd}; fi"
    else:
        if attach:
            raise typer.BadParameter("--attach requires --tmux.")
        cmd = run_cmd

    docker_cmd = _docker_exec(container, cmd, tty=tty, use_repo=True)
    raise typer.Exit(_ssh(host, docker_cmd, tty=tty))


app.command("launch")(run)


@app.command()
def runs(
    host: Annotated[Optional[str], typer.Argument(help="Mettabox host (metta0..metta4).")] = None,
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
    host: Annotated[str, typer.Argument(help="Mettabox host (metta0..metta4).")],
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
    host: Annotated[str, typer.Argument(help="Mettabox host (metta0..metta4).")],
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
    host: Annotated[str, typer.Argument(help="Mettabox host (metta0..metta4).")],
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
    host: Annotated[Optional[str], typer.Argument(help="Mettabox host (metta0..metta4).")] = None,
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
    host: Annotated[str, typer.Argument(help="Mettabox host (metta0..metta4).")],
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
    raise typer.Exit(_run_local(["uv", "run", "sky", "status"]))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
