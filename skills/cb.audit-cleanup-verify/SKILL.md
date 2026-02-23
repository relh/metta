---
name: cb.audit-cleanup-verify
description:
  Use when asked to audit a specific subpart of the codebase for cleanup/simplification, remove compat/indirection
  cruft, and verify behavior still works locally or on mettabox.
args: <focus_path> [smoke_cmd] [mettabox_host=metta3]
---

# Audit Cleanup Verify

## Overview

Run a focused cleanup on one path and finish all the way through shipping.

This skill is complete only when:

- changes are pushed on a non-`main` branch
- a PR is open
- local repo is back on `main`

## Required Flow

```bash
FOCUS="${FOCUS:-${1:-}}"
if [ -z "$FOCUS" ]; then
  echo "Usage: <focus_path> [smoke_cmd] [mettabox_host=metta3]"
  return 1 2>/dev/null || exit 1
fi
SMOKE_CMD="${SMOKE_CMD:-${2:-uv run ./tools/run.py recipes.experiment.cogsguard.train -- run=smoke.cleanup}}"
BASE=$(git merge-base HEAD origin/main)
git diff --stat "$BASE"...HEAD -- "$FOCUS"
rg -n "shim|compat|backward|legacy|alias|fallback|dict.get\\(" "$FOCUS"
```

1. Cleanup only inside `FOCUS`; remove shims/aliases/fallbacks and unnecessary indirection.
2. Keep behavior unchanged and bias toward net simplification.
3. Verify with targeted tests plus smoke command:

```bash
uv run pytest -q <targeted-tests>
$SMOKE_CMD
```

4. If verify fails, fix and repeat until green.
5. Ship:

- ensure branch is not `main`
- commit
- push
- open PR with clear summary + verification
- check that CI started (or report why unavailable)
- include PR URL in final response

6. End by returning local checkout to `main`.

## Non-Negotiables

- Do not stop at “tests pass”; PR must be open.
- Do not leave user on a feature branch at end; return to `main`.
- If blocked from push/PR, report the exact blocker and attempted commands.
