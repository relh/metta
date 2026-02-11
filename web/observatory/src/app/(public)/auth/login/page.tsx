'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useState } from 'react'

import { Button } from '@/components/Button'
import { Card } from '@/components/Card'
import { sanitizeRedirectPath } from '@/utils/redirect'

import { getAuthUrl } from './actions'

export default function LoginPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const redirectPath = sanitizeRedirectPath(searchParams.get('redirect'))
  const [loading, setLoading] = useState(false)

  const handleSignIn = useCallback(async () => {
    setLoading(true)
    const authUrl = await getAuthUrl(redirectPath)
    router.replace(authUrl)
  }, [redirectPath, router])

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md text-center">
        <Card>
          <div className="p-4">
            <h1 className="text-3xl font-semibold text-foreground leading-none m-0 mb-6">Softmax Observatory</h1>
            <Button onClick={handleSignIn} disabled={loading} theme="primary" size="lg" wide>
              {loading ? 'Redirecting...' : 'Sign in'}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}
