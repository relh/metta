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
from typing import Literal

import jwt

METTA_DIR = Path("/home/ubuntu/metta")
COGENTS_DIR = Path("/home/ubuntu/cogents")
PROMPT_DIR = COGENTS_DIR / "prompts"
CREDENTIALS_FILE = Path.home() / ".config/metta/credentials.sh"
LOG_DIR = Path.home() / ".agent/logs"
DEFAULT_TIMEOUT_MIN = 60
DEFAULT_COGAMES_POLICY = "metta://policy/role_py"
DEFAULT_COGAMES_SEASON = "beta-cvc"
ResearcherProfile = Literal["experienced", "neophyte"]


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


def read_content(skill: str | None, prompt: str | None) -> tuple[str, str]:
    """Read skill or prompt content. Returns (content, label).

    Skills and prompts are both read from the cogents repo.
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


def build_competitor_command(
    policy: str,
    policy_name: str,
    season: str,
    output_root: str,
    cogames_bin: str,
    researcher_profile: ResearcherProfile,
) -> list[str]:
    return [
        "uv",
        "run",
        "./packages/cogames-rl-researcher/scripts/run_ai_researcher_startup.py",
        "--policy",
        policy,
        "--policy-name",
        policy_name,
        "--season",
        season,
        "--researcher-profile",
        researcher_profile,
        "--output-root",
        output_root,
        "--cogames-bin",
        cogames_bin,
    ]


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


def run_command(command: list[str], timeout_min: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=METTA_DIR,
        capture_output=True,
        text=True,
        timeout=timeout_min * 60,
    )


def main():
    parser = argparse.ArgumentParser(description="Cogent agent runner")
    parser.add_argument("--branch", default="main", help="Git branch to check out (default: main)")
    parser.add_argument("--skill", help="Skill name (reads from cogents/skills/<name>/SKILL.md)")
    parser.add_argument("--prompt", help="Prompt path (reads from cogents/prompts/<path>)")
    parser.add_argument(
        "--neophyte-competitor-bot",
        action="store_true",
        help="Run cogames researcher startup using the neophyte profile",
    )
    parser.add_argument(
        "--experienced-competitor-bot",
        action="store_true",
        help="Run cogames researcher startup using the experienced profile",
    )
    parser.add_argument("--policy", default=DEFAULT_COGAMES_POLICY, help="Policy URI/path for researcher startup")
    parser.add_argument("--policy-name", help="Policy name for researcher upload/submit")
    parser.add_argument("--season", default=DEFAULT_COGAMES_SEASON, help="Tournament season")
    parser.add_argument("--output-root", default="./artifacts/ai_researcher", help="Researcher artifact output root")
    parser.add_argument("--cogames-bin", default="cogames", help="Cogames binary path for researcher startup")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_MIN, help="Timeout in minutes (default: 60)")
    args = parser.parse_args()

    competitor_profile: ResearcherProfile | None = None
    if args.neophyte_competitor_bot and args.experienced_competitor_bot:
        parser.error("Use only one of --neophyte-competitor-bot or --experienced-competitor-bot")
    if args.neophyte_competitor_bot:
        competitor_profile = "neophyte"
    if args.experienced_competitor_bot:
        competitor_profile = "experienced"

    if competitor_profile is not None:
        if args.skill or args.prompt:
            parser.error("Competitor bot flags cannot be combined with --skill/--prompt")
        if not args.policy_name:
            parser.error("--policy-name is required with competitor bot flags")
    else:
        if not args.skill and not args.prompt:
            parser.error("One of --skill or --prompt is required")
        if args.skill and args.prompt:
            parser.error("Only one of --skill or --prompt can be specified")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    if competitor_profile is not None:
        label = f"{competitor_profile}-competitor-bot"
    elif args.skill:
        label = f"skill-{args.skill}"
    else:
        label = f"prompt-{Path(args.prompt).stem}"
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

    mode = "claude"
    if competitor_profile is not None:
        command = build_competitor_command(
            policy=args.policy,
            policy_name=args.policy_name,
            season=args.season,
            output_root=args.output_root,
            cogames_bin=args.cogames_bin,
            researcher_profile=competitor_profile,
        )
        print(f"[cogent] Running {competitor_profile} competitor bot: {' '.join(command)}")
        run_target = run_command
        run_args = (command, args.timeout)
        mode = f"{competitor_profile} competitor bot"
    else:
        content, label = read_content(args.skill, args.prompt)
        print(f"[cogent] Running claude ({len(content)} chars)...")
        run_target = run_claude
        run_args = (content, args.timeout)

    try:
        result = run_target(*run_args)
    except subprocess.TimeoutExpired:
        msg = f"TIMEOUT: {mode} exceeded {args.timeout} minute limit"
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
