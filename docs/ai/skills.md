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

- `cb.audit-cleanup-verify`
- `cb.cleanup-pr-sweep`
- `cb.cleanup-refactor`
- `cb.lint-fix`
- `cb.review-main`
- `cb.simplify-diff`
- `cb.sync-nim-python`
- `cf.bop-it`
- `cf.really`
- `cg.play`
- `cg.policy-dashboard`
- `cg.submit`
- `db.fix-traceback`
- `db.run-and-triage`
- `db.test-triage`
- `do.datadog-api-auth`
- `do.kiosk-update`
- `do.mettabox-ops`
- `do.worktrunk`
- `n.add-publishable-package`
- `n.add-season`
- `n.setup-worktree-ide-themes`
- `n.debug-jobs`
- `n.monitor-infra`
- `n.observatory-up`
- `pr.address-review`
- `pr.check-ci`
- `pr.context`
- `pr.context-cool`
- `pr.cool`
- `pr.fix-author-prs`
- `pr.fix-branch`
- `pr.fix-ci`
- `pr.fix-comments`
- `pr.submit`
- `pr.summary`
- `pr.sync-main`
- `r.make-package`
- `relh.cb.branch-hygiene`
- `relh.pr.merge-conflicts`
- `relh.tr.run-recipe`
- `sk.learn-skills`
- `sk.make-skill`
- `sk.submit-skill`
- `sk.sync-skills`
- `sk.update-skill`
- `st.apply`
- `st.extract`
- `st.extract-copy`
- `st.fix-stack`
- `st.graphite-stack`
- `st.issue-to-stack`
- `st.make-stack`
- `st.split`
- `t.run-tests`
- `tr.checkpoint-find`
- `tr.cogames-command`
- `tr.cogames-variant-debug`
- `tr.perf-eval`
- `tr.policy-save-load-audit`
- `tr.recipe-curriculum-audit`
- `tr.wandb-inspect`
- `wt.cleanup`

See each `skills/<name>/SKILL.md` for the full workflow.

## Editing Skills

Edit shared skills in `skills/`.
