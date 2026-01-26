#!/usr/bin/env python3
"""
Sync Codex/Graphite PR review comments to beads.

Monitors open PRs for review comments from code review bots and creates
beads for actionable feedback that needs to be addressed.

Usage:
    # Preview what would be created
    python codex_review_sync.py --dry-run

    # Create beads for review comments
    python codex_review_sync.py

    # Filter by PR author
    python codex_review_sync.py --author relh
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass

# Bots whose comments we track
REVIEW_BOTS = [
    "chatgpt-codex-connector[bot]",
    "codex[bot]",
    "graphite-app[bot]",
]

# Priority badge patterns in comments
PRIORITY_PATTERN = re.compile(r"!\[P([0-4])", re.IGNORECASE)


@dataclass
class ReviewComment:
    pr_number: int
    pr_title: str
    pr_url: str
    comment_id: int
    comment_url: str
    file_path: str
    line: int | None
    body: str
    author: str
    priority: int  # 0-4, lower is higher priority


def run_gh(args: list[str]) -> str:
    """Run gh CLI command and return output."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def get_open_prs(author: str | None, state: str, limit: int) -> list[dict]:
    """Get list of PRs."""
    cmd = ["pr", "list", "--state", state, "--limit", str(limit), "--json", "number,title,url,author"]
    if author:
        cmd.extend(["--author", author])
    output = run_gh(cmd)
    return json.loads(output) if output else []


def get_pr_review_comments(pr_number: int) -> list[dict]:
    """Get inline review comments for a PR."""
    output = run_gh(["api", f"repos/:owner/:repo/pulls/{pr_number}/comments"])
    return json.loads(output) if output else []


def extract_priority(body: str) -> int:
    """Extract priority from comment body (P0-P4 badges). Default P2."""
    match = PRIORITY_PATTERN.search(body)
    if match:
        return int(match.group(1))
    return 2  # Default priority


def is_actionable(body: str) -> bool:
    """Check if comment is actionable (not just informational)."""
    # Skip pure info comments
    info_patterns = [
        r"About Codex in GitHub",
        r"Codex Review\s*$",
        r"Reviews are triggered when",
    ]
    for pattern in info_patterns:
        if re.search(pattern, body, re.IGNORECASE):
            return False
    # Must have some substance
    return len(body.strip()) > 50


def scan_prs_for_comments(
    author: str | None,
    state: str,
    limit: int,
    exclude_prs: set[int] | None = None,
) -> list[ReviewComment]:
    """Scan PRs for review bot comments."""
    comments: list[ReviewComment] = []
    prs = get_open_prs(author, state, limit)
    exclude_prs = exclude_prs or set()

    for pr in prs:
        pr_number = pr["number"]
        if pr_number in exclude_prs:
            continue
        pr_title = pr["title"]
        pr_url = pr["url"]

        try:
            review_comments = get_pr_review_comments(pr_number)
        except subprocess.CalledProcessError:
            continue

        for comment in review_comments:
            comment_author = comment.get("user", {}).get("login", "")
            if comment_author not in REVIEW_BOTS:
                continue

            body = comment.get("body", "")
            if not is_actionable(body):
                continue

            comments.append(
                ReviewComment(
                    pr_number=pr_number,
                    pr_title=pr_title,
                    pr_url=pr_url,
                    comment_id=comment.get("id", 0),
                    comment_url=comment.get("html_url", ""),
                    file_path=comment.get("path", ""),
                    line=comment.get("line"),
                    body=body,
                    author=comment_author,
                    priority=extract_priority(body),
                )
            )

    return comments


def create_bead(comment: ReviewComment, dry_run: bool) -> str | None:
    """Create a bead for the review comment."""
    # Extract first line as title (often has the suggestion summary)
    first_line = comment.body.split("\n")[0][:100]
    # Clean up markdown
    title = re.sub(r"\*\*|!\[.*?\]\(.*?\)|<.*?>", "", first_line).strip()
    if not title or len(title) < 10:
        title = f"Address Codex review on {comment.file_path}"

    description = f"""Codex review comment on PR #{comment.pr_number}

**File:** {comment.file_path}:{comment.line or "N/A"}
**PR:** {comment.pr_url}
**Comment:** {comment.comment_url}

## Review Comment

{comment.body}
"""

    if dry_run:
        print(f"  Would create: P{comment.priority} - {title[:60]}...")
        return None

    try:
        result = subprocess.run(
            [
                "bd",
                "create",
                title,
                "--description",
                description,
                "--labels",
                "codex-review,bug",
                "--priority",
                str(comment.priority),
                "--external-ref",
                f"gh-comment:{comment.comment_id}",
                "--silent",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        bead_id = result.stdout.strip()
        print(f"  Created: {bead_id} - {title[:50]}...")
        return bead_id
    except subprocess.CalledProcessError as e:
        # Check if already exists (duplicate external_ref)
        if "duplicate" in e.stderr.lower() or "exists" in e.stderr.lower():
            print(f"  Skipped (already exists): {title[:50]}...")
        else:
            print(f"  Error: {e.stderr}", file=sys.stderr)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Codex/Graphite PR review comments to beads.",
    )
    parser.add_argument("--author", help="Filter PRs by GitHub author")
    parser.add_argument("--state", default="open", choices=["open", "closed", "all"])
    parser.add_argument("--limit", type=int, default=50, help="Max PRs to check")
    parser.add_argument(
        "--exclude-pr",
        type=int,
        action="append",
        default=[],
        help="PR numbers to exclude (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without creating beads")
    args = parser.parse_args()

    exclude_prs = set(args.exclude_pr) if args.exclude_pr else set()
    print(f"Scanning {args.state} PRs for review comments...")
    if exclude_prs:
        print(f"Excluding PRs: {sorted(exclude_prs)}")
    comments = scan_prs_for_comments(args.author, args.state, args.limit, exclude_prs)

    if not comments:
        print("No actionable review comments found.")
        return

    print(f"Found {len(comments)} actionable review comment(s):")
    for comment in sorted(comments, key=lambda c: c.priority):
        create_bead(comment, args.dry_run)


if __name__ == "__main__":
    main()
