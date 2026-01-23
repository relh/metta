# Skills

This folder is the canonical, tool-agnostic skills registry for this repo.

Layout

- Each skill lives at `skills/<name>/SKILL.md`.
- The `SKILL.md` file keeps the same YAML front matter format used by Codex.
- User-specific skills can live under `skills/user/<username>/`.

Installing skills locally

- In this repo, `.codex/skills` and `.claude/skills` are symlinks to `skills/`.
- To install skills outside the repo, copy or symlink `skills/` into the target tool's skills directory.

Notes

- This repo does not assume a fixed Claude Code skills directory. Set `CLAUDE_SKILLS_DIR` explicitly.
- Keep `skills/` as the single source of truth for global skills. User-specific skills live under `skills/user/`.
