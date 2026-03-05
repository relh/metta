import { Suspense } from 'react'

import { BardoLobby } from '../../components/BardoLobby'

export default function BardoPage() {
  return (
    <Suspense fallback={null}>
      <BardoLobby />
    </Suspense>
  )
}
