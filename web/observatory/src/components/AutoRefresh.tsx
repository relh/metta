'use client'
import { FC, useEffect } from 'react'

import { useAutoRefreshRegister } from './AutoRefreshProvider'

// Kept as a component (rather than a hook) for convenience in React Server Components.
// Registers the desired interval with the global AutoRefreshProvider.
export const AutoRefresh: FC<{ interval?: number }> = ({ interval = 5000 }) => {
  const register = useAutoRefreshRegister()

  useEffect(() => {
    return register(interval)
  }, [register, interval])

  return null
}
