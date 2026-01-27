'use client'

import { parseAsString, useQueryState } from 'nuqs'
import { FC, useEffect, useState, useTransition } from 'react'

import { Input } from '@/components/Input'
import { Spinner } from '@/components/Spinner'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'

import { useResetError } from './ResetErrorContext'

const DEBOUNCE_MS = 300

export const SearchParamInput: FC<{ paramName: string; placeholder: string }> = ({ paramName, placeholder }) => {
  let [isPending, startTransition] = useTransition()

  const [q, setQ] = useQueryState(
    paramName,
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )

  // Local state for immediate input feedback
  const [localValue, setLocalValue] = useState(q)
  const debouncedValue = useDebouncedValue(localValue, DEBOUNCE_MS)
  const resetError = useResetError()

  // Sync debounced value to URL
  useEffect(() => {
    if (debouncedValue !== q) {
      setQ(debouncedValue || null)
      resetError?.()
    }
  }, [debouncedValue, q, setQ])

  // Sync URL changes back to local state (e.g., browser back/forward)
  useEffect(() => {
    setLocalValue(q)
  }, [q])

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex-1">
        <Input placeholder={placeholder} value={localValue} onChange={setLocalValue} />
        <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center gap-0.5">
          {isPending && (
            <div className="p-1">
              <Spinner />
            </div>
          )}
          {localValue && (
            // TODO - use a proper icon (extract icons code from gridworks to common package)
            <button
              type="button"
              onClick={() => setLocalValue('')}
              className="p-1 border-none bg-transparent text-gray-500 hover:text-gray-700 cursor-pointer leading-none"
              aria-label="Clear"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
