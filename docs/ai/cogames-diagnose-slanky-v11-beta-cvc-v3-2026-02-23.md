# Cogames Diagnose Findings: slanky v11 (beta-cvc-v3)

Date: 2026-02-23 Branch: `richard-new-diagnose`

## Run Executed

```bash
uv run cogames diagnose "metta://policy/slanky:v11" --mission-set cogsguard_evals
```

Resolved policy artifact:

- `s3://observatory-private/cogames/submissions/s5hvylinkg2z4k24wg9xlo8q/f9c7205f-f793-4ba0-ae46-c0d9d13d174d.zip`

Local run output:

- `outputs/cogames-diagnose/20260223-233046-7cfe1fb7`

## Headline Diagnosis

From `doctor_note.json` and `manifest.json`:

- `run_status`: `complete`
- `stage_status`: `stage2_completed`
- `diagnose_validity.valid`: `true`
- `diagnosis_status`: `diagnosis_complete`
- `dominant_issue`: `strategy`

## Axis Profile (normalized scores)

- Stability: `100.00` (confirmed)
- Efficiency: `85.56` (confirmed)
- Control: `66.67` (confirmed, weakest axis)

Derived summary:

- reward variance: `3.785e-05`
- non-zero episode %: `100.0`
- timeout rate: `0.0`

## Top Symptom + Prescription

Top symptom:

- `symptom_id`: `stage1.control.risk`
- axis: `control`
- severity: `0.33`
- confidence: `0.87`
- likely cause: `Action selection is error-prone under pressure.`

Primary prescription:

- owner: `policy_researcher`
- action: `Reduce invalid actions and improve decision timing on high-risk interactions.`
- validation metric / threshold: `control.normalized_score >= 80 and action.failed <= 0.08`

## Stage-2 Social Follow-up

Social review:

- confirmed: `true`
- severity: `0.0`
- confidence: `0.85`
- summary: `Social scrimmage confirms Stage 1 diagnosis without major coordination regressions.`

Evidence refs:

- `absolute:policy_reward_mean=0.3789`
- `mirror:policy_reward_mean=0.3776`
- `mirror:policy_reward_gap=0.0000`
- `absolute:timeout_rate=0.0000`
- `mirror:timeout_rate=0.0000`

Diagnosis delta:

- stage1 dominant issue: `strategy`
- final dominant issue: `strategy`
- changed: `false`

## Probe-Level Flag

One Stage-1 control probe failed:

- `probe_id`: `stage1.junction_light_shift`
- failed evidence: `eval_divide_and_conquer:mean_action_failed=253.3750 (<= 0.2000)`

This aligns with the `control` axis being the weakest profile dimension.

## Replay Exemplar Pointers

From `doctor_note.replay_exemplars`:

- best: `replays/23cdccaa-5ee9-4adc-95e2-94cd76084d3a.json.z`
- worst: `replays/a3c410d4-ed3a-4ea4-b7b9-9400f70595d0.json.z`
- most_diagnostic: `replays/13271dfa-5a0d-4cd5-892d-8c839c4d95f8.json.z`

## Dashboard Representation Added

Diagnose tab now includes a compact **Run Findings Snapshot** card:

- dominant issue + diagnosis status
- top symptom (ranked by severity)
- primary prescription (symptom-linked where available)
- Stage-2 social confirmation line with absolute/mirror reward means and mirror gap
- per-axis horizontal bars over normalized scores

This is meant to give an at-a-glance doctor-note read in the policy dashboard before drilling into full probe/symptom
sections.
