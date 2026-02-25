'use client'

import clsx from 'clsx'
import Link from 'next/link'
import { useMemo, useState } from 'react'

import { StyledLink } from '@/components/StyledLink'
import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { matchesRoute, policyVersionRoute } from '@/lib/routes'
import { getPolicyColor } from './policyColor'
import { compareMissingLast, type ScoreSortDirection } from './scoreSort'
import { useFocusedPolicies } from './useFocusedPolicies'

type SortDirection = ScoreSortDirection
const stageSortPrefix = 'stage:'

type SortKey = 'player' | 'entered' | `${typeof stageSortPrefix}${string}`
type SortState = { key: SortKey; direction: SortDirection } | null

export type PlayersTableStageColumn = {
  key: string
  label: string
  selected: boolean
}

export type PlayersTableStageCell = {
  hasPool: boolean
  mean: number | null
  stddev: number | null
  completed: number
  failed: number
  pending: number
}

export type PlayersTableRow = {
  policyId: string
  policyLabel: string
  enteredAt: string
  enteredAtLabel: string
  stages: Record<string, PlayersTableStageCell>
  defaultRank: number
}

type PlayersSortableTableProps = {
  seasonName: string
  hasTournamentProgress: boolean
  showEnteredColumn: boolean
  columns: PlayersTableStageColumn[]
  rows: PlayersTableRow[]
}

function defaultSortDirection(sortKey: SortKey): SortDirection {
  return sortKey === 'player' ? 'asc' : 'desc'
}

