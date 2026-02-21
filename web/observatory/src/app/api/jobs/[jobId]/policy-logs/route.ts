import { NextRequest, NextResponse } from 'next/server'

import { getRepo } from '@/lib/repo/server'

export async function GET(_request: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params
  try {
    const repo = await getRepo()
    const logFiles = await repo.listJobPolicyLogs(jobId)
    return NextResponse.json(logFiles)
  } catch {
    return NextResponse.json([], { status: 200 })
  }
}
