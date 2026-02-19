import { notFound } from 'next/navigation'

import { Card } from '@/components/Card'
import { LinkButton } from '@/components/LinkButton'
import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'
import { SkillTree } from '@/components/cogames-diagnose/SkillTree'
import { loadDiagnoseDoctorNote, loadDiagnoseManifest } from '@/lib/cogames-diagnose/fs'

export default async function CogamesDiagnoseRunPage(props: PageProps<'/cogames-diagnose/[runId]'>) {
  const { runId } = await props.params

  let manifest = null
  try {
    manifest = await loadDiagnoseManifest(runId)
  } catch {
    manifest = null
  }

  let doctorNote
  try {
    doctorNote = await loadDiagnoseDoctorNote(runId)
  } catch {
    notFound()
  }

  const reportHref = `/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/diagnose_report.html`
  const noteHref = `/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/doctor_note.json`
  const manifestHref = `/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/manifest.json`

  return (
    <StandardPageLayout>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1 min-w-0">
          <p className="text-xs font-semibold uppercase text-foreground-muted tracking-wide">Cogames Diagnose</p>
          <h1 className="text-2xl font-semibold text-foreground truncate">
            {manifest ? manifest.policy : 'Diagnose Run'} <span className="text-foreground-muted">({runId})</span>
          </h1>
        </div>
        <div className="flex gap-2">
          <LinkButton href="/cogames-diagnose" theme="secondary">
            All Runs
          </LinkButton>
          <LinkButton href={reportHref} theme="tertiary">
            Open Report
          </LinkButton>
        </div>
      </div>

      <Card title="Artifacts">
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <a
            className="underline text-foreground-subtle hover:text-foreground"
            href={noteHref}
            target="_blank"
            rel="noopener noreferrer"
          >
            doctor_note.json
          </a>
          <a
            className="underline text-foreground-subtle hover:text-foreground"
            href={manifestHref}
            target="_blank"
            rel="noopener noreferrer"
          >
            manifest.json
          </a>
          <a
            className="underline text-foreground-subtle hover:text-foreground"
            href={`/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/diagnose_validity.json`}
            target="_blank"
            rel="noopener noreferrer"
          >
            diagnose_validity.json
          </a>
          <a
            className="underline text-foreground-subtle hover:text-foreground"
            href={`/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/interpretation_stability.json`}
            target="_blank"
            rel="noopener noreferrer"
          >
            interpretation_stability.json
          </a>
          <a
            className="underline text-foreground-subtle hover:text-foreground"
            href={`/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/replay_bundle.zip`}
            target="_blank"
            rel="noopener noreferrer"
          >
            replay_bundle.zip
          </a>
        </div>
        {manifest?.command ? (
          <p className="mt-3 text-xs text-foreground-muted">
            command: <span className="font-mono">{manifest.command}</span>
          </p>
        ) : null}
      </Card>

      <SkillTree doctorNote={doctorNote} />
    </StandardPageLayout>
  )
}

export async function generateMetadata({ params }: PageProps<'/cogames-diagnose/[runId]'>) {
  const { runId } = await params
  return {
    title: `Diagnose: ${runId} | Observatory`,
  }
}
