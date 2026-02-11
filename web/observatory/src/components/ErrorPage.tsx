'use client'

import { useEffect, useSyncExternalStore } from 'react'

import { Button } from '@/components/Button'
import { useRegisterErrorReset, useResetError } from '@/components/ResetErrorContext'
import {
  getServerSnapshot as getOutageServerSnapshot,
  getSnapshot as getOutageSnapshot,
  setOutageSimulated,
  subscribe as subscribeOutage,
} from '@/lib/debug/simulate-outage'

export function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useRegisterErrorReset(reset)
  const resetError = useResetError()
  const outageActive = useSyncExternalStore(subscribeOutage, getOutageSnapshot, getOutageServerSnapshot)

  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="rounded-md bg-red-100 dark:bg-red-900/30 p-4">
      <h2 className="text-xl font-bold mb-4 text-red-700 dark:text-red-400">Something went wrong!</h2>
      <pre className="whitespace-pre-wrap wrap-break-word">{error.message}</pre>
      <div className="flex gap-2 mt-4">
        <Button onClick={() => (resetError ?? reset)()}>Try again</Button>
        {outageActive && (
          <Button
            theme="primary"
            onClick={() => {
              setOutageSimulated(false)
              ;(resetError ?? reset)()
            }}
          >
            Disable Simulated Outage & Retry
          </Button>
        )}
      </div>
    </div>
  )
}
