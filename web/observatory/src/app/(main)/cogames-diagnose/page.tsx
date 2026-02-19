import Link from 'next/link'

import { Card } from '@/components/Card'
import { LinkButton } from '@/components/LinkButton'
import { StandardPageLayout } from '@/components/layouts/StandardPageLayout'
import { listDiagnoseRuns, loadDiagnoseManifest } from '@/lib/cogames-diagnose/fs'

export default async function CogamesDiagnoseIndexPage() {
  const runs = await listDiagnoseRuns()
  const manifests = await Promise.all(runs.map((runId) => loadDiagnoseManifest(runId)))

  return (
    <StandardPageLayout>
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-foreground-muted tracking-wide">Cogames Diagnose</p>
          <h1 className="text-2xl font-semibold text-foreground">Diagnose Runs</h1>
        </div>
        <LinkButton href="/policies" theme="tertiary">
          &larr; Back to policies
        </LinkButton>
      </div>

      <Card title="Local Runs">
        {runs.length === 0 ? (
          <div className="space-y-3 text-sm text-foreground-muted">
            <p>No local runs found under `outputs/cogames-diagnose/`.</p>
            <p className="text-foreground-subtle">
              Create one with <span className="font-mono">cogames diagnose &lt;policy&gt;</span>, then refresh.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {runs.map((runId, idx) => {
              const manifest = manifests[idx]
              const title = manifest
                ? `${manifest.policy} (${manifest.pack_id}:${manifest.pack_version})`
                : 'Diagnose run'
              const subtitle = manifest
                ? `stage=${manifest.stage_status} · status=${manifest.run_status} · created_at=${manifest.created_at}`
                : 'manifest.json missing'
              return (
                <div
                  key={runId}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface-alt px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate">{title}</p>
                    <p className="text-xs text-foreground-muted font-mono truncate">{runId}</p>
                    <p className="text-xs text-foreground-muted">{subtitle}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <LinkButton href={`/cogames-diagnose/${encodeURIComponent(runId)}`} theme="secondary">
                      Open
                    </LinkButton>
                    <Link
                      className="text-xs text-foreground-muted hover:text-foreground underline"
                      href={`/cogames-diagnose/${encodeURIComponent(runId)}/artifacts/manifest.json`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      manifest.json
                    </Link>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </StandardPageLayout>
  )
}

export const metadata = {
  title: 'Cogames Diagnose | Observatory',
}
