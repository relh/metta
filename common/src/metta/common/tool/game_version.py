from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from metta.common.util.fs import get_repo_root

GAME_VERSION_ALIASES = {
    "arena_basic_easy_shaped": "964e50e1beb6b06afdc295126fcbedacf8a55142",
    "arena_basic_easy_shaped_last_good": "964e50e1beb6b06afdc295126fcbedacf8a55142",
    "cvc_pre_cogsguard": "dd7179580e82781eba528461db0f0c9b770ac3a1",
    "cogs_v_clips_pre_cogsguard": "dd7179580e82781eba528461db0f0c9b770ac3a1",
}


def sanitize_alias_env_key(alias: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", alias).upper().strip("_")
    return f"METTA_GAME_VERSION_{cleaned}"


def is_git_commit(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{7,40}", value))


def resolve_game_version(version: str, aliases: dict[str, str] | None = None) -> str:
    alias_map = aliases or GAME_VERSION_ALIASES
    if not is_git_commit(version):
        env_key = sanitize_alias_env_key(version)
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
    if version in alias_map:
        commit = alias_map[version]
        if commit:
            return commit
        env_key = sanitize_alias_env_key(version)
        raise ValueError(
            f"Game version alias '{version}' is not configured. "
            f"Set {env_key} to a git commit hash or pass a commit directly."
        )
    if is_git_commit(version):
        return version
    raise ValueError(f"Unknown game version '{version}'.")


def parse_game_version_args(argv: list[str]) -> tuple[str | None, list[str]]:
    filtered: list[str] = []
    version: str | None = None
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg in {"--game-version", "--game_version"}:
            if idx + 1 >= len(argv):
                raise ValueError("--game-version requires a value")
            version = argv[idx + 1]
            idx += 2
            continue
        if arg.startswith("--game-version=") or arg.startswith("--game_version="):
            version = arg.split("=", 1)[1]
            idx += 1
            continue
        filtered.append(arg)
        idx += 1
    return version, filtered


def resolve_full_commit_hash(repo_root: Path | str, commit: str) -> str:
    result = subprocess.run(
        ["git", "rev-parse", commit],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    return result.stdout.strip()


def _worktree_head(path: Path | str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip()


def ensure_game_version_worktree(repo_root: Path | str, version_name: str, commit: str) -> Path:
    repo_root = Path(repo_root)
    commit = resolve_full_commit_hash(repo_root, commit)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", version_name).strip("_") or "game_version"
    worktree_root = repo_root / ".metta" / "game_versions"
    worktree_root.mkdir(parents=True, exist_ok=True)
    worktree_path = worktree_root / f"{safe_name}-{commit[:12]}"
    if worktree_path.exists():
        head = _worktree_head(worktree_path)
        if head == commit:
            return worktree_path
        if head is None:
            raise ValueError(f"Existing game version path is not a git worktree: {worktree_path}")
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            check=True,
            cwd=str(repo_root),
        )
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree_path), commit],
        check=True,
        cwd=str(repo_root),
    )
    return worktree_path


def run_in_game_version(version: str, argv: list[str], command: list[str]) -> int:
    if os.getenv("METTA_GAME_VERSION_ACTIVE") == "1":
        return -1
    commit = resolve_game_version(version)
    repo_root = get_repo_root()
    worktree_path = ensure_game_version_worktree(repo_root, version, commit)
    env = os.environ.copy()
    env["METTA_GAME_VERSION_ACTIVE"] = "1"
    env["METTA_GAME_VERSION_NAME"] = version
    env["METTA_GAME_VERSION_COMMIT"] = commit
    return subprocess.run([*command, *argv], cwd=str(worktree_path), env=env).returncode
