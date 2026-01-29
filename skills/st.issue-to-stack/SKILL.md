---
name: st.issue-to-stack
description:
  Use when a user reports an issue to fix and you want to do all work in one new branch + worktree first, then split the
  result into a Graphite PR stack at the end.
---

# Issue To Stack

## Overview

Implement a fix end-to-end in a single new **worktree + WIP branch**, using clean, incremental commits. Once the fix is
verified, split those commits into a Graphite stack so each PR stays reviewable.

**Announce at start:** "I’m using the issue-to-stack skill: I’ll fix everything on one WIP branch in a new worktree,
then split it into a Graphite stack with st.graphite-stack."

## Step 1: Create a WIP Worktree + Branch

Pick a short slug for the issue (e.g. `legacy-nim-agents`).

```bash
git fetch origin

SLUG="legacy-nim-agents"
WIP_BRANCH="subho/${SLUG}-wip"
WORKTREE="../metta.${USER}.${SLUG}-wip"

git worktree add -b "$WIP_BRANCH" "$WORKTREE" origin/main
cd "$WORKTREE"
```

## Step 2: Reproduce the Issue

- Run the exact command(s) the user provided.
- Capture the full error/traceback and identify the import path / config / checkpoint causing the failure.

If the reproduction is slow or flaky, minimize it (one command, one test, or one import) before coding.

## Step 3: Implement the Fix as Stack-Friendly Commits (Still on WIP)

Stay on the same WIP branch, but make **one commit per logical PR**:

- Commit 1: the minimal compatibility shim / core fix
- Commit 2: follow-up feature/tooling (if needed)
- Commit 3: tests/docs/lint cleanup

Loop per commit:

```bash
# Make changes...
git status --short
metta lint --fix <touched paths>
metta pytest --changed
git add -A
git commit -m "fix: <small, reviewable change>"
```

## Step 4: Verify the Whole WIP Branch

Before splitting:

```bash
metta lint
metta pytest
```

## Step 5: Split WIP into a Graphite Stack

Use `st.graphite-stack` to decide boundaries and PR titles/descriptions.

```bash
git log --oneline origin/main..HEAD
```

If the commits already match the intended stack, create a branch per commit by cherry-picking in order:

```bash
# Example: split 3 commits from the WIP branch
COMMITS=(<sha1> <sha2> <sha3>) # oldest -> newest
BRANCHES=("subho/${SLUG}-shim" "subho/${SLUG}-tooling" "subho/${SLUG}-tests")

git checkout origin/main
gt create "${BRANCHES[0]}" -m "fix: <PR 1 title>"
git cherry-pick "${COMMITS[0]}"
/pr.submit

gt create "${BRANCHES[1]}" -m "feat: <PR 2 title>"
git cherry-pick "${COMMITS[1]}"
/pr.submit

gt create "${BRANCHES[2]}" -m "test: <PR 3 title>"
git cherry-pick "${COMMITS[2]}"
/pr.submit

gt submit --stack --no-interactive
gt log short
```

## Step 6: Hand Off

Report:

- Stack order (`gt log short`)
- Graphite PR URLs
- The original WIP branch name (keep it until the stack is merged)

## Quick Reference

| Task                | Command                                        |
| ------------------- | ---------------------------------------------- |
| Create WIP worktree | `git worktree add -b <wip> <path> origin/main` |
| See WIP commits     | `git log --oneline origin/main..HEAD`          |
| Split to stack      | `gt create` + `git cherry-pick`                |
| Submit each PR      | `/pr.submit`                                   |
| Submit whole stack  | `gt submit --stack --no-interactive`           |

## Integration

**Uses:** `st.graphite-stack`, `pr.submit`, `cb.lint-fix`, `t.run-tests`, `db.run-and-triage`  
**Pairs with:** `st.make-stack` (when commits aren’t clean), `st.split` (to split an already-submitted branch)
