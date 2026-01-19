'use client'
import { useRouter } from 'next/navigation'
import { FC, useEffect } from 'react'

// component instead of hook for convenience in React Server Components
export const AutoRefresh: FC<{ interval?: number }> = ({ interval = 5000 }) => {
  const router = useRouter()

  useEffect(() => {
    const intervalId = setInterval(() => {
      router.refresh()
    }, interval)
    return () => clearInterval(intervalId)
  }, [interval])

  return null
}
