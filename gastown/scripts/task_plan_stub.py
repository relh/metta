from __future__ import annotations

import argparse
import datetime
import os
import re
from pathlib import Path
from typing import Any

import asana as asana_sdk
from asana_util import asana_client, extract_task_gid

DEFAULT_TEMPLATE = "gastown/scripts/plan_template.md"
DEFAULT_OUTPUT_DIR = Path("gastown/generated/plans")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"


def _fetch_task(task_gid: str, token: str) -> dict[str, Any]:
    client = asana_client(token)
    tasks_api = asana_sdk.TasksApi(client)
    task = tasks_api.get_task(
        task_gid,
        {"opt_fields": "gid,name,permalink_url,notes"},
    )
    return {
        "gid": task.get("gid"),
        "name": task.get("name"),
        "url": task.get("permalink_url"),
        "notes": (task.get("notes") or "").strip(),
    }


def _render_template(template: str, data: dict[str, str]) -> str:
    output = template
    for key, value in data.items():
        output = output.replace(key, value)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a plan stub from an Asana task.")
    parser.add_argument("task", help="Task gid or URL")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--out", default="", help="Output plan path")
    args = parser.parse_args()

    token = os.getenv("ASANA_TOKEN")
    if not token:
        raise RuntimeError("ASANA_TOKEN is required")

    task_gid = extract_task_gid(args.task)
    task = _fetch_task(task_gid, token)
    today = datetime.date.today().isoformat()
    slug = _slugify(task.get("name") or "task")
    out_path = Path(args.out) if args.out else DEFAULT_OUTPUT_DIR / f"{today}-{slug}.md"

    template_path = Path(args.template)
    template_text = template_path.read_text(encoding="utf-8")

    notes = task.get("notes") or "(No description)"
    rendered = _render_template(
        template_text,
        {
            "__TASK_NAME__": task.get("name") or "Untitled task",
            "__TASK_GID__": task.get("gid") or task_gid,
            "__TASK_URL__": task.get("url") or "",
            "__DATE__": today,
            "__TASK_NOTES__": notes,
        },
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
