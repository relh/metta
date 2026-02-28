---
name: cb.simplify-repo
description:
  Use when asked to run a broad, behavior-preserving cleanup across many repo subfolders and ship the result as one
  focused PR.
args: <subfolder_count=50> [focus_paths...]
---

# Simplify Repo

## Overview

Run a broad cleanup sweep and keep only high-confidence, behavior-preserving simplifications.

**Announce at start:** "I’m running cb.simplify-repo: I’ll scan `<subfolder_count>` subfolders, keep only clear macro
wins, and ship one focused PR."

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

## Step 2: Scan For Macro Candidates

Prioritize patterns with clear readability/indirection wins:

```bash
DIRS="$(tr '\n' ' ' </tmp/simplify_dirs.txt)"
ruff check --select SIM $DIRS
rg -n -U -g '*.py' "if .*:\n\s+if |\.keys\(\)|return\s+\w+\s*$" $DIRS
rg -n -g '*.py' \
  "except Exception|except:\s*$|\bis None\b|dict\.get\(|getattr\([^,]+,[^,]+,[^)]+\)|shim|compat|backward|legacy|alias|fallback" \
  $DIRS
rg -n -U -g '*.py' "def [A-Za-z_]\w*\([^)]*\):\n\s+return [A-Za-z_][A-Za-z0-9_]*\(" $DIRS
if command -v vulture >/dev/null 2>&1; then
  vulture $DIRS --min-confidence 95 --exclude "*test*.py,*migrations*"
fi
```

Keep only behavior-equivalent candidates. For fallback/`None`/`except` matches, keep a candidate only when callsites and
types prove an internal invariant (not external input). For `vulture` matches, keep only very-high-confidence dead code:
`>=95`, zero in-repo references (`rg -n "\bSymbolName\b"`), and not part of a public export surface.

## Step 3: Apply Minimal Safe Simplifications

Rules:

- Collapse duplicated branches and nested `if` chains when semantics are unchanged.
- Replace key-view indirection (`for k in d.keys()`, `x in d.keys()`) with direct iteration/membership.
- Replace defensive internal fallbacks (`dict.get`, `getattr(..., default)`, `x or default`) only when required fields
  are guaranteed by invariants.
- Remove broad `except` blocks or dead `None` branches only when you can prove they are unreachable.
- Remove dead code from `vulture` results only when confidence is `>=95` and callsite search confirms no live usage.
- Delete compat aliases/shim wrappers only after updating all in-repo callsites.
- Remove dead helper layers only when all callsites stay equivalent.
- Avoid broad stylistic churn; skip borderline refactors.

## Step 4: Validate Touched Code

```bash
CHANGED_PY=$(git diff --name-only -- '*.py')
if [ -n "$CHANGED_PY" ]; then
  echo "$CHANGED_PY" | xargs ruff check
  echo "$CHANGED_PY" | xargs python -m py_compile
else
  echo "No Python files changed"
fi
# run nearest tests for touched modules
metta pytest <targeted-test-paths>
```

If environment-limited failures occur, note them in the PR.

## Step 5: Ship One PR

```bash
git add -A
git commit -m "refactor: macro simplify repo without behavior changes" \
  -m "Co-Authored-By: GPT-5 <gpt-5@openai.com>"
git push -u origin HEAD
```

Draft summary from diff, then create PR:

```bash
# Use skill: pr.summary
gh pr create --base main --head "$(git branch --show-current)" --title "<TITLE>" --body "<BODY>"
```

## Integration

**Uses:** `cb.cleanup-refactor`, `cb.simplify-diff`, `pr.summary`  
**Pairs with:** `pr.check-ci`, `pr.fix-ci`  
**Alternative:** `cb.cleanup-pr-sweep` when the user wants many small PRs instead of one.
