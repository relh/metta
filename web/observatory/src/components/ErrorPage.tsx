'use client'

import { useEffect } from 'react'

import { Button } from '@/components/Button'
import { useRegisterErrorReset, useResetError } from '@/components/ResetErrorContext'

export function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useRegisterErrorReset(reset)
  const resetError = useResetError()

  useEffect(() => {
    console.error(error)
  }, [error])

  return (
    <div className="rounded-md bg-red-100 dark:bg-red-900/30 p-4">
      <h2 className="text-xl font-bold mb-4 text-red-700 dark:text-red-400">Something went wrong!</h2>
      <pre className="whitespace-pre-wrap wrap-break-word">{error.message}</pre>
      <Button onClick={() => (resetError ?? reset)()}>Try again</Button>
    </div>
  )
}
