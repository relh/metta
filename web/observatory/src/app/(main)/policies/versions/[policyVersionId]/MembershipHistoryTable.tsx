'use client'
import { FC, useMemo, useState } from 'react'
import Select from 'react-select'

import clsx from 'clsx'

import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { MembershipHistoryEntry } from '@/lib/repo'
import { formatRelativeTime } from '@/utils/datetime'

const ActionBadge: FC<{ action: string }> = ({ action }) => {
  const colors: Record<string, string> = {
    add: 'bg-green-100 text-green-800',
    remove: 'bg-gray-100 text-gray-600',
  }
  return (
    <span className={clsx('px-2 py-1 rounded text-xs font-medium', colors[action] || 'bg-gray-100')}>{action}</span>
  )
}

type SeasonOption = { value: string; label: string }

const ALL_SEASONS: SeasonOption = { value: '__all__', label: 'All seasons' }

const selectStyles = {
  control: (base: any) => ({
    ...base,
    minHeight: '36px',
    fontSize: '0.875rem',
    minWidth: '180px',
  }),
  option: (base: any) => ({
    ...base,
    fontSize: '0.875rem',
    padding: '6px 12px',
  }),
}

export const MembershipHistoryTable: FC<{ memberships: MembershipHistoryEntry[] }> = ({ memberships }) => {
  const [selectedSeason, setSelectedSeason] = useState<SeasonOption>(ALL_SEASONS)

  const seasonOptions = useMemo(() => {
    const unique = [...new Set(memberships.map((m) => m.season_name))]
    return [ALL_SEASONS, ...unique.map((s) => ({ value: s, label: s }))]
  }, [memberships])

  const filtered = useMemo(
    () =>
      selectedSeason.value === '__all__'
        ? memberships
        : memberships.filter((m) => m.season_name === selectedSeason.value),
    [memberships, selectedSeason]
  )

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-gray-600 text-sm font-medium">Season:</span>
        <Select
          options={seasonOptions}
          value={selectedSeason}
          onChange={(option) => setSelectedSeason(option ?? ALL_SEASONS)}
          styles={selectStyles}
          isSearchable={false}
          instanceId="membership-season-filter"
        />
      </div>
      {filtered.length === 0 ? (
        <div className="text-gray-500 text-sm">No membership changes for this filter.</div>
      ) : (
        <Table>
          <TableHeader>
            <TH>Time</TH>
            <TH>Season</TH>
            <TH>Pool</TH>
            <TH>Action</TH>
            <TH>Notes</TH>
          </TableHeader>
          <TableBody>
            {filtered.map((entry, i) => (
              <TR key={i}>
                <TD className="text-gray-500 text-sm">{formatRelativeTime(entry.created_at)}</TD>
                <TD>
                  <StyledLink href={`/tournament/${entry.season_name}`}>{entry.season_name}</StyledLink>
                </TD>
                <TD className="capitalize">{entry.pool_name}</TD>
                <TD>
                  <ActionBadge action={entry.action} />
                </TD>
                <TD className="text-sm text-gray-600">{entry.notes || '-'}</TD>
              </TR>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