export function PlayersSortableTable({
  seasonName,
  hasTournamentProgress,
  showEnteredColumn,
  columns,
  rows,
}: PlayersSortableTableProps) {
  const [sortState, setSortState] = useState<SortState>(null)
  const allPolicyIds = useMemo(() => rows.map((row) => row.policyId), [rows])
  const { focusedPolicyIds, focusedPolicyIdSet, hasFocusedPolicies, setFocusedPolicyIds, toggleFocusedPolicy } =
    useFocusedPolicies({
      validPolicyIds: allPolicyIds,
      orderedPolicyIds: allPolicyIds,
    })
  const hasAllPoliciesFocused = rows.length > 0 && focusedPolicyIds.length === rows.length

  const onSort = (sortKey: SortKey) => {
    setSortState((current) => {
      if (!current || current.key !== sortKey) {
        return { key: sortKey, direction: defaultSortDirection(sortKey) }
      }
      return { key: sortKey, direction: current.direction === 'asc' ? 'desc' : 'asc' }
    })
  }

  const getSortIndicator = (sortKey: SortKey) => {
    if (sortState?.key !== sortKey) return '\u25B4\u25BE'
    return sortState.direction === 'asc' ? '\u25B2' : '\u25BC'
  }

  const getSortAria = (sortKey: SortKey): 'ascending' | 'descending' | 'none' => {
    if (sortState?.key !== sortKey) return 'none'
    return sortState.direction === 'asc' ? 'ascending' : 'descending'
  }

  const sortedRows = useMemo(() => {
    const nextRows = [...rows]
    nextRows.sort((a, b) => {
      if (sortState?.key === 'player') {
        const byPlayer = a.policyLabel.localeCompare(b.policyLabel, undefined, { sensitivity: 'base' })
        if (byPlayer !== 0) return sortState.direction === 'asc' ? byPlayer : -byPlayer
      } else if (sortState?.key === 'entered' && showEnteredColumn) {
        const byEntered = a.enteredAt.localeCompare(b.enteredAt)
        if (byEntered !== 0) return sortState.direction === 'asc' ? byEntered : -byEntered
      } else if (sortState?.key?.startsWith(stageSortPrefix)) {
        const poolName = sortState.key.slice(stageSortPrefix.length)
        const aScore = a.stages[poolName]?.mean ?? undefined
        const bScore = b.stages[poolName]?.mean ?? undefined
        const byStage = compareMissingLast(aScore, bScore, sortState.direction)
        if (byStage !== 0) return byStage
      }

      return a.defaultRank - b.defaultRank
    })
    return nextRows
  }, [rows, showEnteredColumn, sortState])

  return (
    <Table>
      <TableHeader>
        <TH className="text-center">
          <div className="inline-flex flex-col items-center gap-0.5">
            <span>Show</span>
            <div className="inline-flex items-center gap-1">
              <button
                type="button"
                onClick={() => setFocusedPolicyIds(allPolicyIds)}
                disabled={allPolicyIds.length === 0 || hasAllPoliciesFocused}
                className={clsx(
                  'bg-transparent border-0 p-0 text-[10px] cursor-pointer',
                  hasAllPoliciesFocused
                    ? 'text-foreground'
                    : 'text-foreground-muted hover:text-foreground disabled:text-foreground-muted disabled:cursor-default'
                )}
                title="Focus all policies"
                aria-label="Focus all policies"
              >
                all
              </button>
              <button
                type="button"
                onClick={() => setFocusedPolicyIds([])}
                disabled={!hasFocusedPolicies}
                className="text-foreground-muted hover:text-foreground disabled:text-foreground-muted disabled:cursor-default cursor-pointer bg-transparent border-0 p-0 text-sm leading-none"
                title="Clear focused policies"
                aria-label="Clear focused policies"
              >
                ×
              </button>
            </div>
          </div>
        </TH>
        <TH className="text-left" aria-sort={getSortAria('player')}>
          <button
            type="button"
            onClick={() => onSort('player')}
            className="inline-flex items-center gap-0.5 cursor-pointer bg-transparent border-0 p-0 font-inherit text-inherit"
          >
            <span>Player</span>
            <span className="text-[10px] text-foreground-muted">{getSortIndicator('player')}</span>
          </button>
        </TH>
        {showEnteredColumn ? (
          <TH className="text-left" aria-sort={getSortAria('entered')}>
            <button
              type="button"
              onClick={() => onSort('entered')}
              className="inline-flex items-center gap-0.5 cursor-pointer bg-transparent border-0 p-0 font-inherit text-inherit"
            >
              <span>Entered</span>
              <span className="text-[10px] text-foreground-muted">{getSortIndicator('entered')}</span>
            </button>
          </TH>
        ) : null}
        {columns.map((column) => {
          const sortKey = `${stageSortPrefix}${column.key}` as SortKey
          return (
            <TH
              key={column.key}
              aria-sort={getSortAria(sortKey)}
              className={clsx(
                'text-right',
                column.selected ? 'bg-blue-100 dark:bg-blue-950/40 text-blue-800 dark:text-blue-200' : ''
              )}
            >
              <button
                type="button"
                onClick={() => onSort(sortKey)}
                className="inline-flex items-center gap-0.5 cursor-pointer bg-transparent border-0 p-0 font-inherit text-inherit"
              >
                <span>{column.label}</span>
                <span className="text-[10px] text-foreground-muted">{getSortIndicator(sortKey)}</span>
              </button>
            </TH>
          )
        })}
      </TableHeader>
      <TableBody>
        {sortedRows.map((row) => {
          const isFocused = focusedPolicyIdSet.has(row.policyId)
          const focusColor = getPolicyColor(row.defaultRank)

          return (
            <TR key={row.policyId}>
              <TD className="text-center">
                <button
                  type="button"
                  onClick={() => toggleFocusedPolicy(row.policyId)}
                  className={clsx(
                    'inline-flex h-5 w-5 items-center justify-center rounded border text-[11px] leading-none cursor-pointer transition-colors',
                    isFocused
                      ? 'text-white'
                      : 'border-border-subtle text-transparent hover:border-foreground-muted hover:text-foreground-muted'
                  )}
                  style={
                    isFocused
                      ? {
                          backgroundColor: focusColor,
                          borderColor: focusColor,
                        }
                      : undefined
                  }
                  title={isFocused ? `Unfocus ${row.policyLabel}` : `Focus ${row.policyLabel}`}
                  aria-label={isFocused ? `Unfocus ${row.policyLabel}` : `Focus ${row.policyLabel}`}
                >
                  ✓
                </button>
              </TD>
              <TD className="text-left">
                <StyledLink href={policyVersionRoute(row.policyId)} className="font-medium">
                  {row.policyLabel}
                </StyledLink>
              </TD>
              {showEnteredColumn ? (
                <TD className="text-left text-foreground-muted text-sm">{row.enteredAtLabel}</TD>
              ) : null}
              {columns.map((column) => {
                const stage = row.stages[column.key]
                if (!stage || !stage.hasPool) {
                  return (
                    <TD
                      key={column.key}
                      className={clsx('text-right text-foreground-muted', column.selected ? 'bg-blue-950/10' : '')}
                    >
                      -
                    </TD>
                  )
                }

                return (
                  <TD key={column.key} className={clsx('text-right', column.selected ? 'bg-blue-950/10' : '')}>
                    <div className="flex flex-col items-end gap-0.5 text-right">
                      <span className="font-mono text-sm">{stage.mean !== null ? stage.mean.toPrecision(4) : '-'}</span>
                      <span className="font-mono text-[0.7rem] text-foreground-muted">
                        +/- {stage.stddev !== null ? stage.stddev.toPrecision(4) : 'n/a'}
                      </span>
                      <Link
                        href={matchesRoute(seasonName, {
                          stage: hasTournamentProgress ? column.key : undefined,
                          pool_names: hasTournamentProgress ? undefined : [column.key],
                          policy_version_ids: [row.policyId],
                        })}
                        className="no-underline text-xs text-foreground-muted hover:text-blue-600 dark:hover:text-blue-400 cursor-pointer transition-colors"
                      >
                        {stage.completed} matches
                        {stage.failed > 0 && `, ${stage.failed} failed`}
                        {stage.pending > 0 && `, ${stage.pending} pending`}
                      </Link>
                    </div>
                  </TD>
                )
              })}
            </TR>
          )
        })}
      </TableBody>
    </Table>
  )
}
