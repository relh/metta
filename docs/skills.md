# Skill Namespaces

This repo uses dot-separated namespaces for skill names (e.g., `pr.fix-ci`).

## Prefix map

| Prefix  | Domain / Intent                                      | Examples                            |
| ------- | ---------------------------------------------------- | ----------------------------------- |
| `pr.`   | PR/Graphite/GitHub workflow                          | pr.fix-ci, pr.summary               |
| `st.`   | Stack management (Graphite stacks)                   | st.make-stack, st.split             |
| `tr.`   | Training / run orchestration                         | tr.cogames-command                  |
| `db.`   | Debugging / triage                                   | db.fix-traceback                    |
| `do.`   | DevOps / infra / ops                                 | do.kiosk-update, do.mettabox-ops    |
| `cb.`   | Codebase analysis/refactor/cleanup                   | cb.review-main, cb.cleanup-refactor |
| `cg.`   | CoGames play / submit / dashboard                    | cg.play, cg.submit                  |
| `sk.`   | Skill management (create/update/submit/sync skills)  | sk.make-skill, sk.submit-skill      |
| `t.`    | Testing                                              | t.run-tests                         |
| `wt.`   | Git worktree utilities                               | wt.cleanup                          |
| `r.`    | Repo scaffolding / package creation                  | r.make-package                      |
| `cf.`   | Control-flow / meta-execution                        | cf.really                           |
| `n.`    | Nishad-specific variants (only when truly personal)  | n.debug-jobs                        |
| `relh.` | Richard-specific variants (only when truly personal) | relh.cb.branch-hygiene              |

## Rules

- Prefer the shared prefixes above; only use `n.`/`relh.` for clearly personal skills.
- If a skill touches multiple domains, pick the most central intent.
- If no prefix fits, propose a new prefix in this file before adding the skill.

## Skill catalog

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
- `cg.test`
- `db.fix-traceback`
- `db.run-and-triage`
- `db.test-triage`
- `do.datadog-api-auth`
- `do.kiosk-update`
- `do.mettabox-ops`
- `do.worktrunk`
- `n.add-publishable-package`
- `n.add-season`
- `n.debug-jobs`
- `n.monitor-infra`
- `n.observatory-up`
- `n.setup-worktree-ide-themes`
- `pr.address-review`
- `pr.check-ci`
- `pr.conform`
- `pr.context`
- `pr.context-cool`
- `pr.cool`
- `pr.fix-branch`
- `pr.fix-branch.team`
- `pr.fix-ci`
- `pr.fix-comments`
- `pr.submit`
- `pr.summary`
- `pr.sync-main`
- `r.make-package`
- `sk.learn-skills`
- `sk.make-skill`
- `sk.submit-skill`
- `sk.sync-skills`
- `sk.update-skill`
- `st.apply`
- `st.extract`
- `st.extract-copy`
- `st.fix-stack`
- `st.fix-stack.team`
- `st.graphite-stack`
- `st.issue-to-stack`
- `st.make-stack`
- `st.split`
- `t.run-tests`
- `tr.checkpoint-find`
- `tr.cogames-command`
- `tr.cogames-variant-debug`
- `tr.perf-eval`
- `tr.perf-eval-env`
- `tr.perf-scorecard`
- `tr.policy-save-load-audit`
- `tr.recipe-curriculum-audit`
- `tr.wandb-inspect`
- `wt.cleanup`

## When creating a new skill

- Always read this file first and select the namespace from the table.
- Use the chosen prefix in the directory name and the `name:` field in `SKILL.md`.
