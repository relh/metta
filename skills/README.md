# Skills

This folder is the canonical, tool-agnostic skills registry for this repo.

Layout

- Each skill lives at `skills/<name>/SKILL.md`.
- The `SKILL.md` file keeps the same YAML front matter format used by Codex.

Installing skills locally

- In this repo, `.codex/skills` and `.claude/skills` are symlinks to `skills/`.
- To install skills outside the repo, run `./scripts/skills-sync.sh`.

Notes

- This repo does not assume a fixed Claude Code skills directory. Set `CLAUDE_SKILLS_DIR` explicitly.
- Keep `skills/` as the single source of truth for all skills. Use a `.private` file in a skill directory to exclude it
  from bulk sync if needed.
- The shared catalog lives at `docs/ai/skills.md`.
