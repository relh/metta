#!/bin/bash
# Sync Asana tasks to beads
# Usage: ./sync-asana.sh [--dry-run] [--scope my|projects|all]
#
# Can be run from:
#   - Gas Town rig: ~/gt/metta/scripts/sync-asana.sh
#   - Metta repo:   gastown/scripts/sync-asana.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Find metta repo root (look for pyproject.toml)
if [ -f "$SCRIPT_DIR/../../pyproject.toml" ]; then
  # Running from within metta repo (gastown/scripts/)
  METTA_REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
else
  # Running from Gas Town rig
  METTA_REPO="${METTA_REPO:-$HOME/Code/work/metta}"
fi

# Rig directory for bd commands (Gas Town context)
RIG_DIR="${GT_RIG:-$(dirname "$SCRIPT_DIR")}"

if [ -z "$ASANA_TOKEN" ]; then
  echo "Error: ASANA_TOKEN not set" >&2
  echo "Get a token from https://app.asana.com/0/developer-console" >&2
  exit 1
fi

# Check for dry-run flag
DRY_RUN=false
for arg in "$@"; do
  if [ "$arg" = "--dry-run" ]; then
    DRY_RUN=true
    break
  fi
done

if [ "$DRY_RUN" = true ]; then
  cd "$RIG_DIR" && uv run --project "$METTA_REPO" python "$SCRIPT_DIR/asana_sync.py" "$@"
else
  # Sync and import
  cd "$RIG_DIR" && uv run --project "$METTA_REPO" python "$SCRIPT_DIR/asana_sync.py" "$@" | bd import
  echo "Sync complete. Run 'bd list --label asana' to see imported tasks."
fi
