---
name: cb.cleanup-pr-sweep
description:
  Use when asked to find multiple meaningful cleanup/simplification opportunities across the repo and land them as
  separate small PRs (typically 10), focusing on removing dead defensive checks/try-excepts and reducing indirection
  without changing behavior.
args: <count=10> [branch_prefix] [focus_paths...]
---

# Cleanup PR Sweep

## Overview

Find and land a batch of small, behavior-preserving cleanup PRs. Prefer deleting dead defensive code (blanket
`try/except`, impossible `None` checks), collapsing duplication, and removing unused backcompat aliases.

**Announce at start:** "I’m running a cleanup sweep: I’ll identify `<count>` safe simplifications, then open one PR per
change."

## The Process

1. **Prep and constraints**
2. **Find candidates**
3. **For each change: branch, edit, validate, PR**
4. **Report PRs**

## Step 1: Prep And Constraints

```bash
git status --short
git switch main
git pull --ff-only
gh auth status
```

Constraints:

- Keep each PR tight: 1 theme, minimal diff, no drive-by refactors.
- Do not add one-off helper functions; prefer inlining/collapsing.
- Do not change `proto/` unless explicitly requested.

## Step 2: Find Candidates

Start with high-signal defensive patterns:

```bash
FOCUS=(metta common app_backend packages observatory)
rg -n --hidden --glob '!node_modules/**' --glob '!dist/**' "except Exception|except:\\s*$|\\bis None\\b|hasattr\\(|callable\\(" "${FOCUS[@]}"
```

Heuristics for "safe to delete":

- A branch is unreachable given types/callsites (confirm with `rg` and type hints).
- A try/except wraps pure operations that cannot raise (or can be narrowed to concrete exceptions).
- Backcompat alias is unused in-repo (confirm with `rg -n "\\bAliasName\\b"`).

Write down 2-3 sentence rationale per candidate before editing.

## Step 3: Land Each Change As Its Own PR

For each candidate (repeat until `<count>` PRs exist):

```bash
git switch main
git pull --ff-only
git switch -c "<branch_prefix>-cleanup-<short-slug>" origin/main
```

Edit the minimal set of files. Then validate:

```bash
python -m py_compile path/to/touched.py  # repeat per touched file
# If relevant unit tests exist, run the smallest targeted test(s):
uv run pytest -q tests/path/to/test_file.py::test_name
```

Commit + PR:

```bash
git add -A
git commit -m "<short title>" -m "<why safe / what removed>" -m "Co-authored-by: GPT-5 <gpt-5@openai.com>"
git push -u origin HEAD
gh pr create --base main --head "$(git branch --show-current)" --title "<title>" --body "<bullets: what changed, why safe>"
```

## Step 4: Report

Return a numbered list of PRs with titles and URLs. Call out any changes that intentionally removed dead backcompat.

## Integration

**Uses:** `cb.cleanup-refactor` (local simplification mindset), `cb.simplify-diff` (make a diff smaller), `cf.really`
(loop until N PRs)

**Pairs with:** `pr.check-ci` (watch failures), `pr.fix-ci` (fix failures) when needed.
