#!/usr/bin/env python3
"""Cogent agent runner — executes a skill or prompt via an AI agent CLI on a target branch.

Each run creates isolated git worktrees for both repos so multiple runs can
execute concurrently on different branches without interfering with each other.
Worktrees are cleaned up in a finally block, and stale worktrees from crashed
runs are pruned at startup.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

import jwt
from credentials import load_credentials

METTA_DIR = Path("/home/ubuntu/metta")
COGENTS_DIR = Path("/home/ubuntu/cogents")
WORKTREE_BASE = Path("/home/ubuntu/.agent/worktrees")
LOG_DIR = Path.home() / ".agent/logs"
DEFAULT_TIMEOUT_MIN = 60


def generate_github_token() -> str:
    """Generate a short-lived GitHub App installation token."""
    app_id = os.environ["AGENT_GITHUB_APP_ID"]
    private_key = os.environ["AGENT_GITHUB_APP_PRIVATE_KEY"]

    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
    encoded = jwt.encode(payload, private_key, algorithm="RS256")

    req = urllib.request.Request(
        "https://api.github.com/app/installations",
        headers={"Authorization": f"Bearer {encoded}", "Accept": "application/vnd.github+json"},
    )
    installations = json.loads(urllib.request.urlopen(req).read())
    if not installations:
        raise RuntimeError("GitHub App has no installations")
    install_id = installations[0]["id"]

    req = urllib.request.Request(
        f"https://api.github.com/app/installations/{install_id}/access_tokens",
        method="POST",
        headers={"Authorization": f"Bearer {encoded}", "Accept": "application/vnd.github+json"},
    )
    return json.loads(urllib.request.urlopen(req).read())["token"]


def configure_git(token: str):
    """Set GITHUB_TOKEN env var for the credential helper (no secrets written to disk)."""
    os.environ["GITHUB_TOKEN"] = token


# ---------------------------------------------------------------------------
# Worktree management
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


def prune_worktrees():
    """Remove stale worktrees from crashed runs. Safe to call concurrently."""
    for repo_dir in (METTA_DIR, COGENTS_DIR):
        subprocess.run(["git", "worktree", "prune"], cwd=repo_dir, capture_output=True)

    if not WORKTREE_BASE.exists():
        return
    for entry in WORKTREE_BASE.iterdir():
        if not entry.is_dir():
            continue
        pid_file = entry / ".cogent_pid"
        if not pid_file.exists():
            _rmtree_force(entry)
            continue
        pid = int(pid_file.read_text().strip())
        if not _pid_alive(pid):
            _rmtree_force(entry)


def _pid_alive(pid: int) -> bool:
    """Check if a process is running (UNIX only)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def resolve_branch(repo_dir: Path, branch: str) -> str:
    """Resolve branch to a remote ref, returning 'main' as fallback for cogents."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"origin/{branch}"],
        cwd=repo_dir,
        capture_output=True,
    )
    if result.returncode != 0:
        return "main"
    return branch


def create_worktree(repo_dir: Path, branch: str, run_dir: Path, name: str) -> Path:
    """Create a git worktree for a branch. Returns the worktree path."""
    wt_path = run_dir / name
    ref = f"origin/{branch}"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(wt_path), ref],
        cwd=repo_dir,
        check=True,
        capture_output=True,
    )
    return wt_path


def remove_worktree(repo_dir: Path, wt_path: Path):
    """Remove a worktree and its directory."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(wt_path)],
        cwd=repo_dir,
        capture_output=True,
    )
    if wt_path.exists():
        _rmtree_force(wt_path)


# ---------------------------------------------------------------------------
# Content reading
# ---------------------------------------------------------------------------


def read_content(
    skill: str | None, prompt: str | None, prompt_text: str | None, cogents_wt: Path, metta_wt: Path
) -> tuple[str, str]:
    """Read skill and/or prompt content. Returns (content, label).

    Skills are read from the cogents worktree. Prompts are read from the metta
    worktree (branch-specific). Both can be provided together — skill content
    comes first, prompt content is appended as additional context.
    """
    parts: list[str] = []
    label_parts: list[str] = []

    if skill:
        path = cogents_wt / "skills" / skill / "SKILL.md"
        if not path.exists():
            print(f"ERROR: Skill file not found: {path}", file=sys.stderr)
            sys.exit(1)
        parts.append(path.read_text())
        label_parts.append(f"skill-{skill}")

    if prompt:
        prompt_dir = metta_wt / "devops" / "cogent" / "prompts"
        path = prompt_dir / prompt
        if not path.exists():
            print(f"ERROR: Prompt file not found: {path}", file=sys.stderr)
            sys.exit(1)
        parts.append(path.read_text())
        label_parts.append(f"prompt-{Path(prompt).stem}")

    if prompt_text:
        parts.append(prompt_text)
        if not label_parts:
            label_parts.append("inline-prompt")

    return "\n\n".join(parts), "-".join(label_parts)


# ---------------------------------------------------------------------------
# Agent invocation
# ---------------------------------------------------------------------------

