---
name: m:submit-skill
description:
  Use when you need to commit and submit skill file changes - handles worktree, lint, commit, submit, publish, and
  merge-when-ready
---

# Submit Skill

## Overview

Commit and submit skill file changes to Graphite. Creates a worktree, lints, commits, submits, publishes the PR, enables
merge-when-ready, and prints the Graphite URL.

**Announce at start:** "Submitting skill changes via worktree."

## The Process

1. Create worktree and branch
2. Lint changed files
3. Commit and submit
4. Publish PR and enable merge-when-ready
5. Monitor PR; run `/gt:fix-branch` if CI fails or comments appear
6. Print Graphite URL

## Step 1: Worktree and Branch

```bash
SKILL_NAME="<skill-name>"
BRANCH_NAME="daveey/skill-$SKILL_NAME"

# Create worktree on a new branch off main
wt switch --create "$BRANCH_NAME"
```

**If updating an existing skill** (branch already exists), just switch to it:

```bash
wt switch "$BRANCH_NAME" || wt switch --create "$BRANCH_NAME"
```

## Step 2: Lint (MANDATORY - NEVER SKIP)

**CRITICAL:** Lint MUST pass before committing. Skipping causes CI failures.

```bash
# Run lint - MUST exit cleanly before proceeding
metta lint

# If metta lint fails on markdown/prettier, use npx:
npx prettier --write docs/ai/daveey/skills/
```

**Do NOT proceed to Step 3 until lint passes.** Fix all errors first.

## Step 3: Commit and Submit

```bash
git add docs/ai/daveey/skills/ docs/ai/daveey/README.md
gt create "$BRANCH_NAME" -m "feat(skills): $SKILL_NAME skill

Co-Authored-By: Claude <noreply@anthropic.com>"
gt submit --no-interactive
```

**If branch already exists** (updating):

```bash
git add -A
gt modify --no-interactive
gt submit --no-interactive
```

## Step 4: Publish and Merge-When-Ready

```bash
PR_NUMBER=$(gh pr list --head "$BRANCH_NAME" --json number -q '.[0].number')
gh pr ready "$PR_NUMBER"
gh pr merge "$PR_NUMBER" --auto --squash
```

## Step 5: Monitor and Fix

After enabling merge-when-ready, monitor the PR until it merges. Poll every 30 seconds:

```bash
OWNER=$(gh repo view --json owner -q '.owner.login')
REPO=$(gh repo view --json name -q '.name')

while true; do
  STATE=$(gh pr view "$PR_NUMBER" --json state,mergedAt -q '.state')
  if [ "$STATE" = "MERGED" ]; then
    echo "PR #$PR_NUMBER merged successfully"
    break
  fi

  # Check for new review comments or CI failures
  CHECKS_FAILING=$(gh api "repos/$OWNER/$REPO/commits/$(git rev-parse HEAD)/check-runs" \
    --jq '[.check_runs[] | select(.conclusion == "failure")] | length')
  UNRESOLVED=$(gh api graphql -f query='
    query($owner: String!, $repo: String!, $pr: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $pr) {
          reviewThreads(first: 100) {
            nodes { isResolved }
          }
        }
      }
    }
  ' -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER" \
    --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved == false)] | length')

  if [ "$CHECKS_FAILING" -gt 0 ] || [ "$UNRESOLVED" -gt 0 ]; then
    echo "Issues detected (CI failures: $CHECKS_FAILING, unresolved comments: $UNRESOLVED)"
    # Run gt:fix-branch to address comments and CI failures
    break  # Exit loop, dispatch fix-branch below
  fi

  sleep 30
done
```

**If issues detected:** Invoke `/gt:fix-branch` (which handles sync, restack, fix-comments, fix-ci, and re-submit). Then
re-enable merge-when-ready and resume monitoring.

**If merged:** Proceed to Step 6.

## Step 6: Report

Print the Graphite URL:

```
https://app.graphite.com/github/pr/Metta-AI/metta/<PR_NUMBER>
```

## Integration

**Uses:**

- **gt:fix-branch** - Fixes PR comments and CI failures during monitoring

**Called by:**

- **m:make-skill** - After creating a new skill
- **m:update-skill** - After updating an existing skill
