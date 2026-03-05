import { headers } from 'next/headers'

import { BardoLobby } from '../components/BardoLobby'
import { ChatpropSnapshot } from '../components/ChatpropSnapshot'
import { DashboardClient } from '../components/DashboardClient'
import { TrainBoardSnapshot } from '../components/TrainBoardSnapshot'
import { serviceForHost } from '../lib/host-routing'

export default async function Page() {
  const requestHeaders = await headers()
  const host = requestHeaders.get('x-forwarded-host') || requestHeaders.get('host')
  const service = serviceForHost(host)

  if (service === 'bardo') {
    return <BardoLobby />
  }
  if (service === 'train-board') {
    return <TrainBoardSnapshot />
  }
  if (service === 'chatprop') {
    return <ChatpropSnapshot />
  }
  return <DashboardClient />
}
