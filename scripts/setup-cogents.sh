#!/bin/bash
# Clone the cogents repo (if needed) and wire up symlinks.
#
# Usage:
#   ./scripts/setup-cogents.sh              # Auto-detect sibling directory
#   COGENTS_PATH=/custom/path ./scripts/...  # Override location

set -e

REPO_ROOT=$(git rev-parse --show-toplevel 2> /dev/null || pwd)
COGENTS_DIR="${COGENTS_PATH:-$(dirname "$REPO_ROOT")/cogents}"
COGENTS_REPO="${COGENTS_REPO:-git@github.com:Metta-AI/cogents.git}"

if [ ! -d "$COGENTS_DIR/.git" ]; then
  echo "Cloning cogents into $COGENTS_DIR..."
  echo "Using GitHub SSH auth from your local account (must have Metta-AI access)."
  git clone "$COGENTS_REPO" "$COGENTS_DIR"
fi

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

echo ""
echo "Done. Cogents is at $COGENTS_DIR"
