# Shared AI Skills

Shared AI skills and commands for use with Claude Code, Codex, and Cursor.

Personal skill libraries live under `skills/user/<username>/` (see `docs/ai/daveey` and `docs/ai/subho`).

## Setup

### For Claude Code + Codex

In this repo, `.claude/skills` and `.codex/skills` already symlink to `skills/`. If you want to install skills outside
the repo, run:

```bash
./scripts/skills-sync.sh
```

This syncs shared skills only. To include personal skills under `skills/user/`, run:

```bash
./scripts/skills-sync.sh --include-user
```

### For Cursor

The shared skills catalog is described in `.cursor/rules/skills.mdc`.

## Available Skills

Shared skills live in `skills/`:

- `address-review`
- `check-ci`
- `checkpoint-find`
- `cleanup-refactor`
- `cogames-command`
- `cogames-variant-debug`
- `fix-traceback`
- `graphite-stack`
- `lint-fix`
- `mettabox-ops`
- `policy-save-load-audit`
- `pr-summary`
- `recipe-curriculum-audit`
- `review-main`
- `run-and-triage`
- `simplify-diff`
- `sync-main`
- `sync-nim-python`
- `test-triage`

See each `skills/<name>/SKILL.md` for the full workflow.

## Editing Skills

Edit shared skills in `skills/`. Personal skills live in `skills/user/<username>/`.
