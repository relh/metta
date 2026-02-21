'use client'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { useCallback, useMemo } from 'react'

import { FOCUS_POLICY_QUERY_KEY, parseFocusedPolicyIds, withFocusedPolicyIds } from './focusPolicyQuery'

type UseFocusedPoliciesArgs = {
  validPolicyIds: string[]
  orderedPolicyIds: string[]
}

type UseFocusedPoliciesResult = {
  focusedPolicyIds: string[]
  focusedPolicyIdSet: Set<string>
  hasFocusedPolicies: boolean
  setFocusedPolicyIds: (policyIds: string[]) => void
  toggleFocusedPolicy: (policyId: string) => void
}

export function useFocusedPolicies({
  validPolicyIds,
  orderedPolicyIds,
}: UseFocusedPoliciesArgs): UseFocusedPoliciesResult {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const validPolicyIdSet = useMemo(() => new Set(validPolicyIds), [validPolicyIds])

  const focusedPolicyIds = useMemo(() => {
    const rawPolicyIds = parseFocusedPolicyIds(searchParams.get(FOCUS_POLICY_QUERY_KEY))
    return rawPolicyIds.filter((policyId) => validPolicyIdSet.has(policyId))
  }, [searchParams, validPolicyIdSet])

  const focusedPolicyIdSet = useMemo(() => new Set(focusedPolicyIds), [focusedPolicyIds])
  const hasFocusedPolicies = focusedPolicyIds.length > 0

  const setFocusedPolicyIds = useCallback(
    (policyIds: string[]) => {
      const nextPolicyIds = policyIds.filter((policyId) => validPolicyIdSet.has(policyId))
      const next = withFocusedPolicyIds(new URLSearchParams(searchParams.toString()), nextPolicyIds)
      const query = next.toString()
      router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
    },
    [pathname, router, searchParams, validPolicyIdSet]
  )

  const toggleFocusedPolicy = useCallback(
    (policyId: string) => {
      if (!validPolicyIdSet.has(policyId)) {
        return
      }
      const nextSet = new Set(focusedPolicyIds)
      if (nextSet.has(policyId)) {
        nextSet.delete(policyId)
      } else {
        nextSet.add(policyId)
      }

      const orderedFocusedPolicyIds = orderedPolicyIds.filter((id) => nextSet.has(id))
      setFocusedPolicyIds(orderedFocusedPolicyIds)
    },
    [focusedPolicyIds, orderedPolicyIds, setFocusedPolicyIds, validPolicyIdSet]
  )

  return {
    focusedPolicyIds,
    focusedPolicyIdSet,
    hasFocusedPolicies,
    setFocusedPolicyIds,
    toggleFocusedPolicy,
  }
}
