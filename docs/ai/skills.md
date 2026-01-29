# Shared AI Skills

Shared AI skills and commands for use with Claude Code, Codex, and Cursor.

Prefix conventions and namespaces live in `docs/skills.md`.

## Setup

### For Claude Code + Codex

In this repo, `.claude/skills` and `.codex/skills` already symlink to `skills/`. If you want to install skills outside
the repo, run:

```bash
./scripts/skills-sync.sh
```

### For Cursor

The shared skills catalog is described in `.cursor/rules/skills.mdc`.

## Available Skills

Shared skills live in `skills/`:

- `pr.address-review`
- `relh.cb.branch-hygiene`
- `cf.really`
- `pr.check-ci`
- `tr.checkpoint-find`
- `cb.cleanup-refactor`
- `tr.cogames-command`
- `tr.cogames-variant-debug`
- `db.fix-traceback`
- `st.graphite-stack`
- `st.apply`
- `pr.cool`
- `st.extract`
- `st.extract-copy`
- `pr.fix-branch`
- `pr.fix-ci`
- `pr.fix-comments`
- `st.fix-stack`
- `st.make-stack`
- `st.split`
- `pr.submit`
- `cb.lint-fix`
- `sk.learn-skills`
- `sk.make-skill`
- `sk.submit-skill`
- `sk.sync-skills`
- `sk.update-skill`
- `do.mettabox-ops`
- `relh.pr.merge-conflicts`
- `tr.policy-save-load-audit`
- `pr.summary`
- `r.make-package`
- `tr.recipe-curriculum-audit`
- `cb.review-main`
- `relh.tr.run-recipe`
- `db.run-and-triage`
- `cb.simplify-diff`
- `pr.sync-main`
- `cb.sync-nim-python`
- `t.run-tests`
- `db.test-triage`
- `do.worktrunk`

See each `skills/<name>/SKILL.md` for the full workflow.

## Editing Skills

Edit shared skills in `skills/`.
