'use client'
import { useRouter, useSearchParams } from 'next/navigation'
import { useEffect, useState } from 'react'

export default function AuthCallback() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [status, setStatus] = useState<'processing' | 'success' | 'error'>('processing')
  const [errorMessage, setErrorMessage] = useState<string>('')

  useEffect(() => {
    const token = searchParams.get('token')

    if (!token) {
      setStatus('error')
      setErrorMessage('No token received from authentication server')
      return
    }

    try {
      // set client-side cookie
      // TODO - use HttpOnly cookie, avoid direct calls to observatory backend from browsers
      // must match AUTH_COOKIE_NAME
      document.cookie = `observatory_auth_token=${token}; path=/`
      setStatus('success')

      const timeoutId = setTimeout(() => {
        router.push('/')
      }, 2000)

      return () => clearTimeout(timeoutId)
    } catch (error) {
      setStatus('error')
      setErrorMessage(error instanceof Error ? error.message : 'Failed to save authentication token')
    }
  }, [searchParams, router])

  return (
    <div className="min-h-screen flex items-center justify-center bg-amber-50 p-4">
      <div className="w-full max-w-lg bg-white/95 rounded-3xl border border-slate-200 shadow-2xl p-8 md:p-12 text-center">
        {status === 'processing' && (
          <>
            <div className="size-20 rounded-full flex items-center justify-center text-4xl mx-auto mb-5 border border-slate-200 bg-slate-100">
              ⏳
            </div>
            <h1 className="text-3xl font-semibold mb-3 text-slate-900">Processing...</h1>
            <p className="text-slate-500">Saving your authentication token</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="size-20 rounded-full flex items-center justify-center text-4xl mx-auto mb-5 border border-green-200 bg-green-100 text-green-700">
              ✓
            </div>
            <h1 className="text-3xl font-semibold mb-3 text-slate-900">You're all set!</h1>
            <p className="text-slate-500">Authentication complete. Redirecting you now...</p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="size-20 rounded-full flex items-center justify-center text-4xl mx-auto mb-5 border border-red-200 bg-red-100 text-red-700">
              ⚠
            </div>
            <h1 className="text-3xl font-semibold mb-3 text-slate-900">Something went wrong</h1>
            <p className="text-slate-500 mb-2">{errorMessage}</p>
            <p className="text-slate-500">Please retry the login process or contact support if the issue persists.</p>
            <button
              onClick={() => router.push('/')}
              className="mt-8 px-6 py-3 rounded-full bg-slate-900 text-white font-semibold uppercase tracking-wider text-sm hover:bg-slate-800 transition-colors"
            >
              Retry Login
            </button>
          </>
        )}
      </div>
    </div>
  )
}
