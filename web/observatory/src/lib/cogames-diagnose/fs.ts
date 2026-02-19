import 'server-only'

import { readFile, readdir, stat } from 'node:fs/promises'
import * as path from 'node:path'

import type { DiagnoseDoctorNote, DiagnoseManifest } from '@/lib/cogames-diagnose/types'

const RUN_ID_RE = /^[0-9a-zA-Z._-]+$/

function assertValidRunId(runId: string): void {
  if (!RUN_ID_RE.test(runId)) {
    throw new Error(`Invalid diagnose run id: ${runId}`)
  }
}

async function pathExists(p: string): Promise<boolean> {
  try {
    await stat(p)
    return true
  } catch {
    return false
  }
}

async function resolveRepoRoot(): Promise<string> {
  let current = process.cwd()
  for (let i = 0; i < 10; i++) {
    const workspace = path.join(current, 'pnpm-workspace.yaml')
    if (await pathExists(workspace)) return current
    const next = path.dirname(current)
    if (next === current) break
    current = next
  }
  throw new Error(`Failed to resolve repo root from cwd=${process.cwd()}`)
}

export async function resolveDiagnoseRunDir(runId: string): Promise<string> {
  assertValidRunId(runId)
  const repoRoot = await resolveRepoRoot()
  return path.join(repoRoot, 'outputs', 'cogames-diagnose', runId)
}

export async function listDiagnoseRuns(): Promise<string[]> {
  const repoRoot = await resolveRepoRoot()
  const root = path.join(repoRoot, 'outputs', 'cogames-diagnose')
  if (!(await pathExists(root))) return []

  const entries = await readdir(root)
  const runs: string[] = []
  for (const entry of entries) {
    if (!RUN_ID_RE.test(entry)) continue
    const full = path.join(root, entry)
    try {
      const s = await stat(full)
      if (s.isDirectory()) runs.push(entry)
    } catch {
      // ignore entries that disappear
    }
  }
  runs.sort((a, b) => b.localeCompare(a))
  return runs
}

async function readJsonFile<T>(fullPath: string): Promise<T> {
  const content = await readFile(fullPath, 'utf8')
  return JSON.parse(content) as T
}

export async function loadDiagnoseManifest(runId: string): Promise<DiagnoseManifest | null> {
  const dir = await resolveDiagnoseRunDir(runId)
  const manifestPath = path.join(dir, 'manifest.json')
  if (!(await pathExists(manifestPath))) return null
  return readJsonFile<DiagnoseManifest>(manifestPath)
}

export async function loadDiagnoseDoctorNote(runId: string): Promise<DiagnoseDoctorNote> {
  const dir = await resolveDiagnoseRunDir(runId)
  const notePath = path.join(dir, 'doctor_note.json')
  return readJsonFile<DiagnoseDoctorNote>(notePath)
}

export async function loadDiagnoseArtifact(runId: string, artifact: string): Promise<Uint8Array> {
  assertValidRunId(runId)
  if (!RUN_ID_RE.test(artifact)) {
    throw new Error(`Invalid artifact name: ${artifact}`)
  }
  const dir = await resolveDiagnoseRunDir(runId)
  const fullPath = path.join(dir, artifact)
  return readFile(fullPath)
}
