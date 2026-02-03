import { NextRequest, NextResponse } from 'next/server'

import { getRepo } from '@/lib/repo/server'

export async function GET(request: NextRequest) {
  const name_fuzzy = request.nextUrl.searchParams.get('name_fuzzy') ?? undefined
  const limit = parseInt(request.nextUrl.searchParams.get('limit') ?? '20', 10)

  const repo = await getRepo()
  const resp = await repo.getPolicyVersions({ name_fuzzy, limit })
  return NextResponse.json(resp.entries)
}
