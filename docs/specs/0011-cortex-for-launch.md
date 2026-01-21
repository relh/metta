# Kickstarting for Launch

> **Status:** Draft **Author:** Subho **Created:** 2026-01-15

## Summary

Cortex is the core agent-architecture library used for both kickstarting and the subsequent reinforcement learning (RL)
stage. Prior to launching the public-facing leaderboard, we aim to:

1. Train and compare multiple Cortex architecture configurations on the new game, including hybrid variants that
   previously demonstrated strong performance (e.g., Ag,S,A on `machina_1`), in order to identify reliable default
   configurations.

2. Establish the practical limits on model size for both training and leaderboard evaluation, targeting architectures in
   the range of 2M to 100M parameters, so that supported limits can be clearly communicated (e.g., "leaderboard supports
   models up to 100M parameters").

This document defines the pre-launch success criteria and the post-launch dissemination and experimentation plan.

## Problem

A public leaderboard is expected to receive submissions spanning a wide range of policy architectures, training
strategies, and model sizes. Without sufficient validation prior to launch, several risks arise:

- The absence of a well-supported default configuration at launch.
- Uncertainty regarding whether previously successful hybrid architectures (notably Ag,S,A) generalize to the new game.
- Insufficient understanding of the feasible upper bounds on model size for end-to-end training and evaluation.
- Inadequate communication of system limits, leading to user confusion or unsupported submissions.

To mitigate these risks, we require empirically validated defaults and a clearly defined statement of supported scale
before the leaderboard becomes public.

## Solution

### Pre-launch

- Conduct an architecture sweep of relevant Cortex variants on the new game, including hybrid configurations.
- Train small and large architecture variants (2M–100M parameters) and confirm that models across this range can be
  successfully trained and evaluated on the leaderboard.
- Publish explicit documentation specifying supported model sizes and recommended default configurations.

### Post-launch

- Produce a public-facing write-up (research paper) describing the Cortex library, the kickstarting-to-RL training
  approach, and empirical results on the new game (during cooling week).
- Polish the repository.
- Continue targeted experiments to generate deeper ablations, robustness analyses, and scaling results suitable for
  publication.

## Goals

- [ ] Architecture validation: Evaluate a representative set of Cortex architectures, including Ag,S,A and selected
      non-hybrid baselines, using a consistent training and evaluation pipeline.
- [ ] Scale validation: Demonstrate successful training and leaderboard evaluation at 2M, ~10M, ~50M, and ~100M
      parameters (or the nearest feasible equivalents) using our current kickstarting + RL recipe.
- [ ] Launch documentation: Update leaderboard documentation with a clear statement of supported model sizes and
      recommended defaults.

## Non-Goals

- Performing an exhaustive hyperparameter search.
- Designing or introducing new learning algorithms beyond the existing Cortex and kickstarting/RL framework.
- Optimizing compute cost or performance beyond what is required for stability and clarity at launch.
- Addressing all potential adversarial or pathological submissions at launch.

## Spec Process Notes

- The status field is used for internal tracking; the spec may be merged while still in Draft.
- No specific review or approval tool is prescribed.

## Design

### Pre-launch plan

#### A. Architecture Validation

- **Setup:** Utilize an existing kickstarting recipe/environment with reward shaping.
- **Sweep:** Run a sweep over various architecture variants (including hybrid variants like Ag,S,A) to identify if the
  defaults need change.
- **Outcome:** Identify stable, competitive default configurations for the new game.

#### B. Scale Validation

- **Sweep:** Train various architecture sizes (2M, 10M, 50M, 90M parameters) using the best identified architecture
  configuration.
- **Verification:** Confirm that models across this range can be successfully trained and evaluated on the leaderboard.
- **Limits:** Establish practical upper bounds for model size.

#### C. Documentation & Deliverables

- **Documentation:** Publish explicit guidance on supported model sizes and recommended defaults.
- **Deliverables:** A "Launch Defaults" configuration bundle and a results table.

### Post-launch plan

#### Research Paper & Repository Polish

Produce a research paper (to be written during the cooling week immediately after launch) and polish the repository.

**Experimental Structure for the Paper:**

**1. ICL / Memory-Focused Environments** Ablate architecture components using memory-intensive environments. Run sweeps
(approx. 5 seeds per variant) along:

- **Axis A (Composition):** Compare single-mechanism stacks (Associative: X, M) vs. heterogeneous column stacks (e.g.,
  Ag, A, S).
- **Axis B (Mechanism):** Ablate Axon components (A experts and ^ projections) to measure performance under strict
  TBPTT.
- **Scaling:** Vary column width and stack depth.

**2. CvC Evaluation** Train best-performing candidates from Section 1 on CvC using curricula. Compare against
single-cell baselines (e.g., LSTM, XLCell). No extensive sweeping here; focus on direct comparison.

**3. External Environments** Replicate evaluations from Section 2 in external environments like Craftax or Memory Gym.
