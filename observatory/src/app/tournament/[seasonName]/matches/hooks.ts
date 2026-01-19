import { useQueryStates } from 'nuqs'

import { nuqsParams } from './searchParams'

export function useMatchFilter() {
  const [matchFilter, setMatchFilter] = useQueryStates(nuqsParams, { shallow: false })
  return [matchFilter, setMatchFilter] as const
}
