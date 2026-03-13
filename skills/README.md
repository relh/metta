# Skills

This folder keeps repo-local and legacy skill definitions. Shared cross-repo skills live in the sibling `cogents`
checkout.

Layout

- Each skill lives at `skills/<name>/SKILL.md`.
- The `SKILL.md` file keeps the same YAML front matter format used by Codex.

Installing skills locally

- In this repo, `.codex/skills` and `.claude/skills` are symlinks to `../cogents/skills`.
- Run `./scripts/setup-cogents.sh` to clone or fast-forward `../cogents` and verify the shared skill list.
- To install skills outside the repo, run `./scripts/skills-sync.sh`.

Notes

- This repo does not assume a fixed Claude Code skills directory. Set `CLAUDE_SKILLS_DIR` explicitly.
- Treat `../cogents/skills` as the shared source of truth. Use a `.private` file in a skill directory to exclude it
  from bulk sync if needed.
- The shared catalog lives at `docs/ai/skills.md`.
