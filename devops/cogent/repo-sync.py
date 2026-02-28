#!/usr/bin/env python3
"""Sync both repos by refreshing the GitHub App token and fetching all branches.

Designed to run from cron every few minutes. Exits silently on success,
prints errors to stderr on failure.
"""

import filecmp
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import jwt
from credentials import load_credentials

REPOS = [Path("/home/ubuntu/metta"), Path("/home/ubuntu/cogents")]

DEPLOY_SRC = Path("/home/ubuntu/metta/devops/cogent")
DEPLOY_DST = Path("/home/ubuntu")
DEPLOYED_FILES = [
    "agent-runner.py",
    "asana_client.py",
    "credentials.py",
    "cron_poller.py",
    "repo-sync.py",
]


def refresh_git_credentials():
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
    install_id = installations[0]["id"]

    req = urllib.request.Request(
        f"https://api.github.com/app/installations/{install_id}/access_tokens",
        method="POST",
        headers={"Authorization": f"Bearer {encoded}", "Accept": "application/vnd.github+json"},
    )
    token = json.loads(urllib.request.urlopen(req).read())["token"]

    os.environ["GITHUB_TOKEN"] = token


def fetch_repos():
    for repo in REPOS:
        if not repo.exists():
            print(f"WARN: repo not found: {repo}", file=sys.stderr)
            continue
        result = subprocess.run(
            ["git", "fetch", "--all", "--prune"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"ERROR fetching {repo.name}: {result.stderr.strip()}", file=sys.stderr)


def deploy_files():
    """Copy cogent scripts from the repo checkout to their deployed locations.

    Only overwrites when the file has actually changed.
    """
    for name in DEPLOYED_FILES:
        src = DEPLOY_SRC / name
        dst = DEPLOY_DST / name
        if not src.exists():
            continue
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            continue
        shutil.copy2(src, dst)
        print(f"deployed: {name}", file=sys.stderr)


def main():
    load_credentials(["AGENT_GITHUB_APP_ID", "AGENT_GITHUB_APP_PRIVATE_KEY"])
    refresh_git_credentials()
    fetch_repos()
    deploy_files()


if __name__ == "__main__":
    main()
