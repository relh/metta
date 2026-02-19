import { loadDiagnoseArtifact, loadDiagnoseManifest } from '@/lib/cogames-diagnose/fs'

function contentTypeForArtifact(artifact: string): string {
  if (artifact.endsWith('.json')) return 'application/json; charset=utf-8'
  if (artifact.endsWith('.html')) return 'text/html; charset=utf-8'
  if (artifact.endsWith('.md')) return 'text/markdown; charset=utf-8'
  if (artifact.endsWith('.txt')) return 'text/plain; charset=utf-8'
  if (artifact.endsWith('.zip')) return 'application/zip'
  return 'application/octet-stream'
}

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string; artifact: string }> }
): Promise<Response> {
  const { runId, artifact } = await params

  const manifest = await loadDiagnoseManifest(runId)
  const allowed = new Set<string>(manifest?.artifact_files ?? [])

  // Always allow the basics even if manifest is missing/out of date.
  allowed.add('manifest.json')
  allowed.add('doctor_note.json')

  if (!allowed.has(artifact)) {
    return new Response('Artifact not found', { status: 404 })
  }

  let body: Uint8Array
  try {
    body = await loadDiagnoseArtifact(runId, artifact)
  } catch {
    return new Response('Artifact not found', { status: 404 })
  }

  const headers = new Headers()
  headers.set('Content-Type', contentTypeForArtifact(artifact))
  if (artifact.endsWith('.zip')) {
    headers.set('Content-Disposition', `attachment; filename="${artifact}"`)
  }

  const bodyInit = body.buffer.slice(body.byteOffset, body.byteOffset + body.byteLength) as unknown as ArrayBuffer
  return new Response(bodyInit, { status: 200, headers })
}
