#!/usr/bin/env python3
"""
Sync Asana tasks to beads for Gas Town integration.

Fetches tasks from Asana and outputs JSONL compatible with `bd import`.
Tasks are linked via external_ref so updates sync correctly.

Usage:
    # Preview what would be imported
    python asana_sync.py --dry-run

    # Import your assigned tasks
    python asana_sync.py | bd import

    # Import specific project tasks
    python asana_sync.py --scope ep3 | bd import

    # Full sync with deduplication
    python asana_sync.py | bd import --dedupe-after

Environment:
    ASANA_TOKEN         - Required: Asana personal access token
    ASANA_WORKSPACE_GID - Optional: Override workspace from config
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

import asana as asana_sdk
import yaml
from asana_util import asana_client

# Default config location (relative to script or absolute)
DEFAULT_CONFIG = Path(__file__).parent / "asana_config.yaml"

# Asana API fields to fetch
OPT_FIELDS = (
    "gid,name,assignee.name,assignee.email,completed,completed_at,"
    "due_on,modified_at,permalink_url,notes,html_notes,"
    "memberships.project.gid,memberships.project.name,"
    "memberships.section.gid,memberships.section.name"
)


def load_config(path: Path) -> dict[str, Any]:
    """Load YAML config file."""
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def resolve_user_gid(
    users_api: asana_sdk.UsersApi,
    workspace_gid: str,
    config: dict[str, Any],
) -> str:
    """Resolve user GID from config or environment."""
    user_cfg = config.get("asana", {}).get("user", {})
    user_gid = (user_cfg.get("gid") or "").strip()
    if user_gid:
        return user_gid

    email = (user_cfg.get("email") or os.getenv("ASANA_USER_EMAIL") or "").strip()
    if email:
        for user in users_api.get_users({"workspace": workspace_gid, "opt_fields": "name,email"}):
            if (user.get("email") or "").lower() == email.lower():
                return user["gid"]

    return "me"


def fetch_my_tasks(
    tasks_api: asana_sdk.TasksApi,
    assignee_gid: str,
    workspace_gid: str,
) -> list[dict[str, Any]]:
    """Fetch all incomplete tasks assigned to user."""
    params = {
        "assignee": assignee_gid,
        "workspace": workspace_gid,
        "completed_since": "now",  # Only incomplete tasks
        "opt_fields": OPT_FIELDS,
    }
    return list(tasks_api.get_tasks(params))


def fetch_project_tasks(
    tasks_api: asana_sdk.TasksApi,
    project_gid: str,
) -> list[dict[str, Any]]:
    """Fetch all incomplete tasks from a project."""
    params = {
        "completed_since": "now",
        "opt_fields": OPT_FIELDS,
    }
    return list(tasks_api.get_tasks_for_project(project_gid, params))


def asana_to_bead(
    task: dict[str, Any],
    prefix: str,
    project_gid: str | None = None,
) -> dict[str, Any]:
    """Convert Asana task to beads JSONL format."""
    gid = task.get("gid", "")
    name = task.get("name", "Untitled task")
    notes = (task.get("notes") or "").strip()
    url = task.get("permalink_url", "")
    due_on = task.get("due_on")
    completed = task.get("completed", False)
    assignee = task.get("assignee") or {}
    memberships = task.get("memberships") or []

    # Build description with Asana context
    desc_parts = []
    if notes:
        desc_parts.append(notes)
    desc_parts.append("")
    desc_parts.append(f"Asana: {url}")
    if assignee.get("name"):
        desc_parts.append(f"Assignee: {assignee['name']}")

    # Extract section/project for labels
    labels = ["asana"]
    section_name = None
    project_name = None

    for membership in memberships:
        project = membership.get("project") or {}
        section = membership.get("section") or {}

        if project_gid and project.get("gid") == project_gid:
            section_name = section.get("name")
            project_name = project.get("name")
        elif not project_gid:
            # Use first membership if no specific project
            if not section_name:
                section_name = section.get("name")
            if not project_name:
                project_name = project.get("name")

    if project_name:
        # Slugify project name for label
        slug = project_name.lower().replace(" ", "-").replace("+", "")[:20]
        labels.append(f"project:{slug}")
    if section_name:
        slug = section_name.lower().replace(" ", "-")[:20]
        labels.append(f"section:{slug}")

    # Map status
    status = "closed" if completed else "open"

    # Build bead
    bead = {
        "id": f"{prefix}-asana-{gid}",
        "title": name,
        "description": "\n".join(desc_parts),
        "status": status,
        "priority": 2,  # Default P2
        "issue_type": "task",
        "external_ref": f"asana:{gid}",
        "labels": labels,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        "updated_at": task.get("modified_at") or datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
    }

    if due_on:
        bead["due_date"] = due_on

    if assignee.get("email"):
        bead["owner"] = assignee["email"]

    return bead


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Asana tasks to beads format for Gas Town.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scope",
        choices=["my", "projects", "all"],
        default="my",
        help="What to sync: my tasks, configured projects, or all (default: my)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"Config file path (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--prefix",
        default="mt",
        help="Beads prefix for imported tasks (default: mt)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be imported without outputting JSONL",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON array instead of JSONL",
    )
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Get token
    token = os.getenv("ASANA_TOKEN")
    if not token:
        print("Error: ASANA_TOKEN environment variable required", file=sys.stderr)
        sys.exit(1)

    # Get workspace
    workspace_gid = (os.getenv("ASANA_WORKSPACE_GID") or config.get("asana", {}).get("workspace_gid") or "").strip()
    if not workspace_gid:
        print("Error: Workspace GID required (ASANA_WORKSPACE_GID or config)", file=sys.stderr)
        sys.exit(1)

    # Initialize API clients
    client = asana_client(token)
    users_api = asana_sdk.UsersApi(client)
    tasks_api = asana_sdk.TasksApi(client)

    beads: list[dict[str, Any]] = []

    # Fetch tasks based on scope
    if args.scope in ("my", "all"):
        user_gid = resolve_user_gid(users_api, workspace_gid, config)
        tasks = fetch_my_tasks(tasks_api, user_gid, workspace_gid)
        for task in tasks:
            beads.append(asana_to_bead(task, args.prefix))

    if args.scope in ("projects", "all"):
        projects = config.get("asana", {}).get("projects", [])
        for project in projects:
            project_gid = (project.get("gid") or "").strip()
            if not project_gid:
                continue
            tasks = fetch_project_tasks(tasks_api, project_gid)
            for task in tasks:
                beads.append(asana_to_bead(task, args.prefix, project_gid=project_gid))

    # Deduplicate by ID
    seen = set()
    unique_beads = []
    for bead in beads:
        if bead["id"] not in seen:
            seen.add(bead["id"])
            unique_beads.append(bead)

    # Output
    if args.dry_run:
        print(f"Would import {len(unique_beads)} tasks:", file=sys.stderr)
        for bead in unique_beads:
            status = bead["status"]
            labels = ", ".join(bead.get("labels", []))
            print(f"  [{status}] {bead['id']}: {bead['title']}", file=sys.stderr)
            if labels:
                print(f"         labels: {labels}", file=sys.stderr)
        return

    if args.json:
        print(json.dumps(unique_beads, indent=2))
    else:
        for bead in unique_beads:
            print(json.dumps(bead))


if __name__ == "__main__":
    main()
