# Cogames Diagnose Audit (2026-02-23)

## Scope

Audit of current implementation against the Thread Vision spec for Cogames Diagnose, across:

- Diagnose engine: `packages/cogames/src/cogames/diagnose.py`
- Vibeservatory backend diagnose API: `vibeservatory/backend/dashboard_backend/cogames_diagnose/router.py`
- Dashboard frontend diagnose views:
  - `dashboard/src/components/CogamesDiagnosePanel.tsx`
  - `diagnose/src/app/page.tsx`
  - `diagnose/src/app/[runId]/page.tsx`
  - `dashboard/src/lib/api.ts`

## Summary Verdict

Overall status: **partially compliant; core pipeline is strong, dashboard presentation/serving has correctness gaps**.

- The diagnose engine already enforces a two-stage flow, stage gating, required social follow-up, validity artifacts,
  doctor-note outputs, and replay bundles.
- The dashboard diagnose tab/backend has several high-impact correctness issues (score scaling, replay evidence logic,
  nested artifact serving, and missing surfacing of critical social/validity context).

## What the Spec Asked For (and Current Status)

### 1) Diagnose as doctor visit + fantasy stat card

Requested:

- Compact behavioral screening suite
- At-a-glance axes + spider/radar chart
- Ranked symptoms + concrete prescriptions

Status: **Mostly implemented**

- Doctor note schema includes axes, ranked symptoms, prescriptions, evidence refs, and exemplars.
- HTML report includes radar chart and triage section.
- Dashboard panel includes a spider chart and grouped probe/symptom/prescription cards.

Notes:

- Dashboard chart/percentage rendering currently has scaling defects (documented in Findings).

### 2) Two-stage pipeline (Individual -> Social) with strict gating

Requested:

- Stage 1 individual psych review first
- Stage 2 social psych review required follow-up
- Block final prescription when stage evidence is incomplete

Status: **Implemented in diagnose engine**

- Stage 1 gate by required axes/missions.
- Stage 2 only runs after Stage 1 passes gate + replay evidence + confirmed signals.
- Incomplete states are explicitly persisted and final completion withheld when evidence is insufficient.

### 3) Stage 1 probe requirements and evidence

Requested:

- Confirmed signals for stability, efficiency, control
- Replay-backed evidence
- Concrete probe framing

Status: **Implemented**

- Stage 1 pack requires at least one probe mission per core axis.
- Stage 1 signals require both metrics and replay evidence.
- Probe catalog and threshold evaluations are emitted.

### 4) Stage 2 social review requirements

Requested:

- Absolute scrimmage mode + mirror mode
- Coordination/interference/adaptation questions
- Follow-up that confirms or changes diagnosis

Status: **Implemented, with one caveat**

- Absolute and mirror runs are both executed and required in validity checks.
- Social signal severity/confidence and diagnosis delta are emitted.
- Caveat: social probe IDs/validation metrics are currently catalog descriptors; they are not yet directly computed by
  dedicated probe-specific telemetry metrics.

### 5) Doctor note canonical schema

Requested fields:

- `symptom_id, axis, severity, confidence, evidence_refs, likely cause, action, expected effect`
- prescription fields: `action, owner, validation metric, pass/fail threshold`

Status: **Implemented**

- Current models and output fields map closely to requested schema.

### 6) Evaluation signals + fixed reproducible pack

Requested:

- Tournament-aligned signals, especially `aligned.junction.held`
- Fixed mission/cogs/steps/episodes/seeds pack
- Invalid if required pack elements missing

Status: **Partially implemented**

- `aligned.junction.held` context is tracked and shown.
- Fixed seeds are encoded.
- Pack contract checker exists and is written to artifact.
- Gap: pack contract mismatch does not currently hard-fail completion (standalone mode continues).

### 7) Required output bundle and reproducibility

Requested:

- JSON outputs + replay bundle + single HTML report
- Shareable and reproducible

Status: **Implemented**

- `doctor_note.json`, `manifest.json`, `diagnose_report.html`, `replay_bundle.zip`, validity/stability JSONs, and
  supporting artifacts are generated.

### 8) Dashboard diagnose tab sufficiency

Requested outcome:

- Decision-ready diagnosis quickly in dashboard

Status: **Partially sufficient**

- Core objects load and render.
- Critical context is omitted or miscomputed in current tab (see Findings).

## Findings (ordered by severity)

1. **Dashboard score scaling is incorrect**

- `normalized_score` is already 0..100 but dashboard formatting multiplies by 100 again.
- Radar chart path also clamps 0..100 values as if they were 0..1, saturating the polygon.

Impact:

- Distorts all axis interpretation in the Diagnose tab and run page.

2. **Dashboard replay evidence gate is derived from wrong field**

- Diagnose panel infers replay evidence from `stage1_probe_evaluations.evidence_refs`.
- Those refs are mostly metric strings, not replay refs; replay refs are in `doctor_note.evidence_index.replay_refs`.

Impact:

- Stage-2 gate/validity display can report false blocked/invalid state.

3. **Vibeservatory backend artifact route cannot serve nested artifact paths**

- Route pattern + artifact regex only allow flat file names.
- Manifest can contain nested artifacts (for example `replays/...`), but API rejects path separators.

Impact:

- Inability to fetch nested artifacts directly from Vibeservatory backend.

4. **Diagnose tab omits key decision context already available in artifacts**

Not surfaced in tab:

- Social review summary/severity/confidence and Stage-2 diagnosis delta
- Tournament objective context (`aligned.junction.held` stage1/absolute/mirror)
- Validity and interpretation stability summaries (`diagnose_validity`, `interpretation_stability`)

Impact:

- Reduces decision readiness and traceability vs intended doctor-note workflow.

5. **Fixed pack contract is advisory rather than a hard final validity gate**

- Engine emits contract checks but allows run continuation/completion in standalone mode on mismatch.

Impact:

- Weakens strict compliance with fixed-pack reproducibility requirement.

## Evidence references (code)

- Diagnose pipeline, gating, social review, artifacts:
  - `packages/cogames/src/cogames/diagnose.py`
- Dashboard diagnose backend routes:
  - `vibeservatory/backend/dashboard_backend/cogames_diagnose/router.py`
- Dashboard diagnose views/API types:
  - `dashboard/src/components/CogamesDiagnosePanel.tsx`
  - `diagnose/src/app/[runId]/page.tsx`
  - `dashboard/src/lib/api.ts`

## Tests executed during audit

- `uv run pytest packages/cogames/tests/test_diagnose_stage1.py -q` -> `14 passed`
- `uv run pytest tests/vibeservatory/backend/cogames_diagnose/test_router.py -q` -> `2 passed`

## Immediate remediation plan

1. Fix dashboard axis percentage/radar scaling logic.
2. Fix dashboard replay evidence derivation to use canonical replay refs.
3. Update backend artifact routing to safely support nested artifact paths.
4. Surface social review + objective context + validity/stability in diagnose UI.

(Optionally next: make pack-contract mismatch a strict invalid/fail gate in diagnose engine.)
