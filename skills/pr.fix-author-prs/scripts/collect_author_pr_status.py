#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass

FAILED_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "startup_failure",
    "timed_out",
}


def _run(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True)
    return result.stdout


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str
    default_branch: str


@dataclass(frozen=True)
class PullRequestRecord:
    number: int
    title: str
    url: str
    head_ref_name: str
    head_ref_oid: str
    base_ref_name: str
    is_draft: bool
    mergeable: str
    review_decision: str


@dataclass(frozen=True)
class PullRequestStatus:
    order: int
    stack_depth: int
    number: int
    title: str
    url: str
    head_ref_name: str
    base_ref_name: str
    is_draft: bool
    mergeable: str
    review_decision: str
    actionable_threads: int
    outdated_unresolved_threads: int
    failed_checks: int
    pending_checks: int
    failed_check_names: list[str]
    pending_check_names: list[str]
    state: str
    reasons: list[str]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a fresh status matrix for all open PRs authored by one user. "
            "Uses GitHub check-runs from each PR head SHA instead of gh pr checks."
        )
    )
    parser.add_argument("author", help="GitHub login or @me")
    parser.add_argument("--pr", type=int, help="Restrict output to one PR number")
    parser.add_argument("--limit", type=int, default=100, help="Maximum open PRs to inspect")
    parser.add_argument(
        "--format",
        choices=("json", "table"),
        default="table",
        help="Output format",
    )
    return parser.parse_args()


def _repo_ref() -> RepoRef:
    data = json.loads(_run(["gh", "repo", "view", "--json", "owner,name,defaultBranchRef"]))
    return RepoRef(
        owner=data["owner"]["login"],
        name=data["name"],
        default_branch=data["defaultBranchRef"]["name"],
    )


def _list_pull_requests(author: str, limit: int, pr_number: int | None) -> list[PullRequestRecord]:
    fields = ",".join(
        [
            "number",
            "title",
            "url",
            "headRefName",
            "headRefOid",
            "baseRefName",
            "isDraft",
            "mergeable",
            "reviewDecision",
        ]
    )
    payload = json.loads(
        _run(
            [
                "gh",
                "pr",
                "list",
                "--author",
                author,
                "--state",
                "open",
                "--limit",
                str(limit),
                "--json",
                fields,
            ]
        )
    )
    records = [
        PullRequestRecord(
            number=item["number"],
            title=item["title"],
            url=item["url"],
            head_ref_name=item["headRefName"],
            head_ref_oid=item["headRefOid"],
            base_ref_name=item["baseRefName"],
            is_draft=item["isDraft"],
            mergeable=item["mergeable"],
            review_decision=item["reviewDecision"] or "NONE",
        )
        for item in payload
    ]
    if pr_number is None:
        return records
    return [record for record in records if record.number == pr_number]


def _thread_counts(repo: RepoRef, pr_number: int) -> tuple[int, int]:
    actionable_threads = 0
    outdated_unresolved_threads = 0
    cursor: str | None = None
    while True:
        query = """
        query($owner:String!, $repo:String!, $pr:Int!, $after:String) {
          repository(owner:$owner, name:$repo) {
            pullRequest(number:$pr) {
              reviewThreads(first:100, after:$after) {
                nodes {
                  isResolved
                  isOutdated
                }
                pageInfo {
                  hasNextPage
                  endCursor
                }
              }
            }
          }
        }
        """
        args = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-f",
            f"owner={repo.owner}",
            "-f",
            f"repo={repo.name}",
            "-F",
            f"pr={pr_number}",
        ]
        if cursor is not None:
            args.extend(["-f", f"after={cursor}"])
        data = json.loads(_run(args))
        threads = data["data"]["repository"]["pullRequest"]["reviewThreads"]
        for thread in threads["nodes"]:
            if thread["isResolved"]:
                continue
            if thread["isOutdated"]:
                outdated_unresolved_threads += 1
                continue
            actionable_threads += 1
        if not threads["pageInfo"]["hasNextPage"]:
            return actionable_threads, outdated_unresolved_threads
        cursor = threads["pageInfo"]["endCursor"]


def _check_run_counts(repo: RepoRef, sha: str) -> tuple[int, int, list[str], list[str]]:
    failed_names: list[str] = []
    pending_names: list[str] = []
    page = 1
    while True:
        data = json.loads(
            _run(
                [
                    "gh",
                    "api",
                    f"repos/{repo.owner}/{repo.name}/commits/{sha}/check-runs?per_page=100&page={page}",
                ]
            )
        )
        checks = data["check_runs"]
        for check in checks:
            status = check["status"]
            conclusion = check["conclusion"]
            name = check["name"]
            if conclusion in FAILED_CONCLUSIONS:
                failed_names.append(name)
                continue
            if status != "completed":
                pending_names.append(name)
                continue
            if conclusion is None:
                pending_names.append(name)
        if len(checks) < 100:
            break
        page += 1
    return len(failed_names), len(pending_names), failed_names, pending_names


