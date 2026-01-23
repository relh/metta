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
5. Print Graphite URL

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

## Step 2: Lint

```bash
metta lint --fix
```

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

## Step 5: Report

Print the Graphite URL:

```
https://app.graphite.com/github/pr/Metta-AI/metta/<PR_NUMBER>
```

## Integration

**Called by:**

- **m:make-skill** - After creating a new skill
- **m:update-skill** - After updating an existing skill
