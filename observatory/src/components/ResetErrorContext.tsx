'use client'
import { useRouter } from 'next/navigation'
import { createContext, FC, PropsWithChildren, use, useCallback, useEffect, useRef, useTransition } from 'react'

type ResetErrorContextValue = {
  resetError: () => void
  isPending: boolean
  registerErrorReset: (reset: () => void) => void
  unregisterErrorReset: () => void
}

const ResetErrorContext = createContext<ResetErrorContextValue | null>(null)

export const ResetErrorProvider: FC<PropsWithChildren> = ({ children }) => {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const errorResetRef = useRef<(() => void) | null>(null)

  const registerErrorReset = useCallback((reset: () => void) => {
    errorResetRef.current = reset
  }, [])

  const unregisterErrorReset = useCallback(() => {
    errorResetRef.current = null
  }, [])

  const resetError = useCallback(() => {
    startTransition(() => {
      if (errorResetRef.current) {
        errorResetRef.current()
      }
      router.refresh()
    })
  }, [router])

  return (
    <ResetErrorContext
      value={{
        resetError,
        isPending,
        registerErrorReset,
        unregisterErrorReset,
      }}
    >
      {children}
    </ResetErrorContext>
  )
}

export function useResetError() {
  const context = use(ResetErrorContext)
  return context?.resetError
}

export function useRegisterErrorReset(reset: () => void) {
  const context = use(ResetErrorContext)
  useEffect(() => {
    context?.registerErrorReset(reset)
    return () => context?.unregisterErrorReset()
  }, [context, reset])
}
