from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Iterable

from asana_util import asana_client, extract_task_gid

ASANA_URL_RE = re.compile(r"https?://app\.asana\.com/\S+", re.IGNORECASE)
ASANA_INLINE_GID_RE = re.compile(r"asana[^0-9]{0,20}(\d{12,})", re.IGNORECASE)


@dataclass
class PrRecord:
    number: int
    title: str
    url: str
    is_draft: bool
    author: str
    task_gids: list[str]


def _run_gh_pr_list(state: str, limit: int) -> list[dict[str, Any]]:
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,body,url,headRefName,isDraft,author",
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout or "[]")
    if not isinstance(payload, list):
        raise RuntimeError("Unexpected gh output; expected JSON list")
    return payload


def _extract_task_gids(text: str) -> list[str]:
    gids: set[str] = set()
    for match in ASANA_URL_RE.findall(text):
        url = match.rstrip(").,;]}>\"'\n\t")
        try:
            gids.add(extract_task_gid(url))
        except ValueError:
            continue
    for match in ASANA_INLINE_GID_RE.findall(text):
        gids.add(match)
    return sorted(gids)


def _build_pr_records(prs: Iterable[dict[str, Any]]) -> list[PrRecord]:
    records: list[PrRecord] = []
    for pr in prs:
        title = pr.get("title") or ""
        body = pr.get("body") or ""
        author = (pr.get("author") or {}).get("login") or "unknown"
        task_gids = _extract_task_gids(f"{title}\n{body}")
        records.append(
            PrRecord(
                number=int(pr.get("number")),
                title=title,
                url=pr.get("url") or "",
                is_draft=bool(pr.get("isDraft")),
                author=author,
                task_gids=task_gids,
            )
        )
    return records


def _has_pr_comment(stories_api: Any, task_gid: str, pr_url: str) -> bool:
    params = {"opt_fields": "text"}
    for story in stories_api.get_stories_for_task(task_gid, params):
        text = (story.get("text") or "").strip()
        if pr_url in text:
            return True
    return False


def _comment_on_task(stories_api: Any, task_gid: str, pr_url: str) -> None:
    stories_api.create_story_for_task({"data": {"text": f"PR: {pr_url}"}}, task_gid, {})


def _print_report(records: list[PrRecord]) -> None:
    missing = [record for record in records if not record.task_gids]
    linked = [record for record in records if record.task_gids]

    print("PRs with Asana references:")
    for record in linked:
        gids = ", ".join(record.task_gids)
        draft = "draft" if record.is_draft else "open"
        print(f"- #{record.number} ({draft}) {record.title} [{gids}]")

    print("")
    print("PRs missing Asana references:")
    if not missing:
        print("- None")
        return
    for record in missing:
        draft = "draft" if record.is_draft else "open"
        print(f"- #{record.number} ({draft}) {record.title} [{record.author}]")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit open PRs for Asana references and optionally comment on tasks with PR links.",
    )
    parser.add_argument("--state", default="open", choices=["open", "closed", "all"])
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--author",
        action="append",
        default=[],
        help="Filter by GitHub author login (repeatable).",
    )
    parser.add_argument("--apply", action="store_true", help="Add PR link comments to Asana tasks.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate Asana comments without posting.")
    args = parser.parse_args()

    try:
        prs = _run_gh_pr_list(args.state, args.limit)
    except subprocess.CalledProcessError as exc:
        print(exc.stderr or exc.stdout or str(exc), file=sys.stderr)
        sys.exit(1)

    records = _build_pr_records(prs)
    if args.author:
        wanted = {author.lower() for author in args.author if author.strip()}
        records = [record for record in records if record.author.lower() in wanted]
    _print_report(records)

    if not args.apply:
        return

    token = os.getenv("ASANA_TOKEN")
    if not token:
        raise RuntimeError("ASANA_TOKEN is required to post comments")

    import asana as asana_sdk  # noqa: PLC0415

    client = asana_client(token)
    stories_api = asana_sdk.StoriesApi(client)

    for record in records:
        if not record.task_gids:
            continue
        for task_gid in record.task_gids:
            if _has_pr_comment(stories_api, task_gid, record.url):
                print(f"- Asana {task_gid}: already has PR link for {record.url}")
                continue
            if args.dry_run:
                print(f"- Asana {task_gid}: would add PR link for {record.url}")
                continue
            _comment_on_task(stories_api, task_gid, record.url)
            print(f"- Asana {task_gid}: added PR link for {record.url}")


if __name__ == "__main__":
    main()