def _stack_depths(records: list[PullRequestRecord]) -> dict[int, int]:
    by_head = {record.head_ref_name: record for record in records}
    depths: dict[int, int] = {}
    for record in records:
        depth = 0
        current = record
        seen_heads = {record.head_ref_name}
        while True:
            parent = by_head.get(current.base_ref_name)
            if parent is None or parent.head_ref_name in seen_heads:
                depths[record.number] = depth
                break
            depth += 1
            current = parent
            seen_heads.add(current.head_ref_name)
    return depths


def _priority_key(status: PullRequestStatus) -> tuple[int, int, int, int, int, int, int]:
    state_priority = {
        "needs_attention": 0,
        "watch": 1,
        "clean": 2,
        "blocked": 3,
    }[status.state]
    conflict_priority = 0 if status.mergeable == "CONFLICTING" else 1
    failed_priority = 0 if status.failed_checks > 0 else 1
    thread_priority = 0 if status.actionable_threads > 0 or status.review_decision == "CHANGES_REQUESTED" else 1
    pending_priority = 0 if status.pending_checks > 0 else 1
    return (
        state_priority,
        status.stack_depth,
        conflict_priority,
        failed_priority,
        thread_priority,
        pending_priority,
        status.number,
    )


def _state(
    record: PullRequestRecord, actionable_threads: int, failed_checks: int, pending_checks: int
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if record.is_draft:
        reasons.append("draft")
    if record.mergeable == "CONFLICTING":
        reasons.append("conflicting")
    if failed_checks > 0:
        reasons.append("failing_checks")
    if actionable_threads > 0:
        reasons.append("actionable_threads")
    if record.review_decision == "CHANGES_REQUESTED":
        reasons.append("changes_requested")
    if pending_checks > 0:
        reasons.append("pending_checks")

    if record.is_draft:
        return "blocked", reasons
    if any(
        reason in reasons for reason in ("conflicting", "failing_checks", "actionable_threads", "changes_requested")
    ):
        return "needs_attention", reasons
    if pending_checks > 0:
        return "watch", reasons
    return "clean", reasons


def _collect_statuses(repo: RepoRef, records: list[PullRequestRecord]) -> list[PullRequestStatus]:
    depths = _stack_depths(records)
    statuses: list[PullRequestStatus] = []
    for record in records:
        actionable_threads, outdated_unresolved_threads = _thread_counts(repo, record.number)
        failed_checks, pending_checks, failed_names, pending_names = _check_run_counts(repo, record.head_ref_oid)
        state, reasons = _state(record, actionable_threads, failed_checks, pending_checks)
        statuses.append(
            PullRequestStatus(
                order=0,
                stack_depth=depths[record.number],
                number=record.number,
                title=record.title,
                url=record.url,
                head_ref_name=record.head_ref_name,
                base_ref_name=record.base_ref_name,
                is_draft=record.is_draft,
                mergeable=record.mergeable,
                review_decision=record.review_decision,
                actionable_threads=actionable_threads,
                outdated_unresolved_threads=outdated_unresolved_threads,
                failed_checks=failed_checks,
                pending_checks=pending_checks,
                failed_check_names=failed_names,
                pending_check_names=pending_names,
                state=state,
                reasons=reasons,
            )
        )

    ordered = sorted(statuses, key=_priority_key)
    return [PullRequestStatus(**{**asdict(status), "order": index}) for index, status in enumerate(ordered, start=1)]


def _table(statuses: list[PullRequestStatus]) -> str:
    if not statuses:
        return "No matching open PRs."

    headers = [
        "order",
        "pr",
        "state",
        "depth",
        "mergeable",
        "review",
        "threads",
        "fail",
        "pend",
        "branch",
        "base",
        "reasons",
    ]
    rows = [
        [
            str(status.order),
            str(status.number),
            status.state,
            str(status.stack_depth),
            status.mergeable,
            status.review_decision,
            str(status.actionable_threads),
            str(status.failed_checks),
            str(status.pending_checks),
            status.head_ref_name,
            status.base_ref_name,
            ",".join(status.reasons) or "-",
        ]
        for status in statuses
    ]
    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def format_row(row: list[str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    lines = [format_row(headers), format_row(["-" * width for width in widths])]
    lines.extend(format_row(row) for row in rows)
    return "\n".join(lines)


def main() -> None:
    args = _parse_args()
    repo = _repo_ref()
    records = _list_pull_requests(args.author, args.limit, args.pr)
    statuses = _collect_statuses(repo, records)
    if args.format == "json":
        print(json.dumps([asdict(status) for status in statuses], indent=2))
        return
    print(_table(statuses))


if __name__ == "__main__":
    main()
