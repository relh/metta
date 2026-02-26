---
name: pr.bless
description:
  Use when you want to self-approve a PR to bypass the human review requirement while keeping CI and merge queue intact.
  Alternative to force-merging.
---

# Bless

Self-approve a PR so it can merge through the normal CI/merge queue pipeline without requiring another human's review.
Uses a label-triggered GitHub Actions workflow for the actual approval (bot review from `github-actions[bot]`).

**Announce at start:** "Blessing this PR for self-approved merge."

## The Process

1. Validate current branch has an open PR
2. Show PR summary for confirmation
3. Add "blessed" label (triggers the approval workflow)
4. Enable merge-when-ready via Graphite

## Step 1: Validate PR

```bash
PR_JSON=$(gh pr view --json number,title,author,state,statusCheckRollup,url,headRefName)
PR_STATE=$(echo "$PR_JSON" | jq -r '.state')
```

**If no PR exists or state is not OPEN:** Stop. Tell the user to submit first (`gt submit`).

## Step 2: Show Summary

Display to the user:

```bash
PR_NUM=$(echo "$PR_JSON" | jq -r '.number')
PR_TITLE=$(echo "$PR_JSON" | jq -r '.title')
PR_AUTHOR=$(echo "$PR_JSON" | jq -r '.author.login')
PR_URL=$(echo "$PR_JSON" | jq -r '.url')
echo "Blessing PR #$PR_NUM: $PR_TITLE (by $PR_AUTHOR)"
echo "$PR_URL"
```

Show CI status summary. If CI is failing, warn but don't block (merge queue will enforce).

## Step 3: Add Label

```bash
gh pr edit "$PR_NUM" --add-label "blessed"
```

This triggers the `bless.yml` workflow which:

- Verifies the labeler is in the allowed-authors list
- Approves the PR via bot review
- Posts to Discord for visibility

If the "blessed" label doesn't exist yet, create it:

```bash
gh label create "blessed" --description "Self-approved for merge" --color "7B61FF" 2>/dev/null || true
```

## Step 4: Enable Merge-When-Ready

```bash
gt submit --merge-when-ready --no-interactive
```

Report the PR URL and that the merge will proceed automatically once CI passes.

## Quick Reference

| Step     | Command                            | Purpose                   |
| -------- | ---------------------------------- | ------------------------- |
| Validate | `gh pr view --json ...`            | Ensure PR exists and open |
| Label    | `gh pr edit --add-label "blessed"` | Trigger approval workflow |
| Merge    | `gt submit --merge-when-ready`     | Auto-merge when CI passes |

## Integration

**Pairs with:**

- **pr.submit** - Submit first, then bless if self-approving
- **pr.check-ci** - Check CI status before blessing

**Called after:**

- **pr.submit** - When you want to self-approve and merge
