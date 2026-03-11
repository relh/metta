type DashboardRecord = Record<string, unknown>

export type DashboardEpisode = DashboardRecord & {
  episode_id: string
  id?: string
  job_id?: string
  created_at?: string | null
  replay_url?: string | null
  thumbnail_url?: string | null
  status: string
  avg_reward?: number
  reward: number
  opponent_name: string
  opponent_version?: number
  team_composition: string
  diagnostic_tags: string[]
  behavior_tags?: string[]
  error_type?: string | null
  error_message?: string | null
  steps: number
  metrics?: Record<string, unknown>
}

export type DashboardKpis = DashboardRecord & {
  diagnostics?: string[]
  avg_reward?: number
  mean_reward?: number
  success_rate?: number
  failure_rate?: number
  total_episodes?: number
  noop_rate?: number
  reward_consistency?: number
  reward_nonzero_pct?: number
  vibe_change_rate?: number
  net_alignment_rate?: number
  hearts_to_junction_rate?: number
  resource_efficiency_per_step?: number
  resource_retention?: number
  junction_control_rate?: number
  alignment_stability?: number
  move_efficiency?: number
  action_success_rate?: number
  freeze_vulnerability?: number
  profile_aggressive?: number
  profile_defensive?: number
  profile_resource_hoarder?: number
  profile_junction_hunter?: number
  profile_mobile_scout?: number
}

export type DashboardFailures = DashboardRecord & {
  total_episodes?: number
  completed_episodes?: number
  failed_episodes?: number
  failed_rate?: number
  timeout_failures?: number
  oom_failures?: number
  crash_failures?: number
  other_failures?: number
  freeze_heavy_completed?: number
  noop_heavy_completed?: number
}

export type DashboardOutcomeSnapshot = DashboardRecord & {
  id?: string
  name?: string
  version?: number
  rank?: number | null
  score?: number | null
  matches?: number
  season?: string
}

export type DashboardOutcomeDelta = DashboardRecord & {
  rank_delta?: number | null
  score_delta?: number | null
  matches_delta?: number | null
}

export type DashboardOutcome = DashboardRecord & {
  verdict?: string
  evidence_sufficient?: boolean
  reason?: string
  current?: DashboardOutcomeSnapshot
  baseline?: DashboardOutcomeSnapshot | null
  delta?: DashboardOutcomeDelta
}

export type DashboardOpponentStats = DashboardRecord & {
  count: number
  total_reward: number
  avg_reward: number
  avg_metrics: Record<string, number>
  strategy_profile: Record<string, number>
}

export type DashboardTeamCompStats = DashboardRecord & {
  composition?: string
  count?: number
  avg_reward?: number
  avg_move_efficiency?: number
  avg_junction_aligned?: number
  avg_resource_gained?: number
}

export type DashboardMatchupSlice = DashboardRecord & {
  key?: string
  count?: number
  avg_reward?: number
  delta_vs_policy?: number
  baseline_count?: number | null
  baseline_avg_reward?: number | null
  delta_vs_baseline?: number | null
}

export type DashboardMatchupSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  interaction_specific_issue?: boolean
  reason?: string
  current_avg_reward?: number
  baseline_avg_reward?: number | null
  global_reward_delta?: number | null
  opponent_spread?: number
  best_opponent?: string | null
  worst_opponent?: string | null
  composition_spread?: number
  best_composition?: string | null
  worst_composition?: string | null
  opponent_slices?: DashboardMatchupSlice[]
  composition_slices?: DashboardMatchupSlice[]
}

export type DashboardTrendPoint = DashboardRecord & {
  id?: string
  name?: string
  version?: number
  rank?: number | null
  score?: number | null
  matches?: number
  has_leaderboard_data?: boolean
}

export type DashboardTrendSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  direction?: string
  reason?: string
  score_delta_from_oldest?: number | null
  rank_delta_from_oldest?: number | null
  points?: DashboardTrendPoint[]
}

