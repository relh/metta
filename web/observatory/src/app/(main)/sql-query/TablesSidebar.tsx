'use client'
import clsx from 'clsx'
import { FC } from 'react'

import { Card } from '@/components/Card'
import { Spinner } from '@/components/Spinner'
import { TableInfo } from '@/lib/repo'

export interface QueryHistoryItem {
  query: string
  timestamp: number
  executionTime?: number
  rowCount?: number
  error?: boolean
}

export const TablesSidebar: FC<{
  tables: TableInfo[]
  tablesLoading: boolean
  selectedTable: string | null
  onTableClick: (tableName: string) => void
  queryHistory: QueryHistoryItem[]
  onHistoryItemClick: (query: string) => void
  onClearHistory: () => void
}> = ({ tables, tablesLoading, selectedTable, onTableClick, queryHistory, onHistoryItemClick, onClearHistory }) => {
  return (
    <div className="w-80 min-w-80 overflow-y-auto">
      <Card padding="sm">
        <h3 className="mb-3 mt-0 text-sm font-semibold uppercase tracking-none text-foreground-subtle">Tables</h3>

        {tablesLoading ? (
          <Spinner />
        ) : (
          <ul className="m-0 list-none p-0">
            {tables.map((table) => (
              <li
                key={table.table_name}
                className={clsx(
                  'mb-0.5 cursor-pointer rounded px-2.5 py-1.5 transition-colors',
                  selectedTable === table.table_name ? 'bg-blue-500 text-white' : 'hover:bg-surface-alt'
                )}
                onClick={() => onTableClick(table.table_name)}
              >
                <div className="text-sm font-medium">{table.table_name}</div>
                <div
                  className={clsx(
                    'text-xs',
                    selectedTable === table.table_name ? 'text-blue-100' : 'text-foreground-muted'
                  )}
                >
                  {table.column_count} columns &bull; {table.row_count.toLocaleString()} rows
                </div>
              </li>
            ))}
          </ul>
        )}

        {queryHistory.length > 0 && (
          <div className="mt-6 border-t border-border pt-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground-subtle">Query History</h3>
              <button
                className="rounded border border-border-strong bg-transparent px-2 py-0.5 text-xs text-foreground-muted hover:bg-surface-alt"
                onClick={onClearHistory}
              >
                Clear
              </button>
            </div>
            <ul className="m-0 max-h-72 list-none overflow-y-auto p-0">
              {queryHistory.map((item, index) => {
                const date = new Date(item.timestamp)
                const timeStr = date.toLocaleTimeString()
                const dateStr = date.toLocaleDateString()
                const isToday = new Date().toDateString() === date.toDateString()

                return (
                  <li
                    key={index}
                    className="mb-0.5 cursor-pointer rounded px-2.5 py-2 text-xs transition-colors hover:bg-surface-alt"
                    onClick={() => onHistoryItemClick(item.query)}
                    title={item.query}
                  >
                    <div className="mb-1 truncate font-mono text-xs text-foreground-subtle">{item.query}</div>
                    <div className="flex items-center justify-between text-[10px] text-foreground-muted">
                      <span>{isToday ? timeStr : dateStr}</span>
                      <span className={item.error ? 'text-red-500' : 'text-green-600'}>
                        {item.error ? 'Error' : item.rowCount !== undefined ? `${item.rowCount} rows` : ''}
                      </span>
                    </div>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </Card>
    </div>
  )
}
