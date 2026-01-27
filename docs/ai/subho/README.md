# Subho's AI Skills

Personal AI skills and commands for use with Claude Code and Cursor.

## Setup

### For Claude Code

Run the setup script to symlink skills to `~/.claude/skills/`:

```bash
./docs/ai/subho/setup.sh
```

This creates symlinks from `~/.claude/skills/` to `docs/ai/subho/skills/`, allowing Claude Code to discover them
automatically.

### For Codex

The same setup script also creates symlinks to `~/.codex/skills/` for Codex integration.

## Available Skills

| Skill       | Description                                                                   |
| ----------- | ----------------------------------------------------------------------------- |
| `worktrunk` | Worktrunk configuration, hooks, LLM commits, and troubleshooting (via plugin) |

## Usage

### In Claude Code

Invoke skills using slash commands:

```
/worktrunk
```

### In Cursor

Reference the skills in your prompts:

```
Use the worktrunk skill to configure worktrunk
```

## Editing Skills

Edit the skills directly in `docs/ai/subho/skills/`. Changes are automatically picked up by Claude Code and Codex (via
symlinks).
