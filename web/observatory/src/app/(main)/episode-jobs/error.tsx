'use client'

import { useEffect } from 'react'

import { Button } from '@/components/Button'
import { useRegisterErrorReset } from '@/components/ResetErrorContext'

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useRegisterErrorReset(reset)

  useEffect(() => {
    // Log the error to an error reporting service
    console.error(error)
  }, [error])

  return (
    <div className="rounded-md bg-red-100 dark:bg-red-900/30 p-4">
      <h2 className="text-xl font-bold mb-4 text-red-700 dark:text-red-400">Something went wrong!</h2>
      <pre>{error.message}</pre>
      <Button
        onClick={
          // Attempt to recover by trying to re-render the segment
          () => reset()
        }
      >
        Try again
      </Button>
    </div>
  )
}
