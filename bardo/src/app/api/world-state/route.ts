import { NextRequest, NextResponse } from 'next/server'

import { bardoProxyHeaders } from './proxy-headers'

const NO_STORE_HEADERS = {
  'Cache-Control': 'no-store, max-age=0',
}

function bardoWorldStateUrl(): string {
  return (process.env.BARDO_WORLD_STATE_URL || 'http://127.0.0.1:8010/bardo/v1/world-state').replace(/\/$/, '')
}

export async function GET(request: NextRequest) {
  const url = new URL(bardoWorldStateUrl())
  const nameFilter = request.nextUrl.searchParams.get('q')?.trim()
  if (nameFilter) {
    url.searchParams.set('q', nameFilter)
  }

  try {
    const response = await fetch(url, {
      cache: 'no-store',
      headers: bardoProxyHeaders(request),
    })
    const payload = await response.json()

    return NextResponse.json(payload, {
      status: response.status,
      headers: NO_STORE_HEADERS,
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    return NextResponse.json(
      { error: `Failed to load bardo world state: ${detail}` },
      { status: 502, headers: NO_STORE_HEADERS }
    )
  }
}
