export type DiagnoseAxis = 'stability' | 'efficiency' | 'control' | 'social_coordination'

export type DiagnoseStageStatus =
  | 'stage1_running'
  | 'stage1_passed_for_social'
  | 'stage1_incomplete'
  | 'stage2_running'
  | 'stage2_completed'
  | 'stage2_incomplete'

export type DiagnoseRunStatus = 'incomplete' | 'complete'

export type DoctorNoteStatus = 'complete' | 'incomplete'

export type Stage1AxisDerivedMetrics = {
  reward_variance: number
  non_zero_episode_pct: number
  timeout_rate: number
  mean_move_success: number
  mean_action_failed: number
  mean_stuck_steps: number
}

export type Stage1AxisScore = {
  axis: DiagnoseAxis
  normalized_score: number
  raw_score: number
  confirmed: boolean
  derived_metrics: Stage1AxisDerivedMetrics
  metric_refs: string[]
  replay_refs: string[]
  baseline_refs: string[]
  baseline_coverage_count: number
  normalization_mode: string
}

export type Stage1ProbeThresholdRule = {
  metric: string
  operator: string
  value: number
}

export type Stage1ProbeDefinition = {
  probe_id: string
  axis: DiagnoseAxis
  mission: string
  scenario: string
  question: string
  validation_metric: string
  pass_fail_threshold: string
  threshold_rules: Stage1ProbeThresholdRule[]
}

export type Stage1ProbeEvaluation = {
  probe_id: string
  axis: DiagnoseAxis
  mission: string
  passed: boolean
  summary: string
  evidence_refs: string[]
}

export type DiagnoseSymptomEvidenceRefs = {
  metric_refs: string[]
  replay_refs: string[]
}

export type DiagnoseSymptom = {
  symptom_id: string
  axis: DiagnoseAxis
  severity: number
  confidence: number
  evidence_refs: DiagnoseSymptomEvidenceRefs
  likely_cause: string
  action: string
  expected_effect: string
}

export type DiagnosePrescription = {
  symptom_id: string
  action: string
  owner: string
  validation_metric: string
  pass_fail_threshold: string
}

export type DiagnoseDoctorNote = {
  schema_version: string
  run_id: string
  status: DoctorNoteStatus
  stage_status: DiagnoseStageStatus
  diagnosis_status: string | null
  dominant_issue: string
  axes: Stage1AxisScore[]
  stage1_probe_threshold_profile_id: string
  stage1_probe_catalog: Stage1ProbeDefinition[]
  stage1_probe_evaluations: Stage1ProbeEvaluation[]
  symptoms: DiagnoseSymptom[]
  prescriptions: DiagnosePrescription[]
  evidence_index: Record<string, string[]>
  missing_requirements: unknown[]
  notes: string[]
}

export type DiagnoseValidityCheck = {
  check_id: string
  passed: boolean
  details: string
}

export type DiagnoseValidityReport = {
  valid: boolean
  failed_check_ids: string[]
  checks: DiagnoseValidityCheck[]
}

export type InterpretationSnapshot = {
  label: string
  run_id: string
  dominant_issue: string
  top_symptom_ids: string[]
}

export type InterpretationStabilityReport = {
  snapshot_count: number
  compared_run_ids: string[]
  dominant_issue_stable: boolean
  top_symptom_stable: boolean
  stable: boolean
  notes: string[]
  snapshots: InterpretationSnapshot[]
}

export type DiagnoseManifest = {
  schema_version: string
  run_id: string
  created_at: string
  command: string
  git_sha: string | null
  pack_id: string
  pack_version: string
  mission_set: string
  policy: string
  scripted_baseline_policy: string | null
  known_strong_policy: string | null
  stage_status: DiagnoseStageStatus
  run_status: DiagnoseRunStatus
  seeds: Record<string, number>
  artifact_files: string[]
  interpretation_stability: InterpretationStabilityReport
  diagnose_validity: DiagnoseValidityReport
}
