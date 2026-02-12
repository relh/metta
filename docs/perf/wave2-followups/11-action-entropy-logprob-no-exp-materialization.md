# Action Follow-Up 2: Avoid Full `exp(log_softmax)` Materialization

## Area

`#6908` Action processing

## Hypothesis

Building full `action_probs = exp(log_softmax(logits))` adds memory traffic and kernels. Rewriting log-prob/entropy
computation to minimize intermediate tensors should reduce latency.

## Proposed Change

Refactor `sample_actions` and `evaluate_actions` math to avoid unnecessary full-probability tensor materialization where
possible, while preserving numerical stability.

## Code Touch Points

- `agent/src/metta/agent/util/distribution_utils.py`
- `agent/tests/util/test_distribution_utils.py`

## Benchmark Plan

1. Microbench old vs new functions at multiple batch sizes/action counts.
2. Run unit tests for numerical equivalence.
3. Measure:

- kernel time and memory bandwidth proxy
- end-to-end action pipeline throughput

## Success Criteria

- > = 10% latency reduction in `evaluate_actions` or `sample_actions`
- numerically stable outputs (tight tolerance)
- no training loss instability from numeric drift

## Guardrails

- Prefer stable `logsumexp`-based formulas.
- Include explicit correctness tests for edge logits.
