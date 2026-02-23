---
name: cf.bop-it
description:
  Use when a user wants a feature request delivered end-to-end (plan, tests, implementation, self-review, lint, test
  runs, commit, push, and a published PR with title/description).
---

# Bop It

## Overview

A single, repeatable loop for shipping a feature request: plan it, test it, build it, review it, and publish a PR.

Always prefer PR-relevant work: run only the smallest set of skills/commands needed for the files and systems touched by
the current diff.

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

Run `cb.review-main` only when it is relevant (for example: broad diff, cross-package behavior, risky logic changes, or
explicit review request). For narrow local changes, do a direct manual merge-base diff review without invoking extra
skills.

If needed, invoke:

```
Use Skill tool: skill="cb.review-main"
```

## Step 5: Lint It (Never Skip)

Run lint only for touched scope first (package/app-local lint commands). Use `cb.lint-fix` only when:

- local lint commands are unavailable/incomplete for the touched scope
- the PR touches multiple lint domains and centralized lint fix is the most relevant path
- user explicitly asks for repo-wide lint fixing

## Step 6: Run It (Tests)

Run tests relevant to changed files first (closest unit/integration tests).

Use `t.run-tests` only when the PR scope is broad, failures are unclear, or user requests full progressive test
coverage.

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

| Bop It step | Default action                | Escalate skill (only if relevant) |
| ----------- | ----------------------------- | --------------------------------- |
| Plan it     | criteria + smallest slice     | n/a                               |
| Test it     | nearest failing tests first   | `t.run-tests`                     |
| Do it       | minimal implementation        | n/a                               |
| Review it   | manual merge-base diff review | `cb.review-main`                  |
| Lint it     | scope-local lint commands     | `cb.lint-fix`                     |
| Ship it     | `pr.summary` + `gh pr create` | n/a                               |

## Integration

**Uses:** `cb.review-main`, `cb.lint-fix`, `t.run-tests`, `pr.summary`  
**Pairs with:** `pr.check-ci` (monitor), `db.test-triage` (fix failing tests), `pr.fix-ci` (fix CI lint), `cf.really`
