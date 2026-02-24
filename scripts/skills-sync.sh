#!/bin/bash
# Sync repo skills into Claude Code and Codex skill directories.
# Skips any skill directory containing a .private file.
#
# Usage:
#   ./scripts/skills-sync.sh
#   ./scripts/skills-sync.sh --force         # Replace existing directories with symlinks
#   ./scripts/skills-sync.sh <path>          # Sync from a specific skills directory

set -e

FORCE=false
SKILLS_DIR=""

for arg in "$@"; do
  case "$arg" in
    --force | -f)
      FORCE=true
      ;;
    *)
      SKILLS_DIR="$arg"
      ;;
  esac
done

if [ -z "$SKILLS_DIR" ]; then
  REPO_ROOT=$(git rev-parse --show-toplevel 2> /dev/null || pwd)
  COGENTS_DIR="${COGENTS_PATH:-$(dirname "$REPO_ROOT")/cogents}"
  if [ -d "$COGENTS_DIR/skills" ]; then
    SKILLS_DIR="$COGENTS_DIR/skills"
  else
    SKILLS_DIR="$REPO_ROOT/skills"
  fi
fi

CLAUDE_SKILLS_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
CODEX_SKILLS_DIR="${CODEX_SKILLS_DIR:-$HOME/.codex/skills}"

mkdir -p "$CLAUDE_SKILLS_DIR" "$CODEX_SKILLS_DIR"

echo "Syncing skills from $SKILLS_DIR"
if $FORCE; then
  echo "(Force mode: replacing existing directories)"
fi

SEEN_SKILLS=""

FIND_CMD=(find "$SKILLS_DIR" -maxdepth 4 -name "SKILL.md" -type f -print)

while IFS= read -r skill_file; do
  skill_path=$(dirname "$skill_file")
  [ -f "$skill_path/.private" ] && continue
  skill_name=$(basename "$skill_path")

  case " $SEEN_SKILLS " in
    *" $skill_name "*)
      echo "  Warning: duplicate skill name '$skill_name' at $skill_path, skipping"
      continue
      ;;
  esac
  SEEN_SKILLS="$SEEN_SKILLS $skill_name"

  for target_dir in "$CLAUDE_SKILLS_DIR" "$CODEX_SKILLS_DIR"; do
    target="$target_dir/$skill_name"

    if [ -L "$target" ]; then
      rm "$target"
    elif [ -e "$target" ]; then
      if $FORCE; then
        rm -rf "$target"
      else
        echo "  Warning: $target already exists, skipping (use --force to overwrite)"
        continue
      fi
    fi

    ln -s "$skill_path" "$target"
    echo "  Linked: $skill_name -> $target_dir"
  done
done < <("${FIND_CMD[@]}")

echo ""
echo "Done! Skills are now available in Claude Code and Codex."
