#!/usr/bin/env python3
"""Bump cortexcore version metadata in packages/cortex and uv.lock."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_version(version: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not m:
        raise ValueError(f"Invalid semver '{version}'. Expected X.Y.Z")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_version(version: str, bump: str) -> str:
    major, minor, patch = parse_version(version)
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "major":
        return f"{major + 1}.0.0"
    raise ValueError(f"Unsupported bump type: {bump}")


def read_pyproject_version(pyproject: Path) -> str:
    text = pyproject.read_text()
    m = re.search(r'(?m)^version = "(\d+\.\d+\.\d+)"$', text)
    if not m:
        raise RuntimeError(f"Could not find version in {pyproject}")
    return m.group(1)


def update_pyproject(pyproject: Path, new_version: str) -> str:
    text = pyproject.read_text()
    m = re.search(r'(?m)^version = "(\d+\.\d+\.\d+)"$', text)
    if not m:
        raise RuntimeError(f"Could not find version in {pyproject}")
    old_version = m.group(1)
    updated = text[: m.start(1)] + new_version + text[m.end(1) :]
    pyproject.write_text(updated)
    return old_version


def update_uv_lock(uv_lock: Path, old_version: str, new_version: str) -> None:
    text = uv_lock.read_text()
    pattern = r'(\[\[package\]\]\nname = "cortexcore"\nversion = ")(\d+\.\d+\.\d+)(")'
    m = re.search(pattern, text)
    if not m:
        raise RuntimeError("Could not locate cortexcore package block in uv.lock")
    found = m.group(2)
    if found != old_version:
        raise RuntimeError(f"uv.lock cortexcore version ({found}) does not match pyproject old version ({old_version})")
    updated = text[: m.start(2)] + new_version + text[m.end(2) :]
    uv_lock.write_text(updated)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump cortexcore version metadata")
    default_repo = Path(__file__).resolve().parents[1]
    parser.add_argument("--repo", type=Path, default=default_repo)
    parser.add_argument("--version", help="Exact target version (X.Y.Z)")
    parser.add_argument("--bump", choices=["patch", "minor", "major"], default="patch")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without modifying files")
    args = parser.parse_args()

    repo = args.repo.resolve()
    pyproject = repo / "packages/cortex/pyproject.toml"
    uv_lock = repo / "uv.lock"

    if not pyproject.exists() or not uv_lock.exists():
        raise RuntimeError(f"Expected metta repo layout under {repo}")

    old_version = read_pyproject_version(pyproject)
    new_version = args.version if args.version else bump_version(old_version, args.bump)
    parse_version(new_version)

    if args.dry_run:
        print(f"Dry run: would update cortexcore version {old_version} -> {new_version}")
        return 0

    update_pyproject(pyproject, new_version)
    update_uv_lock(uv_lock, old_version=old_version, new_version=new_version)
    print(f"Updated cortexcore version: {old_version} -> {new_version}")
    print(f"Modified: {pyproject}")
    print(f"Modified: {uv_lock}")
    print("Next: commit/push a PR and merge to main before publishing.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        sys.stderr.write(f"ERROR: {exc}\n")
        raise SystemExit(1) from exc