AGENT_COMMANDS = {
    "claude": ["claude", "-p", "--verbose", "--dangerously-skip-permissions"],
    "codex": ["codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "-"],
}


def run_agent(content: str, timeout_min: int, agent: str, cwd: Path) -> subprocess.CompletedProcess:
    """Invoke the chosen agent CLI with the given content piped via stdin."""
    cmd = AGENT_COMMANDS[agent]
    return subprocess.run(
        cmd,
        input=content,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout_min * 60,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Cogent agent runner")
    parser.add_argument("--branch", required=True, help="Git branch to check out")
    parser.add_argument("--skill", help="Skill name (reads from cogents/skills/<name>/SKILL.md)")
    parser.add_argument("--prompt", help="Prompt path (reads from devops/cogent/prompts/<path> in metta repo)")
    parser.add_argument("--prompt-text", help="Raw prompt text (used by poller for inline branch job prompts)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MIN, help="Timeout in minutes (default: 60)")
    parser.add_argument(
        "--agent", choices=list(AGENT_COMMANDS), default="codex", help="Agent CLI to use (default: codex)"
    )
    parser.add_argument("--asana-task-id", help="Asana task GID — post results back as a comment on completion")
    parser.add_argument("--create-branch", help="Create a new branch with this name off --branch before running")
    args = parser.parse_args()

    if not args.skill and not args.prompt and not args.prompt_text:
        parser.error("At least one of --skill, --prompt, or --prompt-text is required")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREE_BASE.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    run_id = f"{timestamp}-{uuid.uuid4().hex[:8]}"
    run_dir = WORKTREE_BASE / run_id

    print(f"[cogent] branch={args.branch} agent={args.agent} timeout={args.timeout}m run={run_id}")

    prune_worktrees()

    load_credentials()

    print("[cogent] Generating GitHub token...")
    token = generate_github_token()
    configure_git(token)

    # Write PID file so stale worktree cleanup can detect crashed runs
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / ".cogent_pid").write_text(str(os.getpid()))

    metta_wt = None
    cogents_wt = None
    push_branch = args.branch
    exit_code = 1

    try:
        print(f"[cogent] Creating metta worktree for {args.branch}...")
        metta_wt = create_worktree(METTA_DIR, args.branch, run_dir, "metta")

        if args.create_branch:
            push_branch = args.create_branch
            print(f"[cogent] Creating branch {push_branch}...")
            subprocess.run(
                ["git", "checkout", "-B", push_branch],
                cwd=metta_wt,
                check=True,
                capture_output=True,
            )
        else:
            push_branch = args.branch
            subprocess.run(
                ["git", "checkout", "-B", push_branch, f"origin/{args.branch}"],
                cwd=metta_wt,
                check=True,
                capture_output=True,
            )

        cogents_branch = resolve_branch(COGENTS_DIR, args.branch)
        print(f"[cogent] Creating cogents worktree for {cogents_branch}...")
        cogents_wt = create_worktree(COGENTS_DIR, cogents_branch, run_dir, "cogents")

        content, label = read_content(args.skill, args.prompt, args.prompt_text, cogents_wt, metta_wt)
        log_path = LOG_DIR / f"{timestamp}-{label}.log"

        print(f"[cogent] Running {args.agent} ({len(content)} chars)...")
        try:
            result = run_agent(content, args.timeout, args.agent, cwd=metta_wt)
        except subprocess.TimeoutExpired:
            msg = f"TIMEOUT: {args.agent} exceeded {args.timeout} minute limit"
            print(f"[cogent] {msg}", file=sys.stderr)
            log_path.write_text(msg + "\n")
            exit_code = 1

        output = (
            f"=== STDOUT ===\n{result.stdout}\n\n"
            f"=== STDERR ===\n{result.stderr}\n\n"
            f"=== EXIT CODE: {result.returncode} ===\n"
        )
        log_path.write_text(output)
        print(f"[cogent] Done. exit_code={result.returncode} log={log_path}")

        if args.asana_task_id:
            print(f"===AGENT_RESULT_START===\n{result.stdout}\n===AGENT_RESULT_END===")

        exit_code = result.returncode

    finally:
        if metta_wt:
            has_commits = subprocess.run(
                ["git", "log", f"origin/{args.branch}..HEAD", "--oneline"],
                cwd=metta_wt,
                capture_output=True,
                text=True,
            )
            if has_commits.returncode == 0 and has_commits.stdout.strip():
                print(f"[cogent] Pushing branch {push_branch}...")
                push_result = subprocess.run(
                    ["git", "push", "-u", "origin", push_branch],
                    cwd=metta_wt,
                    capture_output=True,
                    text=True,
                )
                if push_result.returncode != 0:
                    print(
                        f"[cogent] ERROR: push failed for {push_branch}: {push_result.stderr.strip()}",
                        file=sys.stderr,
                    )
                    exit_code = 1

        print(f"[cogent] Cleaning up worktrees for {run_id}...")
        if metta_wt:
            remove_worktree(METTA_DIR, metta_wt)
        if cogents_wt:
            remove_worktree(COGENTS_DIR, cogents_wt)
        if run_dir.exists():
            _rmtree_force(run_dir)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
