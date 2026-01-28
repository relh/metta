# Subho's AI Skills

Personal AI skills for Subho. Shared skills live in `docs/ai/skills.md`.

## Location

- Personal skills: `skills/user/subho/`
- Shared skills: `skills/`

## Setup

### For Claude Code + Codex

In this repo, `.claude/skills` and `.codex/skills` point at `skills/` (shared only). To sync personal skills into your
local tools, run:

```bash
./scripts/skills-sync.sh
```

That command only syncs shared skills. If you only want Subho's personal skills, run:

```bash
./scripts/skills-sync.sh skills/user/subho
```

To sync shared + all user skills, run:

```bash
./scripts/skills-sync.sh --include-user
```

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

Edit the skills directly in `skills/user/subho/`.
