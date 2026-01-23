#!/bin/bash
# Setup script to symlink skills from docs/ai/daveey/skills/ to ~/.claude/skills/
# This enables Claude Code to discover these skills automatically
#
# Usage:
#   ./setup.sh           # Safe mode - skip existing directories
#   ./setup.sh --force   # Replace existing directories with symlinks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
FORCE=false

if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
  FORCE=true
fi

# Create ~/.claude/skills if it doesn't exist
mkdir -p "$CLAUDE_SKILLS_DIR"

echo "Linking skills from $SKILLS_DIR to $CLAUDE_SKILLS_DIR"
if $FORCE; then
  echo "(Force mode: replacing existing directories)"
fi

# Link each skill directory
for skill_path in "$SKILLS_DIR"/*/; do
  skill_name=$(basename "$skill_path")
  target="$CLAUDE_SKILLS_DIR/$skill_name"

  # Handle existing symlinks
  if [ -L "$target" ]; then
    rm "$target"
    echo "  Removed existing symlink: $skill_name"
  # Handle existing directories
  elif [ -d "$target" ]; then
    if $FORCE; then
      rm -rf "$target"
      echo "  Removed existing directory: $skill_name"
    else
      echo "  Warning: $skill_name already exists as a directory, skipping"
      echo "    To overwrite, use --force or remove $target"
      continue
    fi
  fi

  # Create symlink
  ln -s "$skill_path" "$target"
  echo "  Linked: $skill_name"
done

echo ""
echo "Done! Skills are now available in Claude Code."
echo "Use /skill-name to invoke them (e.g., /gt:fix-branch)"
