---
name: cf.bop-it
description:
  Use when a user wants a feature request delivered end-to-end (plan, tests, implementation, self-review, lint, test
  runs, commit, push, and a published PR with title/description).
---

# Bop It

## Overview

A single, repeatable loop for shipping a feature request: plan it, test it, build it, review it, and publish a PR.

**Announce at start:** "I’m using cf.bop-it: I’ll take this feature from plan to a PR, with tests and lint passing."

## Step 1: Plan It (Acceptance Criteria + Approach)

- Restate the request as concrete acceptance criteria (inputs, outputs, edge cases).
- Identify the smallest testable slice.
- If the change is non-trivial, write a short scratch plan in `docs/plans/` (gitignored; do not commit).

## Step 2: Test It (Red)

- Add/adjust tests that fail for the current behavior and prove the feature works when done.
- Keep tests close to the change (same package/module) and minimal (avoid broad integration tests unless needed).

## Step 3: Do It (Green)

- Implement the minimal code to make the new tests pass.
- Avoid extra abstractions and backwards-compat shims unless explicitly requested.

## Step 4: Review It (Local Code Review)

Use a merge-base diff against `origin/main` and look for:

- correctness bugs / regressions
- unintended diffs (drive-by changes)
- missing tests or missing negative cases
- cleanup opportunities that shrink the diff

If helpful, invoke:

```
Use Skill tool: skill="cb.review-main"
```

## Step 5: Lint It (Never Skip)

```
Use Skill tool: skill="cb.lint-fix"
```

## Step 6: Run It (Tests)

```
Use Skill tool: skill="t.run-tests"
```

## Step 7: Ship It (Commit, Push, PR)

1. Draft a PR title/body from the diff (edit for clarity):
   - `Use Skill tool: skill="pr.summary"`
2. Commit:

```bash
git status --short
git diff --stat
git add -A
git commit -m "feat: <short description>"
```

3. Push:

```bash
git push -u origin HEAD
```

4. Create PR (paste the title/body you drafted):

```bash
gh pr create --base main --head "$(git branch --show-current)" --title "<TITLE>" --body "<BODY>"
gh pr view --web
```

5. Optional: enable auto-merge (squash) once checks pass:

```bash
gh pr merge --auto --squash
```

## Quick Reference

| Bop It step | Skill / Command               | Output       |
| ----------- | ----------------------------- | ------------ |
| Plan it     | (criteria + scratch plan)     | clear scope  |
| Test it     | add failing tests             | red          |
| Do it       | implement minimal change      | green        |
| Review it   | `cb.review-main`              | issues list  |
| Lint it     | `cb.lint-fix`                 | lint clean   |
| Run it      | `t.run-tests`                 | tests clean  |
| Ship it     | `pr.summary` + `gh pr create` | published PR |

## Integration

**Uses:** `cb.review-main`, `cb.lint-fix`, `t.run-tests`, `pr.summary`  
**Pairs with:** `pr.check-ci` (monitor), `db.test-triage` (fix failing tests), `pr.fix-ci` (fix CI lint), `cf.really`
