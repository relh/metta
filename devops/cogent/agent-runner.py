#!/usr/bin/env python3
"""Cogent agent runner — executes a skill or prompt via Claude Code on a target branch."""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import jwt

METTA_DIR = Path("/home/ubuntu/metta")
COGENTS_DIR = Path("/home/ubuntu/cogents")
CREDENTIALS_FILE = Path.home() / ".config/metta/credentials.sh"
LOG_DIR = Path.home() / ".agent/logs"
DEFAULT_TIMEOUT_MIN = 60


CREDENTIAL_KEYS = [
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "WANDB_API_KEY",
    "DISCORD_WEBHOOK_URL",
    "AGENT_GITHUB_APP_ID",
    "AGENT_GITHUB_APP_PRIVATE_KEY",
]


def load_credentials():
    """Source credentials.sh and load specific env vars (preserves multiline values)."""
    script = f"source {CREDENTIALS_FILE}\n"
    for key in CREDENTIAL_KEYS:
        script += f'printf "%s\\0" "${{{key}}}"\n'

    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    values = result.stdout.split("\0")
    for key, value in zip(CREDENTIAL_KEYS, values, strict=False):
        if value:
            os.environ[key] = value


def generate_github_token() -> str:
    """Generate a short-lived GitHub App installation token."""
    app_id = int(os.environ["AGENT_GITHUB_APP_ID"])
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
    """Write token to git credential store."""
    cred_path = Path.home() / ".git-credentials"
    cred_path.write_text(f"https://x-access-token:{token}@github.com\n")
    cred_path.chmod(0o600)
    subprocess.run(["git", "config", "--global", "credential.helper", "store"], check=True)


def checkout_repo(repo_dir: Path, branch: str, fallback_to_main: bool = False):
    """Fetch and checkout a branch. If fallback_to_main, use main when branch doesn't exist."""
    subprocess.run(["git", "fetch", "--all", "--prune"], cwd=repo_dir, check=True)

    if fallback_to_main:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"origin/{branch}"],
            cwd=repo_dir,
            capture_output=True,
        )
        if result.returncode != 0:
            branch = "main"

    subprocess.run(["git", "checkout", branch], cwd=repo_dir, check=True)
    subprocess.run(["git", "pull", "--ff-only"], cwd=repo_dir, check=True)


PROMPT_DIR = METTA_DIR / "devops" / "cogent" / "prompts"


def read_content(skill: str | None, prompt: str | None) -> tuple[str, str]:
    """Read skill or prompt content. Returns (content, label).

    Skills are read from the cogents repo. Prompts are read from the metta repo
    (branch-specific, checked out via --branch).
    """
    if skill:
        path = COGENTS_DIR / "skills" / skill / "SKILL.md"
        if not path.exists():
            print(f"ERROR: Skill file not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path.read_text(), f"skill-{skill}"

    path = PROMPT_DIR / prompt
    if not path.exists():
        print(f"ERROR: Prompt file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(), f"prompt-{Path(prompt).stem}"


def run_claude(content: str, timeout_min: int) -> subprocess.CompletedProcess:
    """Invoke claude -p with the given content piped via stdin."""
    return subprocess.run(
        ["claude", "-p", "--verbose"],
        input=content,
        cwd=METTA_DIR,
        capture_output=True,
        text=True,
        timeout=timeout_min * 60,
    )


def main():
    parser = argparse.ArgumentParser(description="Cogent agent runner")
    parser.add_argument("--branch", default="main", help="Git branch to check out (default: main)")
    parser.add_argument("--skill", help="Skill name (reads from cogents/skills/<name>/SKILL.md)")
    parser.add_argument("--prompt", help="Prompt path (reads from devops/cogent/prompts/<path> in metta repo)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MIN, help="Timeout in minutes (default: 60)")
    args = parser.parse_args()

    if not args.skill and not args.prompt:
        parser.error("One of --skill or --prompt is required")
    if args.skill and args.prompt:
        parser.error("Only one of --skill or --prompt can be specified")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    label = f"skill-{args.skill}" if args.skill else f"prompt-{Path(args.prompt).stem}"
    log_path = LOG_DIR / f"{timestamp}-{label}.log"

    print(f"[cogent] branch={args.branch} {label} timeout={args.timeout}m")
    print(f"[cogent] log: {log_path}")

    load_credentials()

    print("[cogent] Generating GitHub token...")
    token = generate_github_token()
    configure_git(token)

    print(f"[cogent] Checking out {args.branch} on metta...")
    checkout_repo(METTA_DIR, args.branch)

    print(f"[cogent] Checking out {args.branch} on cogents (fallback to main)...")
    checkout_repo(COGENTS_DIR, args.branch, fallback_to_main=True)

    content, label = read_content(args.skill, args.prompt)

    print(f"[cogent] Running claude ({len(content)} chars)...")
    try:
        result = run_claude(content, args.timeout)
    except subprocess.TimeoutExpired:
        msg = f"TIMEOUT: Claude Code exceeded {args.timeout} minute limit"
        print(f"[cogent] {msg}", file=sys.stderr)
        log_path.write_text(msg + "\n")
        sys.exit(1)

    output = (
        f"=== STDOUT ===\n{result.stdout}\n\n"
        f"=== STDERR ===\n{result.stderr}\n\n"
        f"=== EXIT CODE: {result.returncode} ===\n"
    )
    log_path.write_text(output)
    print(f"[cogent] Done. exit_code={result.returncode} log={log_path}")

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
