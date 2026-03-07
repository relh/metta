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
| `hr.`   | Hiring / recruiting pipeline                         | hr.screen-resumes                   |
| `n.`    | Nishad-specific variants (only when truly personal)  | n.debug-jobs                        |
| `relh.` | Richard-specific variants (only when truly personal) | relh.cb.branch-hygiene              |
| `rl.research.` | RL research pipeline (full flow + phase skills) | rl.research.begin, rl.research.task-characterize |
| `rl.feature.` | RL feature build pipeline (spec → algorithm → launch) | rl.feature.build |
| `rl.improve.` | RL recipe improvement (diagnose → fix → launch → evaluate loop) | rl.improve.begin |
| `rl.analyze.` | RL training run analysis (signal planning + analysis) | rl.analyze.begin, rl.analyze.analyze |

## Rules

- Prefer the shared prefixes above; only use `n.`/`relh.` for clearly personal skills.
- If a skill touches multiple domains, pick the most central intent.
- If no prefix fits, propose a new prefix in this file before adding the skill.

## Skill catalog

- `cb.analyze-conciseness-opportunities`
- `cb.analyze-docs-plans`
- `cb.audit-cleanup-verify`
- `cb.cleanup-checkpoint-policy-integration`
- `cb.cleanup-concise-simplification`
- `cb.cleanup-docs-glanky-audit`
- `cb.cleanup-pr-sweep`
- `cb.cleanup-refactor`
- `cb.cleanup-targeted-surface`
- `cb.document-analysis-code-review-indirection`
- `cb.fix-add-doctor-check-stale-dispatch-hooks-doc`
- `cb.fix-agents-bootstrap`
- `cb.fix-any-find`
- `cb.fix-beads-redirect-avoid-chain-docs-optimization-opportunities`
- `cb.fix-benchmark-shows-improvement`
- `cb.fix-ci-c`
- `cb.fix-docs-detail`
- `cb.fix-failures-work-was-elsewhere`
- `cb.fix-mettagrid-preserve-per-aoe-filter-dependencies-tick-ordering`
- `cb.fix-miner-cargo-capacity`
- `cb.fix-planky-glanky-import-migration-rsik`
- `cb.fix-richard-address-correct`
- `cb.fix-scripted-agents-handle-split-primary-vibe-action-spaces`
- `cb.fix-sim-git-commit-recipes`
- `cb.implement-comprehensive-analysis-document`
- `cb.implement-config-opt-jobs-auto-verbose-failures-cpp-mettagrid`
- `cb.implement-dependencies-common`
- `cb.implement-docs-framework-something`
- `cb.implement-explicit-distance-weighting-junction-selection`
- `cb.implement-mode-docs-glanky-audit`
- `cb.implement-regicide-mode`
- `cb.implement-targeted-feature`
- `cb.lint-fix`
- `cb.review-main`
- `cb.simplify-diff`
- `cb.simplify-repo`
- `cb.sync-nim-python`
- `cf.bop-it`
- `cf.really`
- `cg.play`
- `cg.submit`
- `cg.test`
- `cm.web`
- `db.analyze-errors`
- `db.analyze-failed-checks-top`
- `db.cleanup-file-symlink-logging-warnings-failure`
- `db.document-error-code-more-details`
- `db.fix-error-exit-code-unknown-command-resolve`
- `db.fix-failed-exit-code-notification-read`
- `db.fix-failing-ci`
- `db.fix-traceback`
- `db.implement-failed-graphql-commits`
- `db.run-and-triage`
- `db.test-triage`
- `do.datadog-api-auth`
- `do.fix-alembic-startup-crash-move-migrations-pre-deploy-helm`
- `do.implement-deployment-dashboard`
- `do.kiosk-update`
- `do.mettabox-ops`
- `do.worktrunk`
- `hr.screen-resumes`
- `n.add-publishable-package`
- `n.add-season`
- `n.create-aws-account`
- `n.debug-jobs`
- `n.monitor-infra`
- `n.observatory-up`
- `n.setup-worktree-ide-themes`
- `pr.address-review`
- `pr.analyze-pr-reviews`
- `pr.bless`
- `pr.check-ci`
- `pr.cleanup-conflict-resolution`
- `pr.conform`
- `pr.context`
- `pr.context-cool`
- `pr.cool`
- `pr.document-pr-merged`
- `pr.fix-any-weird-conflicts-auditing`
- `pr.fix-author-prs`
- `pr.fix-branch`
- `pr.fix-branch.team`
- `pr.fix-ci`
- `pr.fix-comments`
- `pr.fix-conflicts-keep-additions`
- `pr.fix-github-pr-comments`
- `pr.fix-merge-conflicts-keeping-changes`
- `pr.fix-pr-meaningful`
- `pr.fix-prs`
- `pr.submit`
- `pr.submit-docsdocs-updates`
- `pr.submit-fixes-gas`
- `pr.submit-stats-policies-presigned-url`
- `pr.summary`
- `pr.sync-conflicts-wise-continue`
- `pr.sync-error-failed-database-enable-wal-mode`
- `pr.sync-high-priority-bug-fix-branches`
- `pr.sync-main`
- `pr.sync-merge`
- `pr.sync-remote-tracking-corpse-skeleton-merge`
- `r.make-package`
- `relh.cb.branch-hygiene`
- `relh.pr.merge-conflicts`
- `relh.tr.run-recipe`
- `rl.analyze.analyze`
- `rl.analyze.begin`
- `rl.feature.build`
- `rl.improve.begin`
- `rl.research.begin`
- `rl.research.deep-research`
- `rl.research.literature-review`
- `rl.research.synthesize`
- `rl.research.task-characterize`
- `sk.implement-docs-skills`
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
- `t.analyze-failing-tests-now`
- `t.cleanup-test-stopwatch-tests`
- `t.cleanup-tests-sharing-logic`
- `t.fix-any-curriculum-tests-may-failing`
- `t.fix-run-pytest-packages-mettagrid-tests-test-weighted-territory`
- `t.fix-test-failures`
- `t.fix-tests-role-distribution-match`
- `t.implement-ci-test-cogames-package-works-after-pub`
- `t.implement-comprehensive-tests-scripted-agent-behaviors`
- `t.implement-mode-tests-domain`
- `t.implement-packages-mettagrid-tests-test-aoe`
- `t.implement-test-issue-warning-beads`
- `t.implement-tests`
- `t.implement-unit-tests-coordination`
- `t.run-tests`
- `t.test-all-policies`
- `t.test-ci`
- `t.test-error-cogas-agents-tests`
- `t.test-failed-tests-cogsguard-roles`
- `t.test-failing-tests`
- `t.test-failure-emergencyminegoal`
- `t.test-failures-checks-template-incomplete`
- `t.test-files-corresponding-src`
- `t.test-issue-setup`
- `t.test-newest-checkpoint`
- `t.test-perf`
- `t.test-performance-one-seed-now`
- `t.test-pr-checkpoint-policy-core-see`
- `t.test-qualifying-cogas`
- `t.test-scenarios`
- `t.test-tests-pass`
- `t.test-them-failing-lint`
- `tr.analyze-glanky-planky-performance-gaps`
- `tr.analyze-hot-loops-performance-optimizations`
- `tr.analyze-performance-step-see-what-dominating`
- `tr.checkpoint-find`
- `tr.cogames-command`
- `tr.cogames-variant-debug`
- `tr.document-perf-folder`
- `tr.document-performance-analysis`
- `tr.fix-agent-performance-regressions`
- `tr.fix-benchmark-run-cog-eval-after-all-merged-fixes`
- `tr.implement-mode-cogames-agents-docs`
- `tr.implement-training-time`
- `tr.perf-eval`
- `tr.perf-eval-env`
- `tr.perf-scorecard`
- `tr.policy-save-load-audit`
- `tr.recipe-curriculum-audit`
- `tr.wandb-analyze`
- `tr.wandb-inspect`
- `wt.cleanup`
- `wt.fix-correct-beads-redirect-path-worktree-resolve-merge`
