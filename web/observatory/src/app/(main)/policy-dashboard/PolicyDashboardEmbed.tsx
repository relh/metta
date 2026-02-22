'use client'

import { useEffect, useState } from 'react'

import { syncAuthCookieToSharedDomain } from '@/auth/browser'

export function PolicyDashboardEmbed({ src }: { src: string }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    // Ensure policy-dashboard subdomain can read auth before iframe data requests fire.
    syncAuthCookieToSharedDomain()
    setReady(true)
  }, [])

  if (!ready) {
    return (
      <div className="h-full w-full flex items-center justify-center text-foreground-muted">
        Preparing dashboard session...
      </div>
    )
  }

  return <iframe title="Policy Dashboard" src={src} className="h-full w-full border-0 bg-background" />
}
