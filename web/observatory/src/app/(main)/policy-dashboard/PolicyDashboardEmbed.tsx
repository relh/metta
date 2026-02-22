'use client'

import { useEffect, useState } from 'react'

import { syncAuthCookieToSharedDomain } from '@/auth/browser'

export function PolicyDashboardEmbed({ src }: { src: string }) {
  const [ready, setReady] = useState(false)
  const [themedSrc, setThemedSrc] = useState(src)

  useEffect(() => {
    function resolveThemedSrc(): string {
      try {
        const url = new URL(src, window.location.origin)
        const isDark = document.documentElement.classList.contains('dark')
        url.searchParams.set('theme', isDark ? 'dark' : 'light')
        return url.toString()
      } catch {
        return src
      }
    }

    const updateThemedSrc = () => setThemedSrc(resolveThemedSrc())

    // Ensure policy-dashboard subdomain can read auth before iframe data requests fire.
    syncAuthCookieToSharedDomain()
    updateThemedSrc()

    const observer = new MutationObserver(updateThemedSrc)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
    setReady(true)

    return () => observer.disconnect()
  }, [src])

  if (!ready) {
    return (
      <div className="h-full w-full flex items-center justify-center text-foreground-muted">
        Preparing dashboard session...
      </div>
    )
  }

  return <iframe title="Policy Dashboard" src={themedSrc} className="h-full w-full border-0 bg-background" />
}
