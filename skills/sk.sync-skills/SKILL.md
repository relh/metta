---
name: sk.sync-skills
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
SKILLS_DIR="${1:-$(git rev-parse --show-toplevel)/skills}"
```

Verify the directory exists and contains skill subdirectories (dirs with `SKILL.md` inside). Any skill directory with a
`.private` file is skipped.

## Step 2: Sync Symlinks

For each skill directory, create/update symlinks in both targets:

```bash
CLAUDE_SKILLS="$HOME/.claude/skills"
CODEX_SKILLS="$HOME/.codex/skills"
mkdir -p "$CLAUDE_SKILLS" "$CODEX_SKILLS"

while IFS= read -r skill_file; do
  skill_path=$(dirname "$skill_file")
  [ -f "$skill_path/.private" ] && continue
  skill_name=$(basename "$skill_path")

  for target_dir in "$CLAUDE_SKILLS" "$CODEX_SKILLS"; do
    rm -rf "$target_dir/$skill_name"
    ln -s "$skill_path" "$target_dir/$skill_name"
  done
done < <(find "$SKILLS_DIR" -maxdepth 4 -name "SKILL.md" -type f)
```

## Step 3: Report

```
## Synced Skills

| Skill | Status |
|-------|--------|
| pr.fix-ci | linked |
| sk.make-skill | linked |

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

**Called by:** `sk.make-skill` (after creating a new skill), `sk.learn-skills` (after importing) **Pairs with:**
`sk.make-skill`, `sk.update-skill`
