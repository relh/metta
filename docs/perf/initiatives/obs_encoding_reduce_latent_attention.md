# Initiative: Reduce Latent Attention Cost In Observation Encoding

## Context

Mettabox profiling of `tests/perf/profile_observation_encoding.py` showed the Python observation encoding pipeline is
~36–45x slower than C++ observation encoding, and latent attention is the largest single component (CUDA mean ~274
us/step, ~45% of the pipeline in that run).

See: `docs/perf/observation_encoding_profile.md`.

## Goal

Reduce end-to-end observation encoding time per step without regressing training quality beyond acceptable bounds.

## Proposed Changes

- Reduce latent attention compute via architecture knobs:
  - fewer layers / heads
  - fewer query tokens
  - smaller latent dimension
- Evaluate cheaper alternatives (the profiling script already instantiates a perceiver path for comparison).
- Ensure any change is configurable and gated behind a config option for A/B testing.

Candidate code locations (to confirm):

- `agent/src/metta/agent/components/obs_enc.py` (attention encoder modules)
- Policy configs (e.g. `agent/src/metta/agent/policies/*.py`)

## Success Metrics

- `tests/perf/profile_observation_encoding.py` pipeline total decreases (especially `latent_attn`).
- End-to-end training SPS improves on cogsguard configs where observation encoding is on the critical path.

## Test Plan

- Add a perf comparison mode to the profiling script for multiple attention configurations.
- Run short training smoke tests to confirm no functional regressions.

## Risks / Notes

- This is a speed/quality tradeoff; require explicit metrics to decide acceptable degradation.
