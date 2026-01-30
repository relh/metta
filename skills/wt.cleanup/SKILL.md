---
name: wt.cleanup
description:
  Use when you are done working in a git worktree and need to remove it. Called as the final step of any skill that
  creates a worktree.
---

# Worktree Cleanup

## Overview

Remove the current git worktree and return to the main repo directory. Safe to call even if not in a worktree.

**Announce at start:** "Cleaning up worktree."

## The Process

```bash
BRANCH=$(git branch --show-current)
ESCAPED_BRANCH=$(printf '%s\n' "$BRANCH" | sed 's/[.\\^$*+?()[{|]/\\&/g')
WORKTREE_PATH=$(git worktree list --porcelain | grep -B2 "branch refs/heads/$ESCAPED_BRANCH" | grep "^worktree " | sed 's/^worktree //')
MAIN_WORKTREE=$(git worktree list --porcelain | head -1 | sed 's/^worktree //')

# Only remove if we're in a secondary worktree (not the main repo)
if [ -n "$WORKTREE_PATH" ] && [ "$(pwd)" = "$WORKTREE_PATH" ] && [ "$WORKTREE_PATH" != "$MAIN_WORKTREE" ]; then
  cd "$MAIN_WORKTREE"
  git worktree remove "$WORKTREE_PATH"
  echo "Removed worktree: $WORKTREE_PATH"
else
  echo "Not in a secondary worktree - nothing to clean up"
fi
```

**If removal fails** (e.g., uncommitted changes): run `git worktree remove --force "$WORKTREE_PATH"` only if you are
certain no work will be lost.

## Bulk Cleanup

To remove all worktrees under `.worktrees/` (e.g., after fixing a full stack):

```bash
MAIN_WORKTREE=$(git worktree list --porcelain | head -1 | sed 's/^worktree //')
cd "$MAIN_WORKTREE"
git worktree list | grep .worktrees | awk '{print $1}' | xargs -I{} git worktree remove {}
```

## When to Skip

- **Called from a parent skill** that manages its own worktree lifecycle (e.g., `st.fix-stack` calls `pr.fix-branch` but
  cleans up all worktrees at the end itself)
- **Worktree needed for future work** on the same branch (rare - prefer cleanup)

## Integration

**Called by:**

- **pr.submit** - After tests pass and submission is complete
- **pr.cool** - After cleanup and submission (when run standalone)
- **pr.fix-ci** - After CI failures are fixed (when run standalone)
- **pr.fix-comments** - After comments are addressed (when run standalone)
- **pr.fix-branch** - After branch is fully fixed and submitted
- **sk.submit-skill** - After skill PR merges
- **st.issue-to-stack** - After stack is submitted
- **st.fix-stack** - Bulk cleanup after all branches are fixed

**Pairs with:**

- **using-git-worktrees** (superpower) - Creates worktrees; this skill removes them
