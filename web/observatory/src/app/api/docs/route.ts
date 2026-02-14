import { config } from '@/config'

export async function GET() {
  const res = await fetch(`${config.apiBaseUrl}/docs`, { cache: 'no-store' })
  return new Response(res.body, {
    status: res.status,
    headers: { 'Content-Type': res.headers.get('Content-Type') ?? 'text/html' },
  })
}
