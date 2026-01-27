#!/bin/bash
# Setup script to symlink skills from docs/ai/subho/skills/ to ~/.claude/skills/ and ~/.codex/skills/
# This enables Claude Code and Codex to discover these skills automatically
#
# Usage:
#   ./setup.sh           # Safe mode - skip existing directories
#   ./setup.sh --force   # Replace existing directories with symlinks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"
CLAUDE_SKILLS_DIR="$HOME/.claude/skills"
CODEX_SKILLS_DIR="$HOME/.codex/skills"
FORCE=false

if [ "$1" = "--force" ] || [ "$1" = "-f" ]; then
  FORCE=true
fi

# Function to symlink skills to a target directory
link_skills() {
  local target_dir="$1"
  local target_name="$2"

  # Create target directory if it doesn't exist
  mkdir -p "$target_dir"

  echo "Linking skills from $SKILLS_DIR to $target_dir"
  if $FORCE; then
    echo "(Force mode: replacing existing directories)"
  fi

  # Link each skill directory
  for skill_path in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_path")
    target="$target_dir/$skill_name"

    # Handle existing symlinks
    if [ -L "$target" ]; then
      rm "$target"
      echo "  [$target_name] Removed existing symlink: $skill_name"
    # Handle existing directories
    elif [ -d "$target" ]; then
      if $FORCE; then
        rm -rf "$target"
        echo "  [$target_name] Removed existing directory: $skill_name"
      else
        echo "  [$target_name] Warning: $skill_name already exists as a directory, skipping"
        echo "    To overwrite, use --force or remove $target"
        continue
      fi
    fi

    # Create symlink
    ln -s "$skill_path" "$target"
    echo "  [$target_name] Linked: $skill_name"
  done
}

# Link to both Claude Code and Codex
link_skills "$CLAUDE_SKILLS_DIR" "Claude Code"
echo ""
link_skills "$CODEX_SKILLS_DIR" "Codex"

echo ""
echo "Done! Skills are now available in Claude Code and Codex."
echo "Use /skill-name to invoke them (e.g., /worktrunk)"
