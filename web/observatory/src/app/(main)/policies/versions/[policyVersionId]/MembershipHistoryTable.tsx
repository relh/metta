'use client'
import { FC, useEffect, useMemo, useState } from 'react'
import Select from 'react-select'

import clsx from 'clsx'

import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { MembershipHistoryEntry } from '@/lib/repo'
import { formatRelativeTime } from '@/utils/datetime'

const ActionBadge: FC<{ action: string }> = ({ action }) => {
  const colors: Record<string, string> = {
    add: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
    remove: 'bg-surface-alt text-foreground-muted',
  }
  return (
    <span className={clsx('px-2 py-1 rounded text-xs font-medium', colors[action] || 'bg-surface-alt')}>{action}</span>
  )
}

const VersionBadge: FC<{ version: number | null }> = ({ version }) => {
  if (version === null) {
    return <span className="text-xs text-foreground-muted">-</span>
  }
  return <span className="px-2 py-1 rounded text-xs font-medium bg-surface-alt text-foreground-subtle">v{version}</span>
}

type SeasonOption = { value: string; label: string }
type VersionOption = { value: number | '__all__'; label: string }

const ALL_SEASONS: SeasonOption = { value: '__all__', label: 'All seasons' }
const ALL_VERSIONS: VersionOption = { value: '__all__', label: 'All versions' }

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
  const [selectedVersion, setSelectedVersion] = useState<VersionOption>(ALL_VERSIONS)

  const seasonOptions = useMemo(() => {
    const unique = [...new Set(memberships.map((m) => m.season_name))]
    return [ALL_SEASONS, ...unique.map((s) => ({ value: s, label: s }))]
  }, [memberships])

  const seasonVersions = useMemo(() => {
    const versions = new Map<string, number[]>()
    for (const entry of memberships) {
      if (entry.season_version === null) {
        continue
      }
      const existing = versions.get(entry.season_name) ?? []
      if (!existing.includes(entry.season_version)) {
        existing.push(entry.season_version)
      }
      versions.set(entry.season_name, existing)
    }
    for (const [season, values] of versions.entries()) {
      values.sort((a, b) => b - a)
      versions.set(season, values)
    }
    return versions
  }, [memberships])

  const versionOptions = useMemo(() => {
    if (selectedSeason.value === '__all__') {
      return [ALL_VERSIONS]
    }
    const versions = seasonVersions.get(selectedSeason.value) ?? []
    return [ALL_VERSIONS, ...versions.map((v) => ({ value: v, label: `v${v}` }))]
  }, [selectedSeason, seasonVersions])

  useEffect(() => {
    setSelectedVersion(ALL_VERSIONS)
  }, [selectedSeason])

  const filtered = useMemo(() => {
    const seasonFiltered =
      selectedSeason.value === '__all__'
        ? memberships
        : memberships.filter((m) => m.season_name === selectedSeason.value)
    if (selectedVersion.value === '__all__') {
      return seasonFiltered
    }
    return seasonFiltered.filter((m) => m.season_version === selectedVersion.value)
  }, [memberships, selectedSeason, selectedVersion])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="text-foreground-muted text-sm font-medium">Season:</span>
        <Select
          options={seasonOptions}
          value={selectedSeason}
          onChange={(option) => setSelectedSeason(option ?? ALL_SEASONS)}
          styles={selectStyles}
          isSearchable={false}
          instanceId="membership-season-filter"
        />
        <span className="text-foreground-muted text-sm font-medium">Version:</span>
        <Select
          options={versionOptions}
          value={selectedVersion}
          onChange={(option) => setSelectedVersion(option ?? ALL_VERSIONS)}
          styles={selectStyles}
          isSearchable={false}
          instanceId="membership-season-version-filter"
          isDisabled={selectedSeason.value === '__all__'}
        />
      </div>
      {filtered.length === 0 ? (
        <div className="text-foreground-muted text-sm">No membership changes for this filter.</div>
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
                <TD className="text-foreground-muted text-sm">{formatRelativeTime(entry.created_at)}</TD>
                <TD>
                  <div className="flex items-center gap-2">
                    <StyledLink href={`/tournament/${entry.season_name}`}>{entry.season_name}</StyledLink>
                    <VersionBadge version={entry.season_version} />
                  </div>
                </TD>
                <TD className="capitalize">{entry.pool_name}</TD>
                <TD>
                  <ActionBadge action={entry.action} />
                </TD>
                <TD className="text-sm text-foreground-muted">{entry.notes || '-'}</TD>
              </TR>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  )
}
