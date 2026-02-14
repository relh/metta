import { getAuthToken } from '@/auth/server'
import { config } from '@/config'

export async function GET() {
  const token = await getAuthToken()
  const headers: Record<string, string> = {}
  if (token) {
    headers['X-Auth-Token'] = token
  }
  const res = await fetch(`${config.apiBaseUrl}/internal/openapi.json`, { headers, cache: 'no-store' })
  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
