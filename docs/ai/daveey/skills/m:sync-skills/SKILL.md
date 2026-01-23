---
name: m:sync-skills
description: Use when skills are missing from Claude Code or Codex, or after switching worktrees/repos
args: '[path-to-skills-dir]'
---

# Sync Skills

Symlink all skills from a directory to both Claude Code (`~/.claude/skills/`) and Codex (`~/.codex/skills/`).

**Announce at start:** "Syncing skills from `<path>` to Claude Code and Codex."

## The Process

1. Resolve skills directory
2. Sync symlinks to both tools
3. Report results

## Step 1: Resolve Skills Directory

```bash
# Use arg if provided, otherwise default to current repo
SKILLS_DIR="${1:-$(git rev-parse --show-toplevel)/docs/ai/daveey/skills}"
```

Verify the directory exists and contains skill subdirectories (dirs with `SKILL.md` inside).

## Step 2: Sync Symlinks

For each skill directory, create/update symlinks in both targets:

```bash
CLAUDE_SKILLS="$HOME/.claude/skills"
CODEX_SKILLS="$HOME/.codex/skills"
mkdir -p "$CLAUDE_SKILLS" "$CODEX_SKILLS"

for skill_path in "$SKILLS_DIR"/*/; do
  [ -f "$skill_path/SKILL.md" ] || continue
  skill_name=$(basename "$skill_path")

  for target_dir in "$CLAUDE_SKILLS" "$CODEX_SKILLS"; do
    rm -rf "$target_dir/$skill_name"
    ln -s "$skill_path" "$target_dir/$skill_name"
  done
done
```

## Step 3: Report

```
## Synced Skills

| Skill | Status |
|-------|--------|
| gt:fix-ci | linked |
| m:make-skill | linked |

<N> skills synced to ~/.claude/skills/ and ~/.codex/skills/
Source: <SKILLS_DIR>

Note: Restart Claude Code sessions for new skills to appear in /slash commands.
```

## Quick Reference

| Target      | Path                      | Format         |
| ----------- | ------------------------- | -------------- |
| Claude Code | `~/.claude/skills/<name>` | symlink to dir |
| Codex       | `~/.codex/skills/<name>`  | symlink to dir |

## Integration

**Called by:** `m:make-skill` (after creating a new skill), `m:learn-skills` (after importing) **Pairs with:**
`m:make-skill`, `m:update-skill`
