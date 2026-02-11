'use client'
import { useRouter } from 'next/navigation'
import { createContext, FC, PropsWithChildren, useCallback, useContext, useEffect, useRef, useState } from 'react'

interface AutoRefreshContextValue {
  /** Currently active interval in ms, or null if no auto-refresh is registered */
  intervalMs: number | null
  /** Register an auto-refresh interval. Returns an unregister function. */
  register: (intervalMs: number) => () => void
}

const AutoRefreshContext = createContext<AutoRefreshContextValue>({
  intervalMs: null,
  register: () => () => {},
})

export const useAutoRefreshInterval = () => useContext(AutoRefreshContext).intervalMs

export const useAutoRefreshRegister = () => useContext(AutoRefreshContext).register

export const AutoRefreshProvider: FC<PropsWithChildren> = ({ children }) => {
  const router = useRouter()
  // Map of registration id -> interval in ms
  const registrationsRef = useRef<Map<number, number>>(new Map())
  const nextIdRef = useRef(0)
  const [activeInterval, setActiveInterval] = useState<number | null>(null)

  const recalculate = useCallback(() => {
    const values = Array.from(registrationsRef.current.values())
    setActiveInterval(values.length > 0 ? Math.min(...values) : null)
  }, [])

  const register = useCallback(
    (intervalMs: number) => {
      const id = nextIdRef.current++
      registrationsRef.current.set(id, intervalMs)
      recalculate()
      return () => {
        registrationsRef.current.delete(id)
        recalculate()
      }
    },
    [recalculate]
  )

  useEffect(() => {
    if (activeInterval === null) return
    const timerId = setInterval(() => {
      router.refresh()
    }, activeInterval)
    return () => clearInterval(timerId)
  }, [activeInterval, router])

  return <AutoRefreshContext value={{ intervalMs: activeInterval, register }}>{children}</AutoRefreshContext>
}
