---
name: cb.simplify-repo
description:
  Use when asked to run a broad, behavior-preserving cleanup across many repo subfolders and ship the result as one
  focused PR.
args: <subfolder_count=50> [focus_paths...]
---

# Simplify Repo

## Overview

Run cleanup with the #1 goal of net LOC reduction without behavior changes.

Top-level requirement:

- Ship a net-negative LOC diff. If not, keep scanning.
- Prefer deletions/inlining over lateral rewrites.
- Reject LOC increases unless they unlock larger deletions.

**Announce at start:** "I’m running cb.simplify-repo: I’ll scan `<subfolder_count>` subfolders, keep only macro wins,
and ship one net-negative LOC PR."

## Step 1: Prepare Branch And Scope

```bash
git status --short
git switch main
git pull --ff-only
git switch -c "$(whoami)/macro-simplify-repo" origin/main
```

```bash
COUNT="${1:-50}"
shift || true
if [ "$#" -gt 0 ]; then
  TARGETS=("$@")
else
  TARGETS=(metta common app_backend packages tools scripts)
fi
rg --files -g '*.py' "${TARGETS[@]}" | xargs -n1 dirname | sort -u | shuf -n "$COUNT" > /tmp/simplify_dirs.txt
```

## Step 2: Scan For Substantial Candidates

```bash
DIRS="$(tr '\n' ' ' </tmp/simplify_dirs.txt)"
ruff check --select SIM $DIRS
rg -n -U -g '*.py' "if .*:\n\s+if |elif .*:\n\s+return|def [A-Za-z_]\w*\([^)]*\):\n\s+return [A-Za-z_][A-Za-z0-9_]*\(" $DIRS
rg -n -g '*.py' "^def [A-Za-z_]\w*\(|^class [A-Za-z_]\w*\(" $DIRS
rg -n -g '*.py' \
  "except Exception|except:\s*$|\bis None\b|dict\.get\(|getattr\([^,]+,[^,]+,[^)]+\)|shim|compat|backward|legacy|alias|fallback" \
  $DIRS
if command -v vulture >/dev/null 2>&1; then
  vulture $DIRS --min-confidence 95 --exclude "*test*.py,*migrations*"
fi
```

## Step 3: Apply Only Macro Wins

Rules:

- Keep changes only when they remove duplication/dead code/compat/indirection and reduce net LOC.
- Inline one-use helpers (including cross-file) when callsites stay readable, then delete the helper.
- Canonicalize duplicative classes: keep one canonical type, migrate all callsites, delete the disguise class.
- Monorepo invariant: all callsites are in-repo.
- Collapse duplicated branches and nested conditionals when semantics are unchanged.
- Replace defensive internal fallbacks (`dict.get`, `getattr(..., default)`, `x or default`) only when invariants prove
  required fields are always present.
- Remove broad `except` blocks or dead `None` branches only when you can prove they are unreachable.
- Remove `vulture` dead code only with confidence `>=95` and no live callsites.
- Reject low-signal churn:
  - `.keys()` rewrites (`x in d.keys()`, `for k in d.keys()`) as standalone edits
  - trivial style-only rewrites that do not reduce indirection
  - behavior-risky container rewrites on non-dict mappings (e.g., `TensorDict`)
- If >10% of changed lines are low-signal churn, revert those hunks and rescan.

## Step 4: Validate Touched Code

```bash
CHANGED_PY=$(git diff --name-only -- '*.py')
if [ -n "$CHANGED_PY" ]; then
  echo "$CHANGED_PY" | xargs ruff check
  echo "$CHANGED_PY" | xargs python -m py_compile
else
  echo "No Python files changed"
fi
git diff --shortstat
# run nearest tests for touched modules
metta pytest <targeted-test-paths>
```

If `git diff --shortstat` is not net-negative LOC, revert low-value hunks and rescan.

## Step 5: Ship One PR

```bash
git add -A
git commit -m "refactor: macro simplify repo without behavior changes" \
  -m "Co-Authored-By: GPT-5 <gpt-5@openai.com>"
git push -u origin HEAD
```

```bash
gh pr create --base main --head "$(git branch --show-current)" --title "<TITLE>" --body "<BODY>"
```
