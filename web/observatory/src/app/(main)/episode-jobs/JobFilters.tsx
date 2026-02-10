'use client'
import { parseAsString, useQueryState } from 'nuqs'
import { FC, useCallback, useEffect, useMemo, useRef, useState, useTransition } from 'react'
import Select from 'react-select'
import AsyncSelect from 'react-select/async'

import { Spinner } from '@/components/Spinner'
import { ALL_JOB_STATUSES, JobStatus, PublicPolicyVersionRow, SeasonDetail } from '@/lib/repo'

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

const PolicySelect: FC<{ defaultPolicyVersionId?: string }> = ({ defaultPolicyVersionId }) => {
  const [isPending, startTransition] = useTransition()
  const [policyVersionId, setPolicyVersionId] = useQueryState(
    'policyVersionId',
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )

  const effectiveId = policyVersionId || defaultPolicyVersionId || ''
  const [selected, setSelected] = useState<Option | null>(null)
  const lastResolvedId = useRef('')

  useEffect(() => {
    if (effectiveId && effectiveId !== lastResolvedId.current) {
      lastResolvedId.current = effectiveId
      searchPolicies('').then((options) => {
        const match = options.find((o) => o.value === effectiveId)
        if (match) setSelected(match)
        else setSelected({ value: effectiveId, label: effectiveId.slice(0, 8) })
      })
    } else if (!effectiveId) {
      lastResolvedId.current = ''
      setSelected(null)
    }
  }, [effectiveId])

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
      <span className={isPending ? 'visible' : 'invisible'}>
        <Spinner />
      </span>
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
      <span className={isPending ? 'visible' : 'invisible'}>
        <Spinner />
      </span>
    </div>
  )
}

const SeasonSelect: FC<{ seasons: SeasonDetail[] }> = ({ seasons }) => {
  const [isPending, startTransition] = useTransition()
  const [seasonId, setSeasonId] = useQueryState(
    'seasonId',
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )

  type SeasonOption = Option & { version: number }
  const options: SeasonOption[] = useMemo(
    () => seasons.map((s) => ({ value: s.id, label: s.name, version: s.version })),
    [seasons]
  )
  const selected = options.find((o) => o.value === seasonId) ?? null

  return (
    <div className="flex items-center gap-2">
      <div className="w-48">
        <Select<SeasonOption>
          options={options}
          value={selected}
          onChange={(opt) => setSeasonId(opt?.value ?? null)}
          formatOptionLabel={(opt) => (
            <span>
              {opt.label} <span className="text-foreground-muted">(v{opt.version})</span>
            </span>
          )}
          placeholder="All seasons"
          styles={selectStyles}
          isClearable
          instanceId="season-select"
        />
      </div>
      <span className={isPending ? 'visible' : 'invisible'}>
        <Spinner />
      </span>
    </div>
  )
}

const PoolSelect: FC<{ seasons: SeasonDetail[] }> = ({ seasons }) => {
  const [isPending, startTransition] = useTransition()
  const [seasonId] = useQueryState('seasonId', parseAsString.withDefault(''))
  const [poolId, setPoolId] = useQueryState(
    'poolId',
    parseAsString.withDefault('').withOptions({
      shallow: false,
      history: 'replace',
      startTransition,
    })
  )

  const options: Option[] = useMemo(() => {
    if (!seasonId) return []
    const season = seasons.find((s) => s.id === seasonId)
    if (!season) return []
    return season.pools.flatMap((p) => (p.id ? [{ value: p.id, label: p.name }] : []))
  }, [seasons, seasonId])

  useEffect(() => {
    if (poolId && !options.find((o) => o.value === poolId)) {
      setPoolId(null)
    }
  }, [options, poolId, setPoolId])

  const selected = options.find((o) => o.value === poolId) ?? null

  return (
    <div className="flex items-center gap-2">
      <div className="w-48">
        <Select<Option>
          options={options}
          value={selected}
          onChange={(opt) => setPoolId(opt?.value ?? null)}
          placeholder={seasonId ? 'All pools' : 'Select a season first'}
          isDisabled={!seasonId}
          styles={selectStyles}
          isClearable
          instanceId="pool-select"
        />
      </div>
      <span className={isPending ? 'visible' : 'invisible'}>
        <Spinner />
      </span>
    </div>
  )
}

export const JobFilters: FC<{ seasons: SeasonDetail[]; defaultPolicyVersionId?: string }> = ({
  seasons,
  defaultPolicyVersionId,
}) => {
  return (
    <>
      <div>
        <div className="text-xs text-foreground-muted mb-1">Policy</div>
        <PolicySelect defaultPolicyVersionId={defaultPolicyVersionId} />
      </div>
      <div>
        <div className="text-xs text-foreground-muted mb-1">Status</div>
        <StatusSelect />
      </div>
      <div>
        <div className="text-xs text-foreground-muted mb-1">Season</div>
        <SeasonSelect seasons={seasons} />
      </div>
      <div>
        <div className="text-xs text-foreground-muted mb-1">Pool</div>
        <PoolSelect seasons={seasons} />
      </div>
    </>
  )
}
