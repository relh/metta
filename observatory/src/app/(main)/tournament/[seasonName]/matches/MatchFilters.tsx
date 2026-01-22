'use client'
import { FC } from 'react'
import Select from 'react-select'

import { PolicySummary, SeasonDetail } from '@/lib/repo'

import { formatPolicyDisplay } from '../utils'
import { useMatchFilter } from './hooks'

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
  multiValue: (base: any) => ({
    ...base,
    backgroundColor: '#dbeafe',
  }),
  multiValueLabel: (base: any) => ({
    ...base,
    color: '#1e40af',
    fontSize: '0.75rem',
    padding: '1px 4px',
  }),
  multiValueRemove: (base: any) => ({
    ...base,
    color: '#1e40af',
    ':hover': {
      backgroundColor: '#bfdbfe',
      color: '#1e3a8a',
    },
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

export const MatchFilters: FC<{ season: SeasonDetail; policies: PolicySummary[] }> = ({ season, policies }) => {
  const [matchFilter, setMatchFilter] = useMatchFilter()

  const poolOptions = season.pools.map((p) => ({ value: p.name, label: p.name }))
  const playerOptions = policies.map((p) => ({
    value: p.policy.id,
    label: formatPolicyDisplay(p),
  }))

  return (
    <div className="flex gap-4 mb-4 pb-4 border-b border-gray-100">
      <div className="flex-1">
        <div className="text-xs text-gray-500 mb-1">Pool</div>
        <Select
          isMulti
          options={poolOptions}
          value={poolOptions.filter((o) => matchFilter.pool_names.includes(o.value))}
          onChange={(selected) => setMatchFilter((f) => ({ ...f, pool_names: selected.map((s) => s.value) }))}
          placeholder="All pools"
          styles={selectStyles}
          isClearable
          instanceId="pool-select"
        />
      </div>
      <div className="flex-1">
        <div className="text-xs text-gray-500 mb-1">Players</div>
        <Select
          isMulti
          options={playerOptions}
          value={playerOptions.filter((o) => matchFilter.policy_version_ids.includes(o.value))}
          onChange={(selected) => setMatchFilter((f) => ({ ...f, policy_version_ids: selected.map((s) => s.value) }))}
          placeholder="All players"
          styles={selectStyles}
          isClearable
          instanceId="player-select"
        />
      </div>
    </div>
  )
}