export type DashboardTrendExplorerSeries = DashboardRecord & {
  key: string
  label: string
  higher_is_better?: boolean
  direction?: string
  reason?: string
  values?: Array<number | null>
  deltas?: Array<number | null>
}

export type DashboardTrendDistribution = DashboardRecord & {
  count?: number
  mean?: number | null
  median?: number | null
  p10?: number | null
  p90?: number | null
}

export type DashboardTrendMetricOverlay = DashboardRecord & {
  key: string
  label?: string
  higher_is_better?: boolean
  current_value?: number | null
  current_display?: string
  team?: DashboardTrendDistribution
  population?: DashboardTrendDistribution
  delta_vs_team_mean?: number | null
  delta_vs_population_mean?: number | null
  signal?: string
  reason?: string
}

export type DashboardSubmissionPatternGroup = DashboardRecord & {
  code?: string
  title?: string
  metric_key?: string
  severity?: string
  count?: number
  versions?: string[]
  evidence?: string
  next_action?: string
}

export type DashboardTrendExplorerSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  selected_metric?: string
  version_labels?: string[]
  series?: DashboardTrendExplorerSeries[]
  metric_overlays?: DashboardTrendMetricOverlay[]
  submission_patterns?: DashboardSubmissionPatternGroup[]
}

export type DashboardConfidenceInterval = DashboardRecord & {
  key?: string
  label?: string
  point_estimate?: number | null
  lower?: number | null
  upper?: number | null
  crosses_zero?: boolean | null
  current_samples?: number
  baseline_samples?: number
  interpretation?: string
}

export type DashboardConfidenceSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  intervals?: DashboardConfidenceInterval[]
  recommended_actions?: string[]
}

export type DashboardPatternSignal = DashboardRecord & {
  code?: string
  title?: string
  severity?: string
  confidence?: string
  evidence?: string
  next_action?: string
}

export type DashboardPatternSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  headline?: string
  signals?: DashboardPatternSignal[]
}

export type DashboardUnsupportedIssue = DashboardRecord & {
  code?: string
  severity?: string
  message?: string
  affected_count?: number
  total_count?: number
  recommended_action?: string
}

export type DashboardUnsupportedSummary = DashboardRecord & {
  has_unsupported_state?: boolean
  issues?: DashboardUnsupportedIssue[]
}

export type DashboardInstrumentationCheck = DashboardRecord & {
  key?: string
  kind?: string
  required?: boolean
  present_count?: number
  total_count?: number
  coverage?: number
  status?: string
  message?: string
}

export type DashboardInstrumentationSummary = DashboardRecord & {
  template_version?: string
  min_coverage_threshold?: number
  compliant?: boolean
  score?: number
  checks?: DashboardInstrumentationCheck[]
  recommended_actions?: string[]
}

export type DashboardStatsInventoryField = DashboardRecord & {
  key?: string
  kind?: string
  present_count?: number
  total_count?: number
  coverage?: number
}

export type DashboardStatsInventorySummary = DashboardRecord & {
  total_episodes?: number
  completed_episodes?: number
  failed_episodes?: number
  distinct_metric_keys?: number
  distinct_tag_keys?: number
  top_metric_keys?: DashboardStatsInventoryField[]
  top_tag_keys?: DashboardStatsInventoryField[]
  notes?: string[]
}

export type DashboardActionSummary = DashboardRecord & {
  rollout_recommendation?: string
  headline?: string
  actions?: string[]
}

export type DashboardOrchestrationExperimentHook = DashboardRecord & {
  id?: string
  priority?: number
  title?: string
  objective?: string
  rationale?: string
  actions?: string[]
  acceptance_checks?: string[]
}

export type DashboardOrchestrationPayloadTemplate = DashboardRecord & {
  template_version?: string
  policy_version_id?: string
  rollout_gate?: string
  mode?: string
  experiment_ids?: string[]
}

export type DashboardOrchestrationSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  mode?: string
  headline?: string
  experiments?: DashboardOrchestrationExperimentHook[]
  payload_template?: DashboardOrchestrationPayloadTemplate
}

