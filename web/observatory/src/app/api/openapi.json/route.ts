import { config } from '@/config'

export async function GET() {
  const res = await fetch(`${config.apiBaseUrl}/openapi.json`, { cache: 'no-store' })
  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': 'application/json' },
  })
}
