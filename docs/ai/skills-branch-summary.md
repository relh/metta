# Skills Branch Summary (2026-03-04)

This summary reflects the post-prune state of this branch.

## TL;DR

- We reduced branch-added skills from `915` to `98` to keep the set reviewable and high-signal.
- We kept the strongest alias families by trigger density and removed low-signal one-offs.
- We ran a second-pass recovery and added back a small set of under-covered families.
- We upgraded key kept skills with domain-specific workflows (mettagrid/C++ hotloop, perf protocol, merge and ops
  policy).

## What Changed

Compared with `origin/main`:

- Added skills: `98`
- Modified existing skills: `3`
- Deleted existing skills: `0`

Modified existing skills:

- `cb.review-main`
- `pr.fix-branch`
- `pr.sync-main`

Complete skill list lives in [docs/skills.md](../skills.md).

## Keep Criteria

The cleanup used a concrete selection rule:

1. Keep branch-added skills with `>=2` trigger variants (higher observed routing signal).
2. Add back a small number of specialized mettagrid/perf skills even with fewer variants.
3. Do a second pass and restore a few low-variant skills only when they cover under-represented families.
4. Remove the rest of the branch-added one-off aliases.

Result:

- Initial branch-added skills: `915`
- Kept from high-signal rule: `82`
- Specialized add-backs: `5`
- Second-pass under-coverage add-backs: `11`
- Final branch-added set: `98`

## Added Skills By Area

- `cb`: 29
- `db`: 8
- `do`: 2
- `pr`: 17
- `sk`: 1
- `t`: 31
- `tr`: 9
- `wt`: 1

Most common action groups:

- `t.test`: 17
- `cb.fix`: 14
- `cb.implement`: 8
- `t.implement`: 7
- `pr.fix`: 6

## Domain-Specific Workflow Upgrades

These kept skills were rewritten with concrete domain instructions:

- `cb.fix-mettagrid-preserve-per-aoe-filter-dependencies-tick-ordering`
- `cb.implement-config-opt-jobs-auto-verbose-failures-cpp-mettagrid`
- `t.fix-run-pytest-packages-mettagrid-tests-test-weighted-territory`
- `t.implement-packages-mettagrid-tests-test-aoe`
- `tr.analyze-hot-loops-performance-optimizations`
- `tr.fix-benchmark-run-cog-eval-after-all-merged-fixes`
- `t.test-perf`
- `t.test-performance-one-seed-now`
- `pr.sync-remote-tracking-corpse-skeleton-merge`
- `pr.fix-conflicts-keep-additions`
- `do.fix-alembic-startup-crash-move-migrations-pre-deploy-helm`
- `do.implement-deployment-dashboard`
- `db.cleanup-file-symlink-logging-warnings-failure`
- `wt.fix-correct-beads-redirect-path-worktree-resolve-merge`
- `tr.fix-agent-performance-regressions`
