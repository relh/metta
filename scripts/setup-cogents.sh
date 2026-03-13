#!/bin/bash
# Clone the cogents repo (if needed) and wire up symlinks.
#
# Usage:
#   ./scripts/setup-cogents.sh              # Auto-detect sibling directory
#   COGENTS_PATH=/custom/path ./scripts/...  # Override location

set -euo pipefail

REPO_ROOT=$(git rev-parse --show-toplevel 2> /dev/null || pwd)
COGENTS_DIR="${COGENTS_PATH:-$(dirname "$REPO_ROOT")/cogents}"
COGENTS_REPO="${COGENTS_REPO:-git@github.com:Metta-AI/cogents.git}"

update_existing_checkout() {
  if [ ! -d "$COGENTS_DIR/.git" ]; then
    return
  fi

  branch=$(git -C "$COGENTS_DIR" branch --show-current)
  if [ "$branch" != "main" ]; then
    echo "Warning: cogents is on branch '${branch:-detached}'; skipping auto-update."
    return
  fi

  if [ -n "$(git -C "$COGENTS_DIR" status --short)" ]; then
    echo "Warning: cogents has local changes; skipping auto-update."
    return
  fi

  if ! git -C "$COGENTS_DIR" fetch origin > /dev/null 2>&1; then
    echo "Warning: failed to fetch cogents origin; leaving existing checkout as-is."
    return
  fi

  behind=$(git -C "$COGENTS_DIR" rev-list --count HEAD..origin/main)
  if [ "$behind" -eq 0 ]; then
    echo "Cogents checkout already up to date."
    return
  fi

  echo "Fast-forwarding cogents by $behind commit(s)..."
  git -C "$COGENTS_DIR" merge --ff-only origin/main
}

verify_shared_skills() {
  python3 - "$REPO_ROOT" "$COGENTS_DIR/skills" << 'PY'
from pathlib import Path
import sys

from metta.setup.cogents_sync import missing_shared_skills

repo_root = Path(sys.argv[1])
skills_dir = Path(sys.argv[2])
missing = missing_shared_skills(repo_root, skills_dir)

if missing:
    print("Error: cogents is missing shared skills referenced by .cursor/rules/skills.mdc:")
    for skill_name in missing:
        print(f"  - {skill_name}")
    raise SystemExit(1)
PY
}

if [ ! -d "$COGENTS_DIR/.git" ]; then
  echo "Cloning cogents into $COGENTS_DIR..."
  echo "Using GitHub SSH auth from your local account (must have Metta-AI access)."
  git clone "$COGENTS_REPO" "$COGENTS_DIR"
fi

update_existing_checkout

for target in .claude/skills .codex/skills .cursor/skills; do
  link_parent="$REPO_ROOT/$(dirname "$target")"
  mkdir -p "$link_parent"
  rm -f "$REPO_ROOT/$target"
  rel=$(python3 -c "import os.path; print(os.path.relpath('$COGENTS_DIR', '$link_parent'))")
  ln -s "$rel/skills" "$REPO_ROOT/$target"
  echo "  $target -> $rel/skills"
done

rm -f "$REPO_ROOT/.cursor/agents"
rel=$(python3 -c "import os.path; print(os.path.relpath('$COGENTS_DIR', '$REPO_ROOT/.cursor'))")
ln -s "$rel/subagents" "$REPO_ROOT/.cursor/agents"
echo "  .cursor/agents -> $rel/subagents"

mkdir -p "$REPO_ROOT/.agent"
rm -f "$REPO_ROOT/.agent/prompts"
rel=$(python3 -c "import os.path; print(os.path.relpath('$COGENTS_DIR', '$REPO_ROOT/.agent'))")
ln -s "$rel/prompts" "$REPO_ROOT/.agent/prompts"
echo "  .agent/prompts -> $rel/prompts"

verify_shared_skills

echo ""
echo "Done. Cogents is at $COGENTS_DIR"
