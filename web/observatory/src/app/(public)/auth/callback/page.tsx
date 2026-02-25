'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

import { writeAuthCookieToken } from '@/auth/browser'
import { sanitizeRedirectPath } from '@/utils/redirect'

import { validateToken } from './actions'

export default function AuthCallback() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [status, setStatus] = useState<
    | {
        type: 'processing'
      }
    | {
        type: 'success'
      }
    | { type: 'error'; message: string }
  >({ type: 'processing' })

  useEffect(() => {
    const token = searchParams.get('token')

    if (!token) {
      setStatus({ type: 'error', message: 'No token received from authentication server' })
      return
    }

    async function processToken(authToken: string) {
      const validation = await validateToken(authToken)

      if (!validation.valid) {
        setStatus({ type: 'error', message: validation.error ?? 'Invalid or expired token' })
        return
      }

      // TODO - use HttpOnly cookie, avoid direct calls to observatory backend from browsers
      // must match AUTH_COOKIE_NAME
      writeAuthCookieToken(authToken)
      setStatus({ type: 'success' })

      setTimeout(() => {
        router.push(sanitizeRedirectPath(searchParams.get('observatory_url')))
      }, 2000)
    }

    processToken(token)
  }, [searchParams, router])

  return (
    <div className="min-h-[80vh] flex items-center justify-center p-4">
      <div className="w-full max-w-lg bg-surface/95 rounded-3xl border border-border shadow-2xl p-8 md:p-12 text-center">
        {status.type === 'processing' && (
          <>
            <div className="size-20 rounded-full flex items-center justify-center text-4xl mx-auto mb-5 border border-border bg-surface-alt">
              ⏳
            </div>
            <h1 className="text-3xl font-semibold mb-3 text-foreground">Processing...</h1>
            <p className="text-foreground-muted">Validating your authentication token</p>
          </>
        )}

        {status.type === 'success' && (
          <>
            <div className="size-20 rounded-full flex items-center justify-center text-4xl mx-auto mb-5 border border-green-200 bg-green-100 text-green-700">
              ✓
            </div>
            <h1 className="text-3xl font-semibold mb-3 text-foreground">You're all set!</h1>
            <p className="text-foreground-muted">Authentication complete. Redirecting you now...</p>
          </>
        )}

        {status.type === 'error' && (
          <>
            <div className="size-20 rounded-full flex items-center justify-center text-4xl mx-auto mb-5 border border-red-200 bg-red-100 text-red-700">
              ⚠
            </div>
            <h1 className="text-3xl font-semibold mb-3 text-foreground">Something went wrong</h1>
            <p className="text-red-500 mb-2 text-lg">{status.message}</p>
            <button
              onClick={() => router.push('/')}
              className="mt-8 px-6 py-3 rounded-full bg-foreground text-surface font-semibold uppercase tracking-wider text-sm hover:bg-foreground-subtle transition-colors"
            >
              Retry Login
            </button>
          </>
        )}
      </div>
    </div>
  )
}
