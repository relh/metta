#!/usr/bin/env python3
"""
Sync a child repository from monorepo with preserved git history.

This script filters the git history to only include the package directory,
then pushes both the main branch and package-specific tags (matching pattern
<package>-*) to the child repository.

Usage:
    uv run devops/git/push_child_repo.py <repo>
    uv run devops/git/push_child_repo.py <repo> --dry-run
    uv run devops/git/push_child_repo.py <repo> --yes  # Skip confirmations
    uv run devops/git/push_child_repo.py <repo> --target-branch test  # Push to test branch

Assumes any repo to publish is in packages/<repo>.
"""

import argparse
import sys
from pathlib import Path

import tomlkit

import gitta as git
from metta.common.util.constants import METTA_GITHUB_ORGANIZATION

# Packages synced to public repos; workspace deps are replaced with git sources
PUBLIC_PACKAGES = {"mettagrid", "cogames"}


def get_remote_url(package_name: str, *, use_https: bool = False) -> str:
    if use_https:
        return f"https://github.com/{METTA_GITHUB_ORGANIZATION}/{package_name}.git"
    return f"git@github.com:{METTA_GITHUB_ORGANIZATION}/{package_name}.git"


def transform_pyproject_for_external(filtered_path: Path) -> bool:
    """Replace workspace deps with git sources. Raises ValueError for unknown deps."""
    pyproject_path = filtered_path / "pyproject.toml"
    if not pyproject_path.exists():
        return False

    content = pyproject_path.read_text()
    doc = tomlkit.parse(content)

    sources = doc.get("tool", {}).get("uv", {}).get("sources", {})
    if not sources:
        return False

    workspace_deps = [name for name, config in sources.items() if isinstance(config, dict) and config.get("workspace")]
    if not workspace_deps:
        return False

    unknown_deps = set(workspace_deps) - PUBLIC_PACKAGES
    if unknown_deps:
        raise ValueError(
            f"Unknown workspace dependencies: {unknown_deps}. Add them to PUBLIC_PACKAGES if they should be synced."
        )

    for dep_name in workspace_deps:
        sources[dep_name] = tomlkit.inline_table()
        sources[dep_name]["git"] = get_remote_url(dep_name, use_https=True)

    pyproject_path.write_text(tomlkit.dumps(doc))
    git.run_git_in_dir(filtered_path, "add", "pyproject.toml")
    git.run_git_in_dir(
        filtered_path,
        "commit",
        "--amend",
        "--no-edit",
    )
    return True


def sync_repo(package_name: str, dry_run: bool = False, skip_confirmation: bool = False, target_branch: str = "main"):
    """Filter and push repository subset to configured remote."""

    # Assume all packages are in packages/<repo_name>
    package_path = f"packages/{package_name}"
    paths = [package_path + "/"]

    remote_url = get_remote_url(package_name)

    print(f"Syncing: {package_name}")
    print(f"Paths: {', '.join(paths)}")
    print(f"Target: {remote_url}")

    # Step 1: Filter
    print("\nFiltering repository...")
    try:
        # Filter to package path and make it the repository root
        filtered_path = git.filter_repo(Path.cwd(), paths, make_root=package_path + "/")
    except Exception as e:
        print(f"Filter failed: {e}")
        sys.exit(1)

    # Step 2: Transform pyproject.toml for external use
    if transform_pyproject_for_external(filtered_path):
        print("Transformed pyproject.toml: replaced workspace sources with external sources")

    # Step 3: Show what we got
    files = git.get_file_list(filtered_path)
    commits = git.get_commit_count(filtered_path)
    print(f"Result: {len(files)} files, {commits} commits")

    # Step 4: Safety checks before push
    try:
        current_origin = git.run_git("remote", "get-url", "origin").strip()
        if current_origin and remote_url.rstrip("/").rstrip(".git") == current_origin.rstrip("/").rstrip(".git"):
            print("\n*** SAFETY STOP ***")
            print("Target remote matches current origin!")
            print("This would destroy the main repository.")
            sys.exit(1)
    except Exception:
        pass  # No origin is fine

    # Step 5: Find package-specific tags
    tag_pattern = f"{package_name}-*"
    try:
        matching_tags = git.run_git_in_dir(filtered_path, "tag", "--list", tag_pattern).strip().splitlines()
        matching_tags = [tag.strip() for tag in matching_tags if tag.strip()]
    except Exception as e:
        print(f"Warning: Failed to list tags: {e}")
        matching_tags = []

    if matching_tags:
        print(f"\nFound {len(matching_tags)} matching tags: {', '.join(matching_tags[:5])}")
        if len(matching_tags) > 5:
            print(f"  ... and {len(matching_tags) - 5} more")
    else:
        print(f"\nNo tags matching pattern '{tag_pattern}' found")

    # Step 6: Push (with confirmations)
    print(f"\n{'DRY RUN: ' if dry_run else ''}Push to {remote_url} (branch: {target_branch})")

    if not dry_run and not skip_confirmation:
        print("\nThis will FORCE PUSH and replace the target repository!")
        print("Type the target URL to confirm:")
        if input("> ").strip() != remote_url:
            print("Aborted - URLs don't match")
            sys.exit(1)

        if input("Final confirmation [y/N]: ").lower() != "y":
            print("Aborted")
            sys.exit(1)

    # Step 7: Do the push
    try:
        git.add_remote("production", remote_url, filtered_path)

        # Push main branch
        push_cmd = ["push", "--force", "production", f"HEAD:{target_branch}"]
        if dry_run:
            push_cmd.insert(2, "--dry-run")

        print(f"\nPushing to {target_branch} branch...")
        output = git.run_git_in_dir(filtered_path, *push_cmd)
        if output:
            print(output)

        # Push package-specific tags
        if matching_tags:
            tag_push_cmd = ["push", "--force", "production"] + matching_tags
            if dry_run:
                tag_push_cmd.insert(2, "--dry-run")

            print(f"\nPushing {len(matching_tags)} package-specific tags...")
            output = git.run_git_in_dir(filtered_path, *tag_push_cmd)
            if output:
                print(output)

        print(f"\n{'Dry run' if dry_run else 'Push'} completed!")
        print(f"Filtered repo at: {filtered_path}")

    except Exception as e:
        print(f"Push failed: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("package", help="Package name (will sync packages/<package>)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be pushed")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--target-branch", default="main", help="Target branch in child repo (default: main)")

    args = parser.parse_args()

    try:
        sync_repo(args.package, args.dry_run, args.yes, args.target_branch)
    except KeyboardInterrupt:
        print("\nAborted")
        sys.exit(1)


if __name__ == "__main__":
    main()
