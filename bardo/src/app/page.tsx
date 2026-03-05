import { Suspense } from 'react'

import { BardoLobby } from '../components/BardoLobby'

export default function Page() {
  return (
    <Suspense fallback={null}>
      <BardoLobby />
    </Suspense>
  )
}