export type DashboardCrashDumpSignature = DashboardRecord & {
  signature?: string
  count?: number
  error_type?: string
  example_message?: string | null
}

export type DashboardCrashDumpEntry = DashboardRecord & {
  episode_id?: string
  job_id?: string
  created_at?: string | null
  error_type?: string | null
  error_message?: string | null
  analysis_command?: string
  replay_url?: string | null
}

export type DashboardCrashDumpSummary = DashboardRecord & {
  evidence_sufficient?: boolean
  headline?: string
  total_failed?: number
  signatures?: DashboardCrashDumpSignature[]
  entries?: DashboardCrashDumpEntry[]
}

export type DashboardCapabilityCodeStatus = DashboardRecord & {
  status?: 'yes' | 'partial' | 'no' | 'planned' | string
  support_type?: 'trained' | 'backed' | string
  training_source?: string | null
  evidence?: string[]
}

export type DashboardCapabilityCodeAudit = DashboardRecord & {
  template_version?: string
  generated_at?: string
  capabilities?: Record<string, DashboardCapabilityCodeStatus>
  sources?: Record<string, DashboardCapabilityCodeStatus>
}

export type DashboardDerived = DashboardRecord & {
  kpis: DashboardKpis
  failures: DashboardFailures
  team_comp?: DashboardTeamCompStats[]
  opponent_metrics: Record<string, DashboardOpponentStats>
  outcome?: DashboardOutcome
  matchup?: DashboardMatchupSummary | null
  trend?: DashboardTrendSummary | null
  trend_explorer?: DashboardTrendExplorerSummary | null
  confidence?: DashboardConfidenceSummary | null
  patterns?: DashboardPatternSummary | null
  unsupported?: DashboardUnsupportedSummary | null
  instrumentation?: DashboardInstrumentationSummary | null
  stats_inventory?: DashboardStatsInventorySummary | null
  actions?: DashboardActionSummary | null
  orchestration?: DashboardOrchestrationSummary | null
  crash_dump?: DashboardCrashDumpSummary | null
  capability_code_audit?: DashboardCapabilityCodeAudit | null
}

export type DashboardPolicy = DashboardRecord & {
  id: string
  name: string
  version: number
  rank?: number | null
  score?: number | null
  matches?: number
}

export type DashboardSelection = DashboardRecord & {
  sampled_episode_count: number
  limit?: number
  offset?: number
  ordering?: string
  includes_failed_jobs_without_episode?: boolean
  baseline_limit?: number | null
}

export type DashboardResponse = DashboardRecord & {
  policy: DashboardPolicy
  season: string
  generated_at: string
  episodes: DashboardEpisode[]
  derived: DashboardDerived
  selection: DashboardSelection
  role_percentiles?: DashboardRolePercentilesResponse | null
  diagnose_runs?: DiagnoseRunSummary[] | null
}

export type DashboardAnalysisResponse = {
  analysis: string
  data_sources: string[]
}

export type DashboardRoleMetricDef = {
  key: string
  source_names: string[]
  higher_is_better: boolean
  include_in_overall?: boolean
  overall_weight?: number
}

export type DashboardRolePercentileMetric = {
  avg?: number
  percentile?: number
  higher_is_better?: boolean
  samples?: number
  source_names?: string[]
  source_metrics?: Record<string, unknown>
}

export type DashboardRolePercentileRow = {
  role: string
  percentile: number
  details?: {
    metrics?: Record<string, DashboardRolePercentileMetric>
    overall_percentile?: number
    [key: string]: unknown
  }
  updated_at: string
}

export type DashboardRolePercentilesResponse = {
  pool_id: string | null
  pool_name: string | null
  roles: Record<string, DashboardRoleMetricDef[]>
  rows: DashboardRolePercentileRow[]
}

export type DiagnoseAxis = 'stability' | 'efficiency' | 'control' | 'social_coordination'

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

