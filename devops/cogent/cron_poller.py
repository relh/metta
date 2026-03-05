#!/usr/bin/env python3
"""Cogent poller — ticks every minute, runs scheduled jobs, branch jobs, and Asana tasks.

Three job sources:
  1. cron_schedule.py JOBS list — recurring/one-shot jobs checked into the repo
  2. .agent/jobs/*.md on remote branches — jobs submitted by agents on feature branches
  3. Asana tasks assigned to the agent user — picked up automatically each tick

The poller is invoked every minute by cron:
  * * * * * /usr/bin/python3 /home/ubuntu/cron_poller.py >> ~/.agent/logs/poller.log 2>&1

It maintains a small state file (~/.agent/poller_state.json) to track last-run
times and completed one-shot jobs.
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

METTA_DIR = Path("/home/ubuntu/metta")
COGENTS_DIR = Path("/home/ubuntu/cogents")
WORKTREE_BASE = Path.home() / ".agent/worktrees"
STATE_FILE = Path.home() / ".agent/poller_state.json"
LOG_DIR = Path.home() / ".agent/logs"
RUNNER = Path("/home/ubuntu/agent-runner.py")
SYNC_SCRIPT = Path("/home/ubuntu/repo-sync.py")

JOBS_DIR = ".agent/jobs"

# Only remote refs matching these prefixes are scanned for .agent/jobs/ files.
# Agents opt in by pushing to a branch under one of these prefixes.
SCAN_PREFIXES = [
    "origin/cogent/",
]

BRANCH_ONCE_MAX_RETRIES = 2
BRANCH_ONCE_RETRY_DELAY_MINUTES = 5


def log(msg: str):
    print(f"[poller] {datetime.now(timezone.utc).strftime('%H:%M:%S')} {msg}", flush=True)


FAILURE_CONTEXT_LINES = 20


def _log_failure_context(label: str, result: subprocess.CompletedProcess):
    """Log exit code and a bounded tail of stderr/stdout for failed jobs."""
    log(f"{label}: exit_code={result.returncode}")
    for stream_name, text in [("stderr", result.stderr), ("stdout", result.stdout)]:
        if not text or not text.strip():
            continue
        lines = text.strip().splitlines()
        tail = lines[-FAILURE_CONTEXT_LINES:]
        if len(lines) > FAILURE_CONTEXT_LINES:
            log(f"{label}: {stream_name} (last {FAILURE_CONTEXT_LINES} of {len(lines)} lines):")
        else:
            log(f"{label}: {stream_name}:")
        for line in tail:
            log(f"{label}:   {line}")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_run": {}, "completed_once": []}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")


# ---------------------------------------------------------------------------
# Schedule matching
# ---------------------------------------------------------------------------


def is_due(
    job_name: str, frequency: str, interval: int | None, at_hour: int | None, at_minute: int, now: datetime, state: dict
) -> bool:
    """Determine whether a job should fire this minute."""
    last_run_str = state["last_run"].get(job_name)
    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None

    if frequency == "once":
        return job_name not in state.get("completed_once", [])

    if frequency == "minutes":
        if last_run is None:
            return True
        elapsed = (now - last_run).total_seconds()
        return elapsed >= (interval or 1) * 60

    if frequency == "hourly":
        if now.minute != at_minute:
            return False
        if last_run and last_run.hour == now.hour and last_run.date() == now.date():
            return False
        return True

    if frequency in ("daily", "weekdays"):
        if frequency == "weekdays" and now.weekday() >= 5:
            return False
        if now.hour != at_hour or now.minute != at_minute:
            return False
        if last_run and last_run.date() == now.date():
            return False
        return True

    return False


def mark_ran(job_name: str, frequency: str, now: datetime, state: dict):
    state["last_run"][job_name] = now.isoformat()
    if frequency == "once":
        state.setdefault("completed_once", [])
        if job_name not in state["completed_once"]:
            state["completed_once"].append(job_name)


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------


def run_sync(state: dict, now: datetime):
    """Run repo-sync.py (token refresh + fetch)."""
    log("sync: refreshing tokens and fetching repos")
    t0 = time.monotonic()
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        capture_output=True,
        text=True,
    )
    record_job_outcome(state, "sync", result.returncode, time.monotonic() - t0, now)
    if result.returncode != 0:
        log(f"sync: FAILED: {result.stderr.strip()}")


def run_agent_job(
    *,
    branch: str,
    skill: str | None = None,
    prompt: str | None = None,
    timeout: int = 60,
    agent: str = "codex",
    label: str,
    state: dict,
    now: datetime,
) -> bool:
    """Invoke agent-runner.py as a subprocess."""
    cmd = [sys.executable, str(RUNNER), "--branch", branch, "--timeout", str(timeout), "--agent", agent]
    if skill:
        cmd += ["--skill", skill]
    if prompt:
        cmd += ["--prompt", prompt]
    if not skill and not prompt:
        raise ValueError(f"{label}: job must specify skill or prompt")

    log(f"{label}: running on branch={branch} agent={agent}")
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    record_job_outcome(state, label, result.returncode, time.monotonic() - t0, now)
    if result.returncode != 0:
        _log_failure_context(label, result)
        return False
    log(f"{label}: done")
    return True


def run_inline_prompt(
    *, branch: str, content: str, timeout: int = 60, agent: str = "codex", label: str, state: dict, now: datetime
) -> bool:
    """Run an inline prompt by passing text directly to agent-runner via --prompt-text."""
    cmd = [
        sys.executable,
        str(RUNNER),
        "--branch",
        branch,
        "--timeout",
        str(timeout),
        "--agent",
        agent,
        "--prompt-text",
        content,
    ]

    log(f"{label}: running inline prompt on branch={branch} agent={agent}")
    t0 = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True)
    record_job_outcome(state, label, result.returncode, time.monotonic() - t0, now)
    if result.returncode != 0:
        _log_failure_context(label, result)
        return False
    log(f"{label}: done")
    return True


# ---------------------------------------------------------------------------
# Branch job scanning
# ---------------------------------------------------------------------------


def list_remote_branches(repo_dir: Path) -> list[str]:
    """List remote branch refs matching SCAN_PREFIXES."""
    result = subprocess.run(
        ["git", "branch", "-r", "--list"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    branches = []
    for line in result.stdout.strip().splitlines():
        ref = line.strip()
        if any(ref.startswith(p) for p in SCAN_PREFIXES):
            branches.append(ref)
    return branches


def list_branch_jobs(repo_dir: Path, ref: str) -> list[str]:
    """List .agent/jobs/ files on a remote branch without checkout."""
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", ref, "--", JOBS_DIR + "/"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]


def read_branch_file(repo_dir: Path, ref: str, path: str) -> str:
    """Read a file from a remote branch ref without checkout."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def delete_branch_job_file(repo_dir: Path, branch: str, file_path: str):
    """Delete a completed one-shot job file from a branch and push.

    Uses a temporary worktree to avoid touching the shared checkout.
    """
    wt_path = WORKTREE_BASE / f"cleanup-{branch.replace('/', '-')}-{os.getpid()}"
    wt_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["git", "worktree", "add", str(wt_path), f"origin/{branch}"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        # Create a local branch tracking the remote so we can push
        subprocess.run(
            ["git", "checkout", "-B", branch, f"origin/{branch}"],
            cwd=wt_path,
            capture_output=True,
            check=True,
        )

        full_path = wt_path / file_path
        if not full_path.exists():
            log(f"cleanup: {file_path} already gone from {branch}")
            return

        try:
            subprocess.run(["git", "rm", str(file_path)], cwd=wt_path, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            log(f"cleanup: {file_path} already removed or git rm failed")
            return
        subprocess.run(
            ["git", "commit", "-m", f"[cogent] cleanup: completed one-shot job {Path(file_path).name}"],
            cwd=wt_path,
            capture_output=True,
            check=True,
        )
        result = subprocess.run(
            ["git", "push", "origin", branch],
            cwd=wt_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log(f"cleanup: push failed for {branch}: {result.stderr.strip()}")
        else:
            log(f"cleanup: deleted {file_path} from {branch}")
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(wt_path)],
            cwd=repo_dir,
            capture_output=True,
        )
        if wt_path.exists():
            _rmtree_force(wt_path)


def parse_job_frontmatter(content: str) -> dict[str, str]:
    """Parse simple key: value frontmatter from a markdown file.

    Expected format:
        ---
        schedule: weekdays 9:00
        skill: cb.review-main
        timeout: 30
        ---
        Optional body used as inline prompt if no skill/prompt specified.
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {"_body": content}

    meta: dict[str, str] = {}
    body_start = 1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = i + 1
            break
        match = re.match(r"^(\w[\w_-]*)\s*:\s*(.+)$", line.strip())
        if match:
            meta[match.group(1).lower()] = match.group(2).strip()
    meta["_body"] = "\n".join(lines[body_start:]).strip()
    return meta


def parse_schedule_string(s: str) -> tuple[str, int | None, int | None, int]:
    """Parse a human-readable schedule string.

    Formats:
        "once"              → run once
        "every 5m"          → every 5 minutes
        "daily 14:30"       → daily at 14:30 UTC
        "weekdays 9:00"     → Mon-Fri at 9:00 UTC
        "hourly :15"        → every hour at minute 15
    """
    s = s.strip().lower()

    if s == "once":
        return "once", None, None, 0

    m = re.match(r"every\s+(\d+)\s*m", s)
    if m:
        return "minutes", int(m.group(1)), None, 0

    m = re.match(r"hourly\s+:(\d+)", s)
    if m:
        return "hourly", None, None, int(m.group(1))

    m = re.match(r"(daily|weekdays)\s+(\d+):(\d+)", s)
    if m:
        return m.group(1), None, int(m.group(2)), int(m.group(3))

    return "once", None, None, 0


def _job_fingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _branch_once_retry_state(state: dict) -> dict:
    return state.setdefault("branch_once_retries", {})


def _should_run_branch_once_job(job_id: str, job_fingerprint: str, now: datetime, state: dict) -> bool:
    retry_state = _branch_once_retry_state(state)
    entry = retry_state.get(job_id)
    if not entry:
        return True

    if entry.get("job_fingerprint") != job_fingerprint:
        retry_state.pop(job_id, None)
        return True

    if entry.get("exhausted"):
        return False

    next_retry_at = entry.get("next_retry_at")
    if not next_retry_at:
        return True
    return now >= datetime.fromisoformat(next_retry_at)


def _record_branch_once_failure(job_id: str, job_fingerprint: str, now: datetime, state: dict):
    retry_state = _branch_once_retry_state(state)
    entry = retry_state.get(job_id, {})
    if entry.get("job_fingerprint") != job_fingerprint:
        failed_attempts = 0
    else:
        failed_attempts = int(entry.get("failed_attempts", 0))
    failed_attempts += 1

    exhausted = failed_attempts > BRANCH_ONCE_MAX_RETRIES
    retry_state[job_id] = {
        "job_fingerprint": job_fingerprint,
        "failed_attempts": failed_attempts,
        "last_failed_at": now.isoformat(),
        "next_retry_at": None if exhausted else (now + timedelta(minutes=BRANCH_ONCE_RETRY_DELAY_MINUTES)).isoformat(),
        "exhausted": exhausted,
    }


def _clear_branch_once_retry(job_id: str, state: dict):
    _branch_once_retry_state(state).pop(job_id, None)


# ---------------------------------------------------------------------------
# Worktree cleanup
# ---------------------------------------------------------------------------


def _rmtree_force(path: Path):
    """Remove a directory tree, handling read-only dirs (e.g. Bazel output)."""

    def _on_error(func, fpath, _exc_info):
        p = Path(fpath)
        # For scandir/listdir failures, the dir itself needs +rx.
        # For unlink/rmdir failures, the parent needs +w.
        if p.is_dir():
            p.chmod(p.stat().st_mode | 0o700)
        p.parent.chmod(p.parent.stat().st_mode | 0o700)
        func(fpath)

    shutil.rmtree(path, onerror=_on_error)


def prune_stale_worktrees():
    """Remove worktrees from crashed agent-runner processes.

    Each run writes a .cogent_pid file. If the PID is no longer alive, the
    worktree is orphaned and safe to remove.
    """
    for repo_dir in (METTA_DIR, COGENTS_DIR):
        subprocess.run(["git", "worktree", "prune"], cwd=repo_dir, capture_output=True)

    if not WORKTREE_BASE.exists():
        return

    for entry in WORKTREE_BASE.iterdir():
        if not entry.is_dir():
            continue
        pid_file = entry / ".cogent_pid"
        if not pid_file.exists():
            log(f"worktree-prune: removing {entry.name} (no pid file)")
            _rmtree_force(entry)
            continue
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)
        except OSError:
            log(f"worktree-prune: removing {entry.name} (pid {pid} dead)")
            _rmtree_force(entry)


# ---------------------------------------------------------------------------
# State pruning & log rotation (gated to once per hour)
# ---------------------------------------------------------------------------

PRUNE_INTERVAL_S = 3600
JOB_HISTORY_MAX = 500


def _branch_from_key(key: str) -> str | None:
    """Extract branch name from a 'branch:<branch>:<file>' key."""
    if not key.startswith("branch:"):
        return None
    parts = key.split(":", 2)
    return parts[1] if len(parts) >= 3 else None


def _remote_ref_exists(branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{branch}"],
        cwd=METTA_DIR,
        capture_output=True,
    )
    return result.returncode == 0


def prune_stale_state(state: dict, now: datetime):
    """Remove entries for completed/gone items from poller state."""
    # asana_tasks: drop terminal entries older than 7 days
    asana_tasks = state.get("asana_tasks", {})
    cutoff = now - timedelta(days=7)
    for gid in list(asana_tasks):
        entry = asana_tasks[gid]
        if entry.get("status") not in ("completed", "failed"):
            continue
        last_run = entry.get("last_run")
        if last_run and datetime.fromisoformat(last_run) < cutoff:
            del asana_tasks[gid]
            log(f"state-prune: removed stale asana task {gid}")

    # completed_once: drop branch: entries whose remote branch is gone
    completed_once = state.get("completed_once", [])
    for name in list(completed_once):
        branch = _branch_from_key(name)
        if branch is None:
            continue
        if not _remote_ref_exists(branch):
            completed_once.remove(name)
            log(f"state-prune: removed stale completed_once {name}")

    # last_run: drop branch: entries whose remote branch is gone
    last_run_dict = state.get("last_run", {})
    for key in list(last_run_dict):
        branch = _branch_from_key(key)
        if branch is None:
            continue
        if not _remote_ref_exists(branch):
            del last_run_dict[key]
            log(f"state-prune: removed stale last_run {key}")

    # branch_once_retries: drop entries whose remote branch is gone
    retries = state.get("branch_once_retries", {})
    for key in list(retries):
        branch = _branch_from_key(key)
        if branch is None:
            continue
        if not _remote_ref_exists(branch):
            del retries[key]
            log(f"state-prune: removed stale branch_once_retries {key}")


def record_job_outcome(state: dict, label: str, exit_code: int, duration_s: float, now: datetime):
    history = state.setdefault("job_history", [])
    history.append(
        {
            "job": label,
            "time": now.isoformat(),
            "exit_code": exit_code,
            "duration_s": round(duration_s, 1),
        }
    )
    if len(history) > JOB_HISTORY_MAX:
        del history[: len(history) - JOB_HISTORY_MAX]


def rotate_old_logs():
    """Delete per-run log files older than 14 days."""
    if not LOG_DIR.exists():
        return
    cutoff = time.time() - 14 * 86400
    for entry in LOG_DIR.iterdir():
        if entry.name == "poller.log":
            continue
        if not entry.name.endswith(".log"):
            continue
        if entry.stat().st_mtime < cutoff:
            entry.unlink()
            log(f"log-rotate: deleted {entry.name}")


STALE_BRANCH_DAYS = 7


def prune_stale_branches():
    """Delete origin/cogent/* branches with no job files and no recent commits."""
    result = subprocess.run(
        ["git", "branch", "-r", "--list", "origin/cogent/*"],
        cwd=METTA_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return
    cutoff_epoch = int(time.time()) - STALE_BRANCH_DAYS * 86400
    for line in result.stdout.strip().splitlines():
        ref = line.strip()
        if not ref:
            continue
        branch = ref.removeprefix("origin/")
        jobs = subprocess.run(
            ["git", "ls-tree", "--name-only", ref, "--", JOBS_DIR + "/"],
            cwd=METTA_DIR,
            capture_output=True,
            text=True,
        )
        if jobs.returncode == 0 and jobs.stdout.strip():
            continue
        commit_time = subprocess.run(
            ["git", "log", "-1", "--format=%ct", ref],
            cwd=METTA_DIR,
            capture_output=True,
            text=True,
        )
        if commit_time.returncode != 0:
            continue
        if int(commit_time.stdout.strip()) > cutoff_epoch:
            continue
        delete = subprocess.run(
            ["git", "push", "origin", "--delete", branch],
            cwd=METTA_DIR,
            capture_output=True,
            text=True,
        )
        if delete.returncode == 0:
            log(f"branch-prune: deleted stale branch {branch}")
        else:
            log(f"branch-prune: failed to delete {branch}: {delete.stderr.strip()}")


# ---------------------------------------------------------------------------
# Asana task scanning
# ---------------------------------------------------------------------------


def _remote_branch_exists(branch: str) -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{branch}"],
        cwd=METTA_DIR,
        capture_output=True,
    )
    return result.returncode == 0


def _extract_agent_result(stdout: str) -> str:
    """Extract the agent's actual output from runner stdout.

    The runner wraps the agent response between delimiter lines. If the
    delimiters aren't found (older runner, or no --asana-task-id), fall back
    to the full stdout.
    """
    start_marker = "===AGENT_RESULT_START==="
    end_marker = "===AGENT_RESULT_END==="
    start = stdout.find(start_marker)
    if start == -1:
        return stdout.strip()
    start += len(start_marker) + 1
    end = stdout.find(end_marker, start)
    if end == -1:
        return stdout[start:].strip()
    return stdout[start:end].strip()


ASANA_CREDENTIAL_KEYS = [
    "ASANA_TOKEN",
    "ASANA_WORKSPACE_GID",
    "ASANA_AGENT_USER_GID",
    "ASANA_RUNNING_TAG_GID",
]


def _load_asana_credentials():
    """Load Asana env vars from Secrets Manager (cron doesn't inherit them)."""
    if os.environ.get("ASANA_TOKEN"):
        return
    from credentials import load_credentials  # noqa: PLC0415

    load_credentials(ASANA_CREDENTIAL_KEYS)


def scan_asana_tasks(state: dict, now: datetime):
    """Scan for Asana tasks assigned to the agent and dispatch them."""
    _load_asana_credentials()
    if not os.environ.get("ASANA_TOKEN"):
        return

    from asana_client import AsanaClient  # noqa: PLC0415 — deferred so poller works without Asana config

    client = AsanaClient.from_env()
    asana_state = state.setdefault("asana_tasks", {})

    def _refresh_last_comment_seen(gid: str, fallback: str) -> str:
        """Read task context again so poller-authored comments are marked as seen."""
        try:
            latest = client.get_task_context(gid).latest_comment_time
            return latest or fallback
        except Exception as e:
            log(f"asana:{gid}: failed to refresh latest comment time: {e}")
            return fallback

    for task in client.get_assigned_tasks():
        gid = task.get("gid")
        if not gid:
            log("asana: skipping task without gid")
            continue
        label = f"asana:{gid}"

        try:
            task_state = asana_state.get(gid, {})

            if task_state.get("status") == "running":
                continue

            ctx = client.get_task_context(gid)

            if task_state.get("status") in ("completed", "failed"):
                last_seen = task_state.get("last_comment_seen", "")
                if not ctx.latest_comment_time or ctx.latest_comment_time <= last_seen:
                    continue

            if ctx.branch:
                branch = ctx.branch
                if not _remote_branch_exists(branch):
                    client.post_comment(
                        gid,
                        f"Branch `{branch}` does not exist on the remote. Check the `branch` custom field for typos.",
                    )
                    last_seen = _refresh_last_comment_seen(gid, ctx.latest_comment_time or now.isoformat())
                    asana_state[gid] = {
                        "branch": branch,
                        "last_run": now.isoformat(),
                        "last_comment_seen": last_seen,
                        "status": "failed",
                    }
                    save_state(state)
                    log(f"{label}: branch `{branch}` not found on remote")
                    continue
                create_branch = None
            else:
                branch = f"cogent/asana-{gid}"
                if _remote_branch_exists(branch):
                    create_branch = None
                else:
                    create_branch = branch

            prompt = ctx.to_prompt()

            asana_state[gid] = {
                "branch": branch,
                "last_run": now.isoformat(),
                "last_comment_seen": ctx.latest_comment_time or now.isoformat(),
                "status": "running",
            }
            save_state(state)

            terminal_status = "failed"
            try:
                client.post_comment(gid, f"Started working on branch `{branch}`. Will post results here when done.")
                client.add_tag(gid, client.running_tag_gid)

                cmd = [
                    sys.executable,
                    str(RUNNER),
                    "--branch",
                    "main" if create_branch else branch,
                    "--prompt-text",
                    prompt,
                    "--asana-task-id",
                    gid,
                ]
                if create_branch:
                    cmd += ["--create-branch", create_branch]
                if ctx.skill:
                    cmd += ["--skill", ctx.skill]

                log(f"{label}: dispatching on branch={branch}")
                t0 = time.monotonic()
                result = subprocess.run(cmd, capture_output=True, text=True)
                record_job_outcome(state, label, result.returncode, time.monotonic() - t0, now)

                if result.returncode == 0:
                    output = _extract_agent_result(result.stdout)
                    if len(output) > 60000:
                        output = output[:60000] + "\n\n... (truncated)"
                    client.post_comment(gid, f"Completed.\n\n{output}")
                    client.complete_task(gid)
                    terminal_status = "completed"
                    log(f"{label}: done")
                else:
                    stderr = result.stderr.strip()
                    if len(stderr) > 10000:
                        stderr = stderr[:10000] + "\n\n... (truncated)"
                    client.post_comment(gid, f"Failed (exit code {result.returncode}).\n\n{stderr}")
                    terminal_status = "failed"
                    log(f"{label}: exit_code={result.returncode}")
            except Exception as e:
                log(f"{label}: post-run failure: {e}")
                terminal_status = "failed"
            finally:
                try:
                    client.remove_tag(gid, client.running_tag_gid)
                except Exception as e:
                    log(f"{label}: failed to remove running tag: {e}")
                asana_state[gid]["status"] = terminal_status
                asana_state[gid]["last_run"] = now.isoformat()
                asana_state[gid]["last_comment_seen"] = _refresh_last_comment_seen(
                    gid, asana_state[gid].get("last_comment_seen", now.isoformat())
                )
                save_state(state)
        except Exception as e:
            log(f"{label}: task scan failed: {e}")
            if gid in asana_state and asana_state[gid].get("status") == "running":
                asana_state[gid]["status"] = "failed"
                asana_state[gid]["last_run"] = now.isoformat()
                save_state(state)


# ---------------------------------------------------------------------------
# Main tick
# ---------------------------------------------------------------------------


def load_schedule_jobs() -> list:
    """Import JOBS from cron_schedule.py in the metta checkout."""
    schedule_path = METTA_DIR / "devops" / "cogent" / "cron_schedule.py"
    if not schedule_path.exists():
        return []
    spec = importlib.util.spec_from_file_location("cron_schedule", schedule_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "JOBS", [])


def tick():
    now = datetime.now(timezone.utc)
    state = load_state()

    prune_stale_worktrees()

    # Hourly maintenance: prune stale state + rotate old logs
    last_prune_str = state.get("last_prune")
    last_prune = None
    if last_prune_str:
        try:
            last_prune = datetime.fromisoformat(last_prune_str)
        except (ValueError, TypeError):
            log(f"state: invalid last_prune value {last_prune_str!r}, resetting")
            state.pop("last_prune", None)
    if last_prune is None or (now - last_prune).total_seconds() >= PRUNE_INTERVAL_S:
        prune_stale_state(state, now)
        rotate_old_logs()
        prune_stale_branches()
        state["last_prune"] = now.isoformat()

    # --- 1. Checked-in jobs from cron_schedule.py ---
    try:
        for job in load_schedule_jobs():
            if not job.enabled:
                continue
            sched = job.schedule
            if not is_due(job.name, sched.frequency.value, sched.interval, sched.at_hour, sched.at_minute, now, state):
                continue

            if job.action.value == "sync":
                run_sync(state, now)
            else:
                run_agent_job(
                    branch=job.branch,
                    skill=job.skill,
                    prompt=job.prompt,
                    timeout=job.timeout_minutes,
                    agent=job.agent,
                    label=job.name,
                    state=state,
                    now=now,
                )
            mark_ran(job.name, sched.frequency.value, now, state)
    except Exception as e:
        log(f"schedule-jobs: failed: {e}")

    # --- 2. Branch-submitted jobs from .agent/jobs/*.md ---
    try:
        for ref in list_remote_branches(METTA_DIR):
            branch_name = ref.removeprefix("origin/")

            for file_path in list_branch_jobs(METTA_DIR, ref):
                if not file_path.endswith(".md"):
                    continue
                content = read_branch_file(METTA_DIR, ref, file_path)
                if not content:
                    continue

                meta = parse_job_frontmatter(content)
                job_id = f"branch:{branch_name}:{Path(file_path).name}"
                job_fingerprint = _job_fingerprint(content)

                sched_str = meta.get("schedule", "once")
                frequency, interval, at_hour, at_minute = parse_schedule_string(sched_str)
                timeout = int(meta.get("timeout", "60"))

                if not is_due(job_id, frequency, interval, at_hour, at_minute, now, state):
                    continue
                if frequency == "once" and not _should_run_branch_once_job(job_id, job_fingerprint, now, state):
                    continue

                skill = meta.get("skill")
                prompt = meta.get("prompt")
                agent = meta.get("agent", "codex")
                body = meta.get("_body", "")

                if skill or prompt:
                    success = run_agent_job(
                        branch=branch_name,
                        skill=skill,
                        prompt=prompt,
                        timeout=timeout,
                        agent=agent,
                        label=job_id,
                        state=state,
                        now=now,
                    )
                elif body:
                    success = run_inline_prompt(
                        branch=branch_name,
                        content=body,
                        timeout=timeout,
                        agent=agent,
                        label=job_id,
                        state=state,
                        now=now,
                    )
                else:
                    log(f"{job_id}: skipped — no skill, prompt, or body")
                    continue

                if success:
                    mark_ran(job_id, frequency, now, state)
                    if frequency == "once":
                        _clear_branch_once_retry(job_id, state)
                        delete_branch_job_file(METTA_DIR, branch_name, file_path)
                else:
                    log(f"{job_id}: failed — retaining job file for retry")
                    if frequency == "once":
                        _record_branch_once_failure(job_id, job_fingerprint, now, state)
                    else:
                        mark_ran(job_id, frequency, now, state)
    except Exception as e:
        log(f"branch-jobs: failed: {e}")

    # --- 3. Asana tasks assigned to agent ---
    try:
        scan_asana_tasks(state, now)
    except Exception as e:
        log(f"asana-scan: failed: {e}")

    save_state(state)


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tick()


if __name__ == "__main__":
    main()
