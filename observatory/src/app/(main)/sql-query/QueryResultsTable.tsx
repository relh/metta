'use client'
import clsx from 'clsx'
import { FC, useState } from 'react'

import { Table, TableBody, TableHeader, TD, TH, TR } from '@/components/Table'
import { SQLQueryResponse } from '@/lib/repo'

function formatCell(cell: unknown) {
  if (cell === null) return <em className="text-gray-400">NULL</em>
  if (typeof cell === 'object') return JSON.stringify(cell)
  return String(cell)
}

export const QueryResultsTable: FC<{
  data: SQLQueryResponse
}> = ({ data }) => {
  const [sortConfig, setSortConfig] = useState<{ column: string; direction: 'asc' | 'desc' } | null>(null)

  function handleSort(column: string) {
    let direction: 'asc' | 'desc' = 'asc'
    if (sortConfig && sortConfig.column === column && sortConfig.direction === 'asc') {
      direction = 'desc'
    }
    setSortConfig({ column, direction })
  }

  function getSortedRows() {
    if (!sortConfig) {
      return data.rows
    }

    const columnIndex = data.columns.indexOf(sortConfig.column)
    if (columnIndex === -1) return data.rows

    return [...data.rows].sort((a, b) => {
      const aVal = a[columnIndex]
      const bVal = b[columnIndex]

      if (aVal === null && bVal === null) return 0
      if (aVal === null) return sortConfig.direction === 'asc' ? 1 : -1
      if (bVal === null) return sortConfig.direction === 'asc' ? -1 : 1

      if (typeof aVal === 'number' && typeof bVal === 'number') {
        return sortConfig.direction === 'asc' ? aVal - bVal : bVal - aVal
      }

      const aStr = String(aVal).toLowerCase()
      const bStr = String(bVal).toLowerCase()

      if (sortConfig.direction === 'asc') {
        return aStr < bStr ? -1 : aStr > bStr ? 1 : 0
      } else {
        return aStr > bStr ? -1 : aStr < bStr ? 1 : 0
      }
    })
  }

  return (
    <div className="overflow-x-auto">
      <Table theme="large">
        <TableHeader>
          {data.columns.map((col) => (
            <TH
              key={col}
              onClick={() => handleSort(col)}
              className={clsx(
                'cursor-pointer select-none transition-colors hover:bg-gray-100',
                sortConfig?.column === col && 'text-blue-600'
              )}
            >
              {col}
              {sortConfig?.column === col && (
                <span className="ml-1 text-blue-500">{sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
              )}
            </TH>
          ))}
        </TableHeader>
        <TableBody>
          {getSortedRows().map((row, idx) => (
            <TR key={idx} className="hover:bg-gray-50">
              {row.map((cell, cellIdx) => (
                <TD key={cellIdx} className="text-xs">
                  {formatCell(cell)}
                </TD>
              ))}
            </TR>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