export type DiagnoseInterpretationStability = DashboardRecord & {
  stable: boolean
  snapshot_count?: number
  dominant_issue_stable?: boolean
  top_symptom_stable?: boolean
  notes?: string[]
}

export type DiagnoseManifest = DashboardRecord & {
  run_id: string
  created_at: string
  command: string
  policy: string
  pack_id: string
  pack_version: string
  stage_status: string
  run_status: string
  artifact_files: string[]
  diagnose_validity: DiagnoseValidityReport
  interpretation_stability: DiagnoseInterpretationStability
}

export type DiagnoseAxisScore = DashboardRecord & {
  axis: DiagnoseAxis
  normalized_score: number
  raw_score: number
  confirmed: boolean
  derived_metrics: {
    reward_variance: number
    non_zero_episode_pct: number
    timeout_rate: number
    mean_move_success: number
    mean_action_failed: number
    mean_stuck_steps: number
    [key: string]: number
  }
}

export type DiagnoseProbeDefinition = DashboardRecord & {
  probe_id: string
  axis: DiagnoseAxis
  mission: string
  question: string
  validation_metric: string
  pass_fail_threshold: string
}

export type DiagnoseProbeEvaluation = DashboardRecord & {
  probe_id: string
  axis: DiagnoseAxis
  passed: boolean
  summary: string
  evidence_refs: string[]
}

export type DiagnoseSymptom = DashboardRecord & {
  symptom_id: string
  axis: DiagnoseAxis
  severity: number
  confidence: number
  likely_cause: string
  action: string
  expected_effect: string
}

export type DiagnosePrescription = DashboardRecord & {
  symptom_id: string
  action: string
  owner: string
  validation_metric: string
  pass_fail_threshold: string
}

export type DiagnoseTournamentObjectiveContext = {
  aligned_junction_held_stage1?: number | null
  aligned_junction_held_stage2_absolute?: number | null
  aligned_junction_held_stage2_mirror?: number | null
}

export type DiagnoseSocialReview = DashboardRecord & {
  confirmed: boolean
  severity: number
  confidence: number
  summary: string
  evidence_refs?: string[]
}

export type DiagnoseStage2DiagnosisDelta = DashboardRecord & {
  stage1_dominant_issue: string
  final_dominant_issue: string
  changed: boolean
  summary: string
  evidence_refs: string[]
}

export type DiagnoseEvidenceIndex = DashboardRecord & {
  metric_refs?: string[]
  replay_refs?: string[]
  baseline_refs?: string[]
}

export type DiagnoseDoctorNote = DashboardRecord & {
  run_id: string
  status: string
  diagnosis_status?: string
  stage_status: string
  dominant_issue: string
  notes: string[]
  axes: DiagnoseAxisScore[]
  stage1_probe_catalog: DiagnoseProbeDefinition[]
  stage1_probe_evaluations: DiagnoseProbeEvaluation[]
  symptoms: DiagnoseSymptom[]
  prescriptions: DiagnosePrescription[]
  tournament_objective_context: DiagnoseTournamentObjectiveContext
  social_review?: DiagnoseSocialReview | null
  stage2_diagnosis_delta?: DiagnoseStage2DiagnosisDelta | null
  evidence_index: DiagnoseEvidenceIndex
}

export type DiagnoseRunSummary = {
  run_id: string
  manifest: DiagnoseManifest | null
}

export type DiagnoseRunsResponse = {
  runs: DiagnoseRunSummary[]
}

export type DiagnoseUploadResponse = {
  run_id: string
  manifest: DiagnoseManifest | null
}

export type PantheonStory = {
  story_id: string
  hall: 'fame' | 'same' | 'lame'
  title: string
  motif: string
  summary: string
  policy: string
  run_id?: string | null
  episode_id?: string | null
  replay_url?: string | null
  source?: string
  tags?: string[]
  created_at: string
}

export type PantheonStoriesResponse = {
  generated_at: string
  source_root?: string | null
  stories: PantheonStory[]
}
