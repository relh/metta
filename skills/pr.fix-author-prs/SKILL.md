---
name: pr.fix-author-prs
description:
  Use when you need to sweep all open PRs for a specific author and fix merge conflicts, failing CI/lint, or actionable
  unresolved review comments, then push updates.
args: <author-login>
---

# Fix Author PRs

## Overview

Run an end-to-end maintenance sweep across every open PR authored by one GitHub user.

**Announce at start:** "Sweeping all open PRs for `<author>` and fixing conflicts, CI failures, and actionable review
comments."

## The Process

1. Build PR inventory for the author:

   ```bash
   AUTHOR="<author-login>"
   gh pr list --author "$AUTHOR" --state open --limit 100 \
     --json number,title,headRefName,url,statusCheckRollup
   ```

2. Build a status matrix (mergeability + unresolved review threads + check runs):

   ```bash
   OWNER=$(gh repo view --json owner -q '.owner.login')
   REPO=$(gh repo view --json name -q '.name')
   PR_NUMBER=<PR_NUMBER>
   gh api graphql -f query='
     query($owner:String!,$repo:String!,$pr:Int!){
       repository(owner:$owner,name:$repo){
         pullRequest(number:$pr){
           mergeable
           reviewThreads(first:100){ nodes{ id isResolved isOutdated } }
         }
       }
     }' -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER"
   ```

3. Process each PR that needs intervention (conflict, failed CI, or active unresolved thread):

   ```bash
   gh pr checkout <PR_NUMBER>
   git fetch origin
   ```

4. Resolve merge conflicts if `mergeable == CONFLICTING`:

   ```bash
   git merge origin/main
   # resolve conflicts, run focused tests, then:
   git add -A
   git commit --no-edit
   git push
   ```

5. Fix failing checks (especially lint/tests) from the current head SHA:

   ```bash
   SHA=$(gh pr view <PR_NUMBER> --json headRefOid -q .headRefOid)
   gh api repos/Metta-AI/metta/commits/$SHA/check-runs
   gh run view <RUN_ID> --log-failed
   ```

   Apply minimal root-cause fixes, run targeted local verification, and push.

6. Address actionable unresolved review threads:
   1. Read the full thread conversation.
   2. Implement a meaningful fix (prefer adding/updating regression tests for behavioral issues).
   3. Push branch updates.
   4. Reply and resolve the thread:

   ```bash
   THREAD_ID=<THREAD_ID>
   RESPONSE_BODY="Fixed: <what changed>"
   gh api graphql -f query='
     mutation($thread:ID!,$body:String!){
       addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$thread, body:$body}){ comment{url} }
       resolveReviewThread(input:{threadId:$thread}){ thread{isResolved} }
     }' -f thread="$THREAD_ID" -f body="$RESPONSE_BODY"
   ```

7. Re-audit all PRs for the author. Stop only when all are true:
   - no failing checks
   - no merge conflicts
   - no active unresolved review threads

## Quick Reference

| Need            | Command                                                |
| --------------- | ------------------------------------------------------ |
| List PRs        | `gh pr list --author <author> --state open`            |
| Checkout PR     | `gh pr checkout <PR>`                                  |
| Detect conflict | GraphQL `pullRequest.mergeable`                        |
| CI by SHA       | `gh api repos/<owner>/<repo>/commits/<sha>/check-runs` |
| Failed logs     | `gh run view <run-id> --log-failed`                    |
| Resolve thread  | GraphQL `resolveReviewThread` mutation                 |

## Integration

**Uses:** pr.fix-ci, pr.fix-comments, cb.lint-fix  
**Pairs with:** pr.check-ci, pr.sync-main, pr.context-cool
