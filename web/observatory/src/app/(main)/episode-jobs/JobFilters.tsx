'use client'
import { parseAsString, useQueryState } from 'nuqs'
import { FC, useCallback, useEffect, useRef, useState, useTransition } from 'react'
import Select from 'react-select'
import AsyncSelect from 'react-select/async'

import { Spinner } from '@/components/Spinner'
import { ALL_JOB_STATUSES, JobStatus, PublicPolicyVersionRow } from '@/lib/repo'

const selectStyles = {
  control: (base: any) => ({
    ...base,
    minHeight: '32px',
    fontSize: '0.75rem',
  }),
  valueContainer: (base: any) => ({
    ...base,
    padding: '0 6px',
  }),
  singleValue: (base: any) => ({
    ...base,
    fontSize: '0.75rem',
  }),
  option: (base: any) => ({
    ...base,
    fontSize: '0.75rem',
    padding: '6px 10px',
  }),
  placeholder: (base: any) => ({
    ...base,
    fontSize: '0.75rem',
  }),
}

type Option = { value: string; label: string }

function formatPolicyOption(pv: PublicPolicyVersionRow): string {
  if (pv.name && pv.version != null) return `${pv.name}:v${pv.version}`
  return pv.id.slice(0, 8)
}

async function searchPolicies(query: string): Promise<Option[]> {
  const params = new URLSearchParams({ limit: '20' })
  if (query) params.set('name_fuzzy', query)
  const resp = await fetch(`/api/policy-versions?${params}`)
  const entries: PublicPolicyVersionRow[] = await resp.json()
  return entries.map((pv) => ({ value: pv.id, label: formatPolicyOption(pv) }))
}

const DEBOUNCE_MS = 300

const PolicySelect: FC = () => {
  const [isPending, startTransition] = useTransition()
  const [policyVersionId, setPolicyVersionId] = useQueryState(
    'policyVersionId',
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )

  const [selected, setSelected] = useState<Option | null>(null)
  const resolvedRef = useRef(false)

  useEffect(() => {
    if (policyVersionId && !resolvedRef.current) {
      resolvedRef.current = true
      searchPolicies('').then((options) => {
        const match = options.find((o) => o.value === policyVersionId)
        if (match) setSelected(match)
        else setSelected({ value: policyVersionId, label: policyVersionId.slice(0, 8) })
      })
    }
  }, [policyVersionId])

  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const loadOptions = useCallback((inputValue: string, callback: (options: Option[]) => void) => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      searchPolicies(inputValue).then(callback)
    }, DEBOUNCE_MS)
  }, [])

  return (
    <div className="flex items-center gap-2">
      <div className="w-64">
        <AsyncSelect<Option>
          value={selected}
          onChange={(opt) => {
            setSelected(opt)
            setPolicyVersionId(opt?.value ?? null)
          }}
          loadOptions={loadOptions}
          defaultOptions
          placeholder="Search policies..."
          styles={selectStyles}
          isClearable
          instanceId="policy-select"
          cacheOptions
        />
      </div>
      {isPending && <Spinner />}
    </div>
  )
}

const StatusSelect: FC = () => {
  const [isPending, startTransition] = useTransition()
  const [status, setStatus] = useQueryState(
    'status',
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )

  const options: Option[] = ALL_JOB_STATUSES.map((s) => ({ value: s, label: s }))
  const selected = options.find((o) => o.value === status) ?? null

  return (
    <div className="flex items-center gap-2">
      <div className="w-40">
        <Select<Option>
          options={options}
          value={selected}
          onChange={(opt) => setStatus((opt?.value as JobStatus) ?? null)}
          placeholder="All statuses"
          styles={selectStyles}
          isClearable
          instanceId="status-select"
        />
      </div>
      {isPending && <Spinner />}
    </div>
  )
}

export const JobFilters: FC = () => {
  return (
    <>
      <div>
        <div className="text-xs text-gray-500 mb-1">Policy</div>
        <PolicySelect />
      </div>
      <div>
        <div className="text-xs text-gray-500 mb-1">Status</div>
        <StatusSelect />
      </div>
    </>
  )
}
