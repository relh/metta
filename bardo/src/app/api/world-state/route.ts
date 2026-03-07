import { NextRequest, NextResponse } from 'next/server'

import { bardoProxyHeaders } from './proxy-headers'

const REVALIDATE_HEADERS = {
  'Cache-Control': 'private, no-cache',
}

function bardoWorldStateUrl(): string {
  return (process.env.BARDO_WORLD_STATE_URL || 'http://127.0.0.1:8010/bardo/v1/world-state').replace(/\/$/, '')
}

function responseHeaders(etag: string | null): HeadersInit {
  if (!etag) return REVALIDATE_HEADERS
  return {
    ...REVALIDATE_HEADERS,
    ETag: etag,
  }
}

export async function GET(request: NextRequest) {
  const url = new URL(bardoWorldStateUrl())
  const nameFilter = request.nextUrl.searchParams.get('q')?.trim()
  if (nameFilter) {
    url.searchParams.set('q', nameFilter)
  }

  try {
    const headers = bardoProxyHeaders(request)
    const ifNoneMatch = request.headers.get('if-none-match')?.trim()
    if (ifNoneMatch) {
      headers['If-None-Match'] = ifNoneMatch
    }

    const response = await fetch(url, {
      cache: 'no-store',
      headers,
    })
    const etag = response.headers.get('etag')
    if (response.status === 304) {
      return new NextResponse(null, {
        status: 304,
        headers: responseHeaders(etag),
      })
    }
    const payload = await response.json()

    return NextResponse.json(payload, {
      status: response.status,
      headers: responseHeaders(etag),
    })
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error)
    return NextResponse.json(
      { error: `Failed to load bardo world state: ${detail}` },
      { status: 502, headers: REVALIDATE_HEADERS }
    )
  }
}
