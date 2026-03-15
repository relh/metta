# Cogames Diagnose Verification (2026-02-24)

## Scope

Validate that `cogames diagnose` runs end-to-end (Stage 1 gate -> Stage 2 social review), writes the expected artifact
bundle, and reports valid completion.

## Commands Run

### Unit/integration coverage

```bash
uv run pytest packages/cogames/tests/test_diagnose_stage1.py -q
uv run pytest tests/vibeservatory/backend/cogames_diagnose/test_router.py -q
```

### Live smoke run (compact)

```bash
uv run cogames diagnose class=random \
  --mission-set cvc_evals \
  --experiments eval_balanced_spread \
  --experiments eval_collect_resources \
  --experiments eval_divide_and_conquer \
  --steps 200 \
  --episodes 1 \
  --output-dir outputs/cogames-diagnose/smoke-20260224
```

### Live negative-path gate run (expected incomplete)

```bash
uv run cogames diagnose class=random \
  --mission-set diagnostic_evals \
  --experiments diagnostic_chest_navigation1 \
  --steps 50 \
  --episodes 1 \
  --output-dir outputs/cogames-diagnose/smoke-negative-20260224
```

### Full default-pack run (full Stage 1 + Stage 2)

```bash
uv run cogames diagnose class=random \
  --mission-set cvc_evals \
  --output-dir outputs/cogames-diagnose/full-20260224
```

### Post-fix compact run (contract expected to fail)

```bash
uv run cogames diagnose class=random \
  --mission-set cvc_evals \
  --experiments eval_balanced_spread \
  --experiments eval_collect_resources \
  --experiments eval_divide_and_conquer \
  --steps 200 \
  --episodes 1 \
  --output-dir outputs/cogames-diagnose/smoke-contract-check-20260224
```

### Post-fix full default-pack run (contract expected to pass)

```bash
uv run cogames diagnose class=random \
  --mission-set cvc_evals \
  --output-dir outputs/cogames-diagnose/full-contract-check-20260224
```

## Results

### Tests

- `packages/cogames/tests/test_diagnose_stage1.py`: `24 passed`
- `tests/vibeservatory/backend/cogames_diagnose/test_router.py`: `4 passed`

### Live smoke diagnose run

- Run ID: `20260224-153041-bd296cb6`
- Output dir: `outputs/cogames-diagnose/smoke-20260224`
- Final stage status: `stage2_completed`
- Final run status: `complete`
- Diagnose validity: `true`
- Failed validity checks: `[]`
- Doctor note status: `complete`
- Diagnosis status: `diagnosis_complete`
- Dominant issue: `strategy`
- Social review: `confirmed=true`

### Live negative-path diagnose run

- Output dir: `outputs/cogames-diagnose/smoke-negative-20260224`
- Final stage status: `stage1_incomplete`
- Final run status: `incomplete`
- Diagnosis status: `diagnosis_incomplete`
- Missing Stage 1 requirements: `3`
- Prescriptions generated: `0` (expected for incomplete diagnosis)

### Full default-pack diagnose run

- Run ID: `20260224-153428-e46bda34`
- Output dir: `outputs/cogames-diagnose/full-20260224`
- Runtime (wall): `3:38.36`
- Final stage status: `stage2_completed`
- Final run status: `complete`
- Diagnose validity: `true`
- Failed validity checks: `[]`
- Stage 1 replay evidence: `45/45`
- Stage 2 replay evidence: `90/90`
- Diagnosis status: `diagnosis_complete`
- Dominant issue: `mixed`
- Top symptoms: `stage1.efficiency.risk`, `stage1.control.risk` (severity `0.33`, confidence `0.87`)
- Stage 1 probe outcomes:
  - `stage1.food_under_pressure`: passed
  - `stage1.heart_lever_diversion`: failed
  - `stage1.junction_light_shift`: failed
- Social review: `confirmed=true`, `severity=0.0`, diagnosis delta `changed=false`
- Interpretation stability artifact: `stable=false` with `snapshot_count=1` (expected without reruns/compare-run dirs)

## Artifact bundle present

Verified these outputs exist:

- `doctor_note.json`
- `diagnose_report.html`
- `manifest.json`
- `replay_bundle.zip`
- `diagnose_validity.json`
- `interpretation_stability.json`
- `metrics.json`
- `stage1_*` and `stage2_*` summaries/signals
- replay dirs: `replays/`, `replays_stage2/`

## Notes

- This smoke run intentionally used non-default `steps`/`episodes` to reduce runtime.
- The compact smoke run metrics above were captured before contract-enforced validity was added.
- Negative-path run confirms Stage 1 gate blocking behavior when mission set/probes do not satisfy pack requirements.
- Full default-pack run completed without runtime failures.

## Post-fix Verification (Contract-Enforced Validity)

After tightening validity checks to require a passing fixed-pack contract:

- Compact non-pack run (steps/episodes overridden and experiment subset):
  - Output dir: `outputs/cogames-diagnose/smoke-contract-check-20260224`
  - Final stage/run: `stage2_completed` / `complete`
  - `diagnose_validity.valid`: `false`
  - failed checks: `["stage1.pack_contract"]`
- Full default-pack run:
  - Output dir: `outputs/cogames-diagnose/full-contract-check-20260224`
  - Runtime (wall): `3:52.86`
  - Final stage/run: `stage2_completed` / `complete`
  - `diagnose_validity.valid`: `true`
  - failed checks: `[]`
