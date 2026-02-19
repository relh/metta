import clsx from 'clsx'
import { FC } from 'react'

import { Card } from '@/components/Card'
import { Tag } from '@/components/Tag'
import type {
  DiagnoseAxis,
  DiagnoseDoctorNote,
  Stage1AxisScore,
  Stage1ProbeDefinition,
  Stage1ProbeEvaluation,
} from '@/lib/cogames-diagnose/types'

const AXIS_ORDER: DiagnoseAxis[] = ['stability', 'efficiency', 'control', 'social_coordination']

const AXIS_LABEL: Record<DiagnoseAxis, string> = {
  stability: 'Stability',
  efficiency: 'Efficiency',
  control: 'Control',
  social_coordination: 'Social Coordination',
}

function formatPct(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`
}

function scoreColor(score: number): string {
  if (score >= 0.75) return 'bg-emerald-500'
  if (score >= 0.5) return 'bg-amber-500'
  return 'bg-rose-500'
}

function axisById(axes: Stage1AxisScore[]): Record<DiagnoseAxis, Stage1AxisScore | undefined> {
  return Object.fromEntries(axes.map((axis) => [axis.axis, axis])) as Record<DiagnoseAxis, Stage1AxisScore>
}

function probeCatalogByAxis(catalog: Stage1ProbeDefinition[]): Record<DiagnoseAxis, Stage1ProbeDefinition[]> {
  const out: Record<DiagnoseAxis, Stage1ProbeDefinition[]> = {
    stability: [],
    efficiency: [],
    control: [],
    social_coordination: [],
  }
  for (const probe of catalog) out[probe.axis].push(probe)
  for (const axis of AXIS_ORDER) out[axis].sort((a, b) => a.probe_id.localeCompare(b.probe_id))
  return out
}

function probeEvalById(evals: Stage1ProbeEvaluation[]): Map<string, Stage1ProbeEvaluation> {
  return new Map(evals.map((ev) => [ev.probe_id, ev]))
}

const ProbeNode: FC<{
  probe: Stage1ProbeDefinition
  evaluation: Stage1ProbeEvaluation | undefined
}> = ({ probe, evaluation }) => {
  const passed = evaluation?.passed ?? false
  return (
    <div className="relative pl-5">
      <div className="absolute left-1 top-2.5 w-3 h-3 rounded-full border border-border-strong bg-surface">
        <div className={clsx('w-full h-full rounded-full', passed ? 'bg-emerald-500' : 'bg-rose-500')} />
      </div>
      <div className="rounded-lg border border-border bg-surface-alt px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{probe.probe_id}</span>
          <span className="text-xs text-foreground-muted">
            {probe.mission} · {probe.validation_metric}
          </span>
          <span className="ml-auto text-xs text-foreground-muted">{passed ? 'passed' : 'failed'}</span>
        </div>
        <p className="mt-2 text-sm text-foreground-subtle">{probe.question}</p>
        <p className="mt-2 text-xs text-foreground-muted">
          Threshold: <span className="font-mono">{probe.pass_fail_threshold}</span>
        </p>
        {evaluation?.summary && <p className="mt-2 text-xs text-foreground-muted">{evaluation.summary}</p>}
        {evaluation?.evidence_refs?.length ? (
          <p className="mt-2 text-[11px] text-foreground-muted">
            evidence: <span className="font-mono">{evaluation.evidence_refs.join(', ')}</span>
          </p>
        ) : null}
      </div>
    </div>
  )
}

const AxisNode: FC<{
  axis: DiagnoseAxis
  score: Stage1AxisScore | undefined
  probes: Stage1ProbeDefinition[]
  evalById: Map<string, Stage1ProbeEvaluation>
}> = ({ axis, score, probes, evalById }) => {
  const normalized = score?.normalized_score ?? 0
  const mastered = score?.confirmed ?? false

  return (
    <Card
      title={
        <div className="flex flex-wrap items-center gap-3">
          <span>{AXIS_LABEL[axis]}</span>
          {mastered ? <Tag>Mastered</Tag> : <span className="text-xs text-foreground-muted">Training</span>}
          <span className="ml-auto text-sm text-foreground-muted font-mono">{formatPct(normalized, 0)}</span>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="h-2 w-full rounded-full bg-border-subtle overflow-hidden">
          <div className={clsx('h-full', scoreColor(normalized))} style={{ width: `${normalized * 100}%` }} />
        </div>

        {score ? (
          <div className="grid grid-cols-2 gap-3 text-xs text-foreground-muted">
            <div>
              move_success{' '}
              <span className="font-mono text-foreground">{formatPct(score.derived_metrics.mean_move_success, 0)}</span>
            </div>
            <div>
              timeout_rate{' '}
              <span className="font-mono text-foreground">{formatPct(score.derived_metrics.timeout_rate, 1)}</span>
            </div>
            <div>
              reward_var{' '}
              <span className="font-mono text-foreground">{score.derived_metrics.reward_variance.toFixed(2)}</span>
            </div>
            <div>
              stuck_steps{' '}
              <span className="font-mono text-foreground">{score.derived_metrics.mean_stuck_steps.toFixed(0)}</span>
            </div>
          </div>
        ) : (
          <p className="text-sm text-foreground-muted">No axis score available.</p>
        )}

        <details open>
          <summary className="cursor-pointer text-sm font-medium text-foreground-subtle hover:text-foreground">
            Probes ({probes.length})
          </summary>
          <div className="mt-3 space-y-3 border-l border-border pl-3">
            {probes.length === 0 ? (
              <p className="text-sm text-foreground-muted">No probes configured for this axis.</p>
            ) : (
              probes.map((probe) => (
                <ProbeNode key={probe.probe_id} probe={probe} evaluation={evalById.get(probe.probe_id)} />
              ))
            )}
          </div>
        </details>
      </div>
    </Card>
  )
}

export const SkillTree: FC<{ doctorNote: DiagnoseDoctorNote }> = ({ doctorNote }) => {
  const axes = axisById(doctorNote.axes)
  const probesByAxis = probeCatalogByAxis(doctorNote.stage1_probe_catalog)
  const evalById = probeEvalById(doctorNote.stage1_probe_evaluations)

  return (
    <div className="space-y-6">
      <Card title="Skill Tree (from doctor_note.json)">
        <div className="flex flex-wrap items-center gap-3 text-sm text-foreground-muted">
          <span>
            run_id <span className="font-mono text-foreground">{doctorNote.run_id}</span>
          </span>
          <span>
            status <span className="font-mono text-foreground">{doctorNote.status}</span>
          </span>
          <span>
            stage <span className="font-mono text-foreground">{doctorNote.stage_status}</span>
          </span>
          <span>
            dominant <span className="font-mono text-foreground">{doctorNote.dominant_issue}</span>
          </span>
        </div>
        {doctorNote.notes?.length ? (
          <ul className="mt-4 list-disc pl-5 text-sm text-foreground-subtle space-y-1">
            {doctorNote.notes.map((note, idx) => (
              <li key={idx}>{note}</li>
            ))}
          </ul>
        ) : null}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {AXIS_ORDER.map((axis) => (
          <AxisNode key={axis} axis={axis} score={axes[axis]} probes={probesByAxis[axis]} evalById={evalById} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title={`Symptoms (${doctorNote.symptoms.length})`}>
          {doctorNote.symptoms.length === 0 ? (
            <p className="text-sm text-foreground-muted">No symptoms recorded.</p>
          ) : (
            <div className="space-y-3">
              {doctorNote.symptoms.map((symptom) => (
                <div key={symptom.symptom_id} className="rounded-lg border border-border bg-surface-alt p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">{symptom.symptom_id}</span>
                    <span className="text-xs text-foreground-muted">{AXIS_LABEL[symptom.axis]}</span>
                    <span className="ml-auto text-xs text-foreground-muted font-mono">
                      severity {(symptom.severity * 100).toFixed(0)} · conf {(symptom.confidence * 100).toFixed(0)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-foreground-subtle">{symptom.likely_cause}</p>
                  <p className="mt-2 text-xs text-foreground-muted">
                    action: <span className="text-foreground-subtle">{symptom.action}</span>
                  </p>
                  <p className="mt-1 text-xs text-foreground-muted">
                    expected: <span className="text-foreground-subtle">{symptom.expected_effect}</span>
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title={`Prescriptions (${doctorNote.prescriptions.length})`}>
          {doctorNote.prescriptions.length === 0 ? (
            <p className="text-sm text-foreground-muted">No prescriptions recorded.</p>
          ) : (
            <div className="space-y-3">
              {doctorNote.prescriptions.map((rx, idx) => (
                <div key={`${rx.symptom_id}-${idx}`} className="rounded-lg border border-border bg-surface-alt p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-foreground">{rx.symptom_id}</span>
                    <span className="text-xs text-foreground-muted">{rx.owner}</span>
                    <span className="ml-auto text-xs text-foreground-muted font-mono">{rx.validation_metric}</span>
                  </div>
                  <p className="mt-2 text-sm text-foreground-subtle">{rx.action}</p>
                  <p className="mt-2 text-xs text-foreground-muted">
                    pass/fail: <span className="font-mono text-foreground">{rx.pass_fail_threshold}</span>
                  </p>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
