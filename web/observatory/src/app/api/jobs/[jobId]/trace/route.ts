import { NextRequest, NextResponse } from 'next/server'

import { getAuthToken } from '@/auth/server'
import { config } from '@/config'

function getCorsHeaders(request: NextRequest): Record<string, string> {
  const origin = request.headers.get('origin')
  const requestedHeaders = request.headers.get('access-control-request-headers')
  return {
    'Access-Control-Allow-Origin': origin ?? '*',
    'Access-Control-Allow-Credentials': 'true',
    'Access-Control-Allow-Methods': 'GET, HEAD, OPTIONS',
    'Access-Control-Allow-Headers': requestedHeaders ?? 'Content-Type, Range',
    'Access-Control-Allow-Private-Network': 'true',
    'Access-Control-Expose-Headers': 'Content-Type, Content-Length, Content-Range, Accept-Ranges',
    Vary: 'Origin',
  }
}

export async function OPTIONS(request: NextRequest) {
  return new NextResponse(null, { status: 204, headers: getCorsHeaders(request) })
}

async function fetchTraceResponse(
  request: NextRequest,
  params: Promise<{ jobId: string }>,
  includeBody: boolean
): Promise<NextResponse> {
  const { jobId } = await params
  // TODO: Accept a dedicated short-lived trace token here instead of full auth token fallback.
  const tokenFromQuery = request.nextUrl.searchParams.get('auth_token')
  const tokenFromCookie = await getAuthToken()
  const token = tokenFromQuery ?? tokenFromCookie
  const headers = getCorsHeaders(request)

  const backendHeaders: Record<string, string> = {}
  if (token) {
    backendHeaders['X-Auth-Token'] = token
  }

  try {
    const backendResponse = await fetch(`${config.apiBaseUrl}/jobs/${jobId}/artifacts/trace`, {
      method: 'GET',
      headers: backendHeaders,
      cache: 'no-store',
    })

    if (!backendResponse.ok) {
      const status = backendResponse.status === 401 || backendResponse.status === 403 ? 401 : backendResponse.status
      const message = status === 401 ? 'Trace auth required' : 'Trace not available'
      return new NextResponse(message, { status, headers })
    }

    if (!includeBody) {
      return new NextResponse(null, { status: 200, headers: { ...headers, 'Content-Type': 'application/json' } })
    }

    const trace = await backendResponse.text()
    return new NextResponse(trace, { status: 200, headers: { ...headers, 'Content-Type': 'application/json' } })
  } catch {
    return new NextResponse('Trace not available', { status: 404, headers })
  }
}

export async function GET(request: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  return fetchTraceResponse(request, params, true)
}

export async function HEAD(request: NextRequest, { params }: { params: Promise<{ jobId: string }> }) {
  return fetchTraceResponse(request, params, false)
}
