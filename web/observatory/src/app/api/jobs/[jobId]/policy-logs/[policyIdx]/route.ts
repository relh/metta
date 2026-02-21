import { NextRequest, NextResponse } from 'next/server'

import { getRepo } from '@/lib/repo/server'

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string; policyIdx: string }> }
) {
  const { jobId, policyIdx } = await params
  const agentIdx = parseInt(policyIdx, 10)
  if (isNaN(agentIdx)) {
    return NextResponse.json({ error: 'Invalid agent index' }, { status: 400 })
  }
  try {
    const repo = await getRepo()
    const logContent = await repo.getJobPolicyLogContent(jobId, agentIdx)
    return new NextResponse(logContent, {
      headers: { 'Content-Type': 'text/plain' },
    })
  } catch {
    return NextResponse.json({ error: 'Log not available' }, { status: 404 })
  }
}
