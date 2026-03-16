# Direct Fallback Workflow

Use this path when `/pr.fix-branch` is clearly the wrong tool for the PR you are sweeping.

Examples:

- the branch is not in the repo's normal Graphite flow
- the PR targets a non-standard base branch and only needs a manual merge
- `gt` tooling is unavailable
- you need a narrowly scoped manual intervention and do not want the full branch orchestration

## Step 1: Isolate The Branch In A Worktree

```bash
PR_NUMBER=<PR_NUMBER>
OWNER=$(gh repo view --json owner -q '.owner.login')
REPO=$(gh repo view --json name -q '.name')
BRANCH=$(gh pr view "$PR_NUMBER" --json headRefName -q '.headRefName')
BASE=$(gh pr view "$PR_NUMBER" --json baseRefName -q '.baseRefName')
WORKTREE=".worktrees/pr-$PR_NUMBER-$BRANCH"
EXISTING=$(git worktree list --porcelain | grep -B2 "branch refs/heads/$BRANCH" | grep '^worktree ' | cut -d' ' -f2)

git fetch origin "$BRANCH" "$BASE"

if [ -n "$EXISTING" ]; then
  cd "$EXISTING"
elif [ -d "$WORKTREE" ]; then
  cd "$WORKTREE"
else
  git worktree add -B "$BRANCH" "$WORKTREE" "origin/$BRANCH"
  cd "$WORKTREE"
fi
```

## Step 2: Sync Against The Actual Base Branch

Never assume `main`.

```bash
git merge "origin/$BASE"
```

If merge conflicts appear:

1. resolve them completely
2. run the smallest targeted verification
3. stage the resolved files
4. commit the merge

```bash
git add -A
git commit --no-edit
```

## Step 3: Gather Review Feedback Before Editing

Fetch all of the review surfaces that can contain actionable requests:

### Review threads

```bash
gh api graphql -f query='
  query($owner:String!, $repo:String!, $pr:Int!){
    repository(owner:$owner, name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100){
          nodes{
            id
            isResolved
            isOutdated
            path
            line
            comments(first:100){
              nodes{
                body
                author{ login }
                createdAt
              }
            }
          }
        }
      }
    }
  }' -f owner="$OWNER" -f repo="$REPO" -F pr="$PR_NUMBER"
```

### Inline PR comments (bots often use these)

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR_NUMBER/comments" --paginate
```

### Top-level issue comments

```bash
gh api "repos/$OWNER/$REPO/issues/$PR_NUMBER/comments" --paginate
```

Rules:

- Read the full conversation, not just the first comment.
- For behavioral feedback, add or update a regression test before the fix.
- Record what changed and the reply you plan to post later.
- Do **not** resolve or reply to review threads yet.

## Step 4: Fix CI From The Current Head SHA

```bash
REMOTE_HEAD_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid -q '.headRefOid')
gh api "repos/$OWNER/$REPO/commits/$REMOTE_HEAD_SHA/check-runs"
gh run view <RUN_ID> --log-failed
```

Rules:

- Use the current remote PR head SHA, never `gh pr checks`.
- Fix the root cause, not the log symptom.
- Re-run the smallest targeted local checks before pushing.
- If you have unpublished local commits, Step 4 still audits the last pushed remote SHA; after push, repeat the remote-SHA verification in Step 5 before resolving anything.

## Step 5: Push And Verify Remote State

```bash
git push

LOCAL_SHA=$(git rev-parse HEAD)
REMOTE_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid -q '.headRefOid')
test "$LOCAL_SHA" = "$REMOTE_SHA"
```

If the SHAs differ, do not resolve comments yet. Investigate first.

## Step 6: Reply And Resolve Only Verified Threads

Only after the push is confirmed on the remote:

```bash
THREAD_ID=<THREAD_ID>
RESPONSE_BODY="Fixed: <what changed>"
gh api graphql -f query='
  mutation($thread:ID!, $body:String!){
    addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:$thread, body:$body}) {
      comment { id }
    }
  }' -f thread="$THREAD_ID" -f body="$RESPONSE_BODY"

gh api graphql -f query='
  mutation($thread:ID!){
    resolveReviewThread(input:{threadId:$thread}) {
      thread { isResolved }
    }
  }' -f thread="$THREAD_ID"
```

Leave threads open when:

- the feedback is a design disagreement
- the fix could not be completed
- another reviewer comment contradicts it

## Step 7: Re-Audit The PR

From the repo root:

```bash
python3 skills/pr.fix-author-prs/scripts/collect_author_pr_status.py <author-login> --pr "$PR_NUMBER" --format table
```

The PR is done only when it has:

- no merge conflicts
- no failed checks
- no actionable unresolved review threads
- no unhandled `CHANGES_REQUESTED` review decision
