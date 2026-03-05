---
name: tr.fix-benchmark-run-cog-eval-after-all-merged-fixes
description: 'Use when fixing benchmark run cog eval after merged fixes.'
---

# Fix Benchmark Run Cog Eval After All Merged Fixes

## Trigger

- Primary: "benchmark re run cog eval after all merged fixes fallbackminegoal"
- Variant: "benchmark re run cog eval after all merged fixes"
- Variant: "benchmark post fix evaluation of cogas agents after all merged"
- Variant: "benchmark results for cog eval 2272bcb docs incorporate wombo mix"

## Workflow

- Re-run the canonical cog eval with fixed seeds, fixed checkpoints, and identical runtime settings.
- Compare against the branch baseline using the same metrics (win rate, score, SPS, and runtime stability).
- If results regress, trace to changed components and run targeted follow-up experiments before claiming fixes.
- Publish a benchmark summary with commands, artifacts, and a clear go/no-go conclusion.
