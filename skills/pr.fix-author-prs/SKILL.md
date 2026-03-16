---
name: pr.fix-author-prs
description:
  Use when you need to sweep every open PR for a specific author, process stacked branches in the right order, fix
  conflicts/CI/review feedback, verify remote state, and stop only when the author's PR queue is clean or explicitly
  blocked.
args: <author-login>
---

# Fix Author PRs

## Overview

Sweep every open PR authored by one GitHub user. This is an **orchestrator** skill: build a fresh status matrix first,
process only the PRs that actually need work, and loop until every PR is clean or blocked on a real human decision.

**Announce at start:** "Sweeping all open PRs for `<author>` and fixing conflicts, CI failures, and actionable review
feedback."

**Core principle:** Inventory -> stack order -> isolated branch fix -> push -> verify remote -> re-audit

## Common Request Language

- "sweep all of `<author>`'s PRs"
- "fix every open PR from `<author>`"
- "do a full review queue pass for `<author>`"
- "clean up `<author>`'s stacked PRs"

## Bundled Helper

Use the bundled status script instead of hand-assembling ad hoc `gh` commands:

```bash
python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py <author-login> --format table
```

It fetches, per PR:

- branch + base branch
- stack depth within the author's open PR set
- mergeability
- review decision
- actionable unresolved review thread count
- fresh check-run status from the current head SHA

Use `--format json` when you need machine-readable output. Use `--pr <number>` to re-audit one PR after fixing it.

## The Process

### Step 0: Prep

```bash
git status --short
gh auth status
gh repo view --json owner,name,defaultBranchRef
```

Rules:

- Do not trample unrelated local changes. If the current checkout is dirty, move the PR work into dedicated worktrees.
- Do not assume `main`. Always use each PR's actual `baseRefName`.
- Do not use `gh pr checks`. Fresh CI status must come from the PR head SHA.

### Step 1: Build The Status Matrix

```bash
AUTHOR="<author-login>"
python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py "$AUTHOR" --format table
```

Interpret the output as follows:

| Signal | Meaning | Action |
| ------ | ------- | ------ |
| `CONFLICTING` | branch cannot merge with its base | fix first |
| `failed_checks > 0` | CI is red on the current head SHA | fix before resolving comments |
| `actionable_threads > 0` | unresolved, non-outdated review threads exist | fix and verify |
| `review_decision == CHANGES_REQUESTED` | reviewer still expects a change even if thread count is zero | inspect with branch fixer |
| `pending_checks > 0` only | work may already be correct, but remote is still running | watch unless other signals exist |
| `is_draft` | author is not ready for review | report, usually skip |

**Stack order matters:** if one PR's `baseRefName` matches another PR's `headRefName`, treat them as a stack and work
from the lowest depth upward.

### Step 2: Prioritize Only The PRs That Need Intervention

Process PRs in this order:

1. lower stack depth before higher stack depth
2. conflicts
3. failing checks
4. actionable review threads or `CHANGES_REQUESTED`
5. pending checks with no other problems

Skip PRs that are already clean, but keep them in the final report.

Stop and ask the user only for real blockers:

- design disagreements or contradictory reviewer guidance
- PRs that require a product decision rather than an implementation fix
- branches you cannot safely restack or merge automatically

### Step 3: Choose The Per-PR Execution Path

For each PR that needs work, create or reuse a dedicated worktree for that branch and operate there.

**Preferred path:** run `/pr.fix-branch` from that PR branch whenever the branch follows the repo's normal Graphite
workflow. This is the default because it already handles:

- sync/restack
- comment fixing
- remote verification before thread resolution
- CI fixing
- submit/push

**Fallback path:** if `/pr.fix-branch` is clearly wrong for this PR, follow `references/direct-fallback.md`.
Use the fallback when:

- the branch is not in the normal Graphite flow
- you only need a manual merge against a non-standard base branch
- `gt` tooling is unavailable or inappropriate
- the PR needs targeted manual intervention rather than the full branch orchestration

### Step 4: Fix One PR End-To-End Before Moving On

For the chosen PR:

1. Checkout the PR branch in its worktree.
2. Sync it against its actual base branch.
3. Resolve merge conflicts first.
4. Fix actionable review feedback.
5. Fix CI failures from the current head SHA.
6. Push or submit the branch.
7. Verify the remote head actually contains the fix.
8. Only then reply to and resolve review threads.

Non-negotiables:

- Behavioral review feedback gets a regression test unless the case is already covered.
- Do not resolve or reply to review threads before the push is verified on the remote.
- Do not mark a PR clean based on stale local assumptions; always re-query GitHub.

### Step 5: Re-Audit The PR You Just Touched

Immediately after each branch update:

```bash
python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py "$AUTHOR" --pr <PR_NUMBER> --format table
```

Stay on the PR until all of the following are true or a real blocker is found:

- no merge conflicts
- no failed checks
- no actionable unresolved review threads
- no unhandled `CHANGES_REQUESTED` review decision

### Step 6: Re-Audit The Author's Full Queue

After each full pass, rerun the full inventory:

```bash
python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py "$AUTHOR" --format table
```

Stop only when every open PR is one of:

- `clean`
- `watch` (only pending checks remain)
- `blocked` with a concrete reason you can report

If new failures appear on PRs you already touched, loop again. This skill is done only when the author's queue is
stable, not when you've made one pass.

### Step 7: Final Report

Return a compact matrix covering every open PR:

| Field | What to report |
| ----- | -------------- |
| `pr` | number + title |
| `branch` | head branch name |
| `status` | clean, watch, blocked, or fixed-but-waiting |
| `issues_found` | conflicts, CI, comments, review decision |
| `actions_taken` | sync, tests, fixes, pushes, replies |
| `blocker` | only if human input is still needed |

Call out stack relationships explicitly when they mattered so the user can see why branches were processed in that
order.

## Quick Reference

| Need | Command |
| ---- | ------- |
| Full author inventory | `python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py <author> --format table` |
| Single PR re-audit | `python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py <author> --pr <number> --format table` |
| Preferred branch fixer | `/pr.fix-branch` |
| Manual fallback | `references/direct-fallback.md` |

## Integration

**Uses:** `pr.fix-branch`, `pr.fix-ci`, `pr.fix-comments`

**Pairs with:** `pr.check-ci`, `st.fix-stack`, `wt.cleanup`
