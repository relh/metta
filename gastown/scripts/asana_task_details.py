from __future__ import annotations

import argparse
import datetime
import os
from pathlib import Path
from typing import Any

import asana as asana_sdk
import yaml
from asana_util import asana_client, extract_task_gid

OPT_FIELDS = (
    "gid,name,assignee.name,assignee.email,completed,completed_at,"
    "due_on,modified_at,permalink_url,notes,"
    "projects.name,projects.gid,"
    "memberships.project.name,memberships.project.gid,"
    "memberships.section.name,memberships.section.gid"
)


def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    assignee = task.get("assignee") or {}
    memberships = task.get("memberships") or []
    projects = task.get("projects") or []

    return {
        "gid": task.get("gid"),
        "name": task.get("name"),
        "url": task.get("permalink_url"),
        "completed": bool(task.get("completed")),
        "completed_at": task.get("completed_at"),
        "due_on": task.get("due_on"),
        "modified_at": task.get("modified_at"),
        "assignee": {
            "name": assignee.get("name"),
            "email": assignee.get("email"),
        }
        if assignee
        else None,
        "projects": [{"gid": project.get("gid"), "name": project.get("name")} for project in projects],
        "memberships": [
            {
                "project": {
                    "gid": (membership.get("project") or {}).get("gid"),
                    "name": (membership.get("project") or {}).get("name"),
                },
                "section": {
                    "gid": (membership.get("section") or {}).get("gid"),
                    "name": (membership.get("section") or {}).get("name"),
                },
            }
            for membership in memberships
        ],
        "notes": (task.get("notes") or "").strip(),
    }


def _format_notes(lines: list[str], indent: str, value: str) -> None:
    if not value:
        return
    note_lines = [line.rstrip() for line in value.splitlines() if line.strip()]
    if not note_lines:
        return
    for note in note_lines:
        lines.append(f"{indent}{note}")


def _write_md(path: Path, payload: dict[str, Any], generated_at: str) -> None:
    lines: list[str] = [
        f"# {payload.get('name') or 'Asana task'}",
        "",
        f"Asana: {payload.get('url') or 'unknown'}",
        f"Generated: {generated_at}",
        "",
    ]

    lines.append(f"- Status: {'completed' if payload.get('completed') else 'open'}")
    if payload.get("due_on"):
        lines.append(f"- Due: {payload['due_on']}")
    if payload.get("modified_at"):
        lines.append(f"- Modified: {payload['modified_at']}")

    assignee = payload.get("assignee") or {}
    if assignee.get("name"):
        lines.append(f"- Assignee: {assignee['name']}")

    projects = payload.get("projects") or []
    if projects:
        lines.append("- Projects:")
        for project in projects:
            label = project.get("name") or project.get("gid") or "unknown"
            lines.append(f"  - {label}")

    memberships = payload.get("memberships") or []
    if memberships:
        lines.append("- Memberships:")
        for membership in memberships:
            project = membership.get("project") or {}
            section = membership.get("section") or {}
            project_label = project.get("name") or project.get("gid") or "unknown"
            section_label = section.get("name") or section.get("gid") or "unknown"
            lines.append(f"  - {project_label} / {section_label}")

    lines.append("")
    lines.append("## Description")
    lines.append("")
    if payload.get("notes"):
        _format_notes(lines, "", payload["notes"])
    else:
        lines.append("(No description)")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a single Asana task and render details.")
    parser.add_argument("task", help="Task gid or URL")
    parser.add_argument("--out", default="", help="Output file path")
    parser.add_argument("--format", choices=["md", "yaml"], default="md")
    args = parser.parse_args()

    token = os.getenv("ASANA_TOKEN")
    if not token:
        raise RuntimeError("ASANA_TOKEN is required")

    task_gid = extract_task_gid(args.task)
    client = asana_client(token)
    tasks_api = asana_sdk.TasksApi(client)
    task = tasks_api.get_task(task_gid, {"opt_fields": OPT_FIELDS})

    generated_at = datetime.datetime.now(datetime.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = _normalize_task(task)
    payload["generated_at"] = generated_at

    if args.format == "yaml":
        output = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    else:
        output = None

    if args.out:
        out_path = Path(args.out)
        if args.format == "yaml":
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(output or "", encoding="utf-8")
        else:
            _write_md(out_path, payload, generated_at)
    else:
        if args.format == "yaml":
            print(output)
        else:
            temp_path = Path("/tmp/asana_task.md")
            _write_md(temp_path, payload, generated_at)
            print(temp_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
