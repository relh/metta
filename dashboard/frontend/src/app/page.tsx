import { headers } from 'next/headers'

import { BardoLobby } from '../components/BardoLobby'
import { DashboardClient } from '../components/DashboardClient'

function isBardoHost(hostValue: string | null): boolean {
  if (!hostValue) return false
  const normalized = hostValue.split(',')[0].trim().toLowerCase().replace(/:\d+$/, '')
  return normalized.startsWith('bardo.')
}

export default async function Page() {
  const requestHeaders = await headers()
  const host = requestHeaders.get('x-forwarded-host') || requestHeaders.get('host')
  if (isBardoHost(host)) {
    return <BardoLobby />
  }
  return <DashboardClient />
}
