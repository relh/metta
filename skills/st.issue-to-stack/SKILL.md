---
name: st.issue-to-stack
description:
  Use when a user reports an issue to fix and you want to do all work in one new branch + worktree first, then split the
  result into a Graphite PR stack at the end.
---

# Issue To Stack

## Overview

Implement a fix end-to-end in a single new **worktree + WIP branch**, using clean, incremental commits. Once the fix is
verified, decide whether it should ship as a **single PR** (preferred when the change is coherent) or be split into a
Graphite stack (only when necessary to keep review manageable).

**Announce at start:** "I’m using the issue-to-stack skill: I’ll fix everything on one WIP branch in a new worktree,
then submit as a single PR or split into a Graphite stack if needed."

## Step 1: Create a WIP Worktree + Branch

Pick a short slug for the issue (e.g. `legacy-nim-agents`).

```bash
git fetch origin

SLUG="legacy-nim-agents"
WIP_BRANCH="${USER}/${SLUG}-wip"
WORKTREE="../metta.${USER}.${SLUG}-wip"

git worktree add -b "$WIP_BRANCH" "$WORKTREE" origin/main
cd "$WORKTREE"
```

## Step 2: Reproduce the Issue

- Run the exact command(s) the user provided.
- Capture the full error/traceback and identify the import path / config / checkpoint causing the failure.

If the reproduction is slow or flaky, minimize it (one command, one test, or one import) before coding.

## Step 3: Implement the Fix as Stack-Friendly Commits (Still on WIP)

Stay on the same WIP branch. Prefer **one commit** when the change is clean and reviewable as a single PR; otherwise
make **one commit per logical PR**:

- Commit 1: the minimal compatibility shim / core fix (include any tests that validate this fix)
- Commit 2: follow-up feature/tooling (if needed; include its tests/docs with it)

Loop per commit:

```bash
# Make changes...
git status --short
```

```
# Run lint (ensures prettier available)
Use Skill tool: skill="cb.lint-fix"
```

```bash
metta pytest --changed
git add -A
git commit -m "fix: <small, reviewable change>"
```

**Testing guidance:** Add tests when they materially increase confidence or prevent regressions; don’t add tests “just
because”. If you do add tests, keep them in the **same PR/commit** as the change they validate (avoid standalone “tests
only” PRs unless the tests are genuinely independent).

## Step 4: Verify the Whole WIP Branch

Before splitting:

```
# Run lint (ensures prettier available)
Use Skill tool: skill="cb.lint-fix"
```

```bash
metta pytest
```

## Step 5: Submit (Single PR) or Split (Stack)

### Option A: Single PR (preferred when possible)

If the diff is coherent and reviewable as one PR, submit the WIP branch directly:

```bash
/pr.submit
```

### Option B: Graphite stack (only when necessary)

If the change is too large or has clearly separable pieces, use `st.graphite-stack` to decide boundaries and PR
titles/descriptions.

```bash
git log --oneline origin/main..HEAD
```

If the commits already match the intended stack, create a branch per commit by cherry-picking in order:

```bash
# Example: split 3 commits from the WIP branch
COMMITS=(<sha1> <sha2> <sha3>) # oldest -> newest
BRANCHES=("${USER}/${SLUG}-shim" "${USER}/${SLUG}-tooling" "${USER}/${SLUG}-tests")

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

## Step 7: Worktree Cleanup

After the stack is submitted (or single PR merged), invoke `/wt.cleanup` to remove the worktree and return to the main
repo.

## Quick Reference

| Task                | Command                                        |
| ------------------- | ---------------------------------------------- |
| Create WIP worktree | `git worktree add -b <wip> <path> origin/main` |
| See WIP commits     | `git log --oneline origin/main..HEAD`          |
| Split to stack      | `gt create` + `git cherry-pick`                |
| Submit each PR      | `/pr.submit`                                   |
| Submit whole stack  | `gt submit --stack --no-interactive`           |

## Integration

**Uses:** `st.graphite-stack`, `pr.submit`, `cb.lint-fix`, `t.run-tests`, `db.run-and-triage`, `wt.cleanup`  
**Pairs with:** `st.make-stack` (when commits aren’t clean), `st.split` (to split an already-submitted branch)
