'use client'

import clsx from 'clsx'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { FC, Fragment } from 'react'

import type { ProgressResponse, StageStats } from '@/lib/api'
import { buildStageProgressItems } from '@/lib/tournament/viewModels'

import { resolveSelectedStage } from './stageSelection'

type ProgressStage = ProgressResponse['stage_flow'][number]

export const StageProgress: FC<{
  stageFlow: ProgressStage[]
  stages: StageStats[]
  defaultStage: string
  started: boolean
}> = ({ stageFlow, stages, defaultStage, started }) => {
  const router = useRouter()
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const progressItems = buildStageProgressItems(stageFlow, stages).map((stage) => ({
    ...stage,
    status: !started && stage.status === 'active' ? 'pending' : stage.status,
  }))
  const selectedStage = resolveSelectedStage(stages, stageFlow, searchParams?.get('stage') ?? defaultStage, started)
  const selectedProgressItem =
    progressItems.find((stage) => stage.inputPool === selectedStage) ??
    progressItems.find((stage) => stage.status === 'active') ??
    progressItems[0]

  const onSelect = (stage: string) => {
    const nextParams = new URLSearchParams(searchParams?.toString() ?? '')
    nextParams.set('stage', stage)
    nextParams.delete('pool_names')
    nextParams.delete('pool_name')
    nextParams.delete('match_page')
    nextParams.delete('teams_page')
    const query = nextParams.toString()
    router.replace(query ? `${pathname}?${query}` : pathname)
  }

  const formatCount = (count: number | null) => (count === null ? '—' : count.toLocaleString())

  return (
    <div className="space-y-3 rounded-md border border-border px-3 py-2">
      <div className="overflow-x-auto pb-1">
        <div className="flex w-max min-w-full items-start justify-center gap-0">
          {progressItems.map((stage, idx) => {
            const isPending = stage.status === 'pending'
            const isSelected = selectedProgressItem?.inputPool === stage.inputPool
            const compactTitle = stage.title.split(/\s+/).slice(0, 2).join(' ')
            const selectedRingClass = !isSelected
              ? 'opacity-70 hover:opacity-100'
              : stage.status === 'active'
                ? 'opacity-100 ring-2 ring-green-300/70 shadow-none'
                : stage.status === 'complete'
                  ? 'opacity-100 ring-2 ring-blue-300/70 shadow-none'
                  : 'opacity-100 ring-2 ring-foreground-muted/40 shadow-none'
            const toneClass = isSelected
              ? stage.status === 'active'
                ? 'border-green-400 bg-green-100 text-green-950 dark:border-green-300 dark:bg-green-500/25 dark:text-green-100'
                : stage.status === 'complete'
                  ? 'border-blue-400 bg-blue-100 text-blue-950 dark:border-blue-300 dark:bg-blue-500/25 dark:text-blue-100'
                  : 'border-border-strong bg-surface-alt text-foreground'
              : stage.status === 'active'
                ? 'border-green-900/60 bg-green-950/15 text-foreground-muted hover:border-green-700 hover:bg-green-950/25 hover:text-foreground'
                : stage.status === 'complete'
                  ? 'border-blue-900/60 bg-blue-950/15 text-foreground-muted hover:border-blue-700 hover:bg-blue-950/25 hover:text-foreground'
                  : 'border-border bg-surface text-foreground-muted hover:bg-surface-alt hover:text-foreground'
            const statusLabel = stage.status === 'active' ? 'active' : !started && isSelected ? 'not started' : null
            return (
              <Fragment key={stage.index}>
                {idx > 0 && (
                  <div
                    aria-hidden="true"
                    className="grid place-items-center px-0.5 pt-4 text-sm font-semibold text-foreground-muted select-none"
                  >
                    →
                  </div>
                )}
                <div className="w-[5.75rem] shrink-0">
                  <button
                    type="button"
                    onClick={() => onSelect(stage.inputPool)}
                    title={`${stage.index}. ${stage.title}`}
                    className={clsx(
                      'min-h-[3.1rem] w-full rounded-md border py-2 px-2 text-left transition-[background-color,border-color,opacity,box-shadow]',
                      'cursor-pointer',
                      isPending ? 'saturate-75' : '',
                      selectedRingClass,
                      toneClass
                    )}
                  >
                    <div className="flex items-start gap-1.5">
                      <span className="rounded bg-surface-alt px-1.5 py-0.5 text-[11px] font-semibold text-foreground-muted">
                        {stage.index}
                      </span>
                      <div className="text-[11px] leading-4 font-semibold whitespace-normal break-words">
                        {compactTitle}
                      </div>
                    </div>
                  </button>
                  {statusLabel && (
                    <div className="mt-1">
                      <span
                        className={clsx(
                          'pointer-events-none select-none rounded px-1.5 py-0.5 text-[10px] font-medium',
                          statusLabel === 'active'
                            ? 'bg-green-200 text-green-900 dark:bg-green-900 dark:text-green-100'
                            : 'bg-surface-alt text-foreground-muted'
                        )}
                      >
                        {statusLabel}
                      </span>
                    </div>
                  )}
                </div>
              </Fragment>
            )
          })}
        </div>
      </div>
      {selectedProgressItem && (
        <div className="px-1">
          <div className="text-sm text-foreground-muted">{selectedProgressItem.description}</div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-foreground-muted">
            {selectedProgressItem.showMatchCount && (
              <span>
                <span className="text-foreground-subtle">Matches:</span>{' '}
                {selectedProgressItem.matchCount.toLocaleString()}
              </span>
            )}
            <span>
              <span className="text-foreground-subtle">{selectedProgressItem.entrantLabel}:</span>{' '}
              {formatCount(selectedProgressItem.entrantCount)}
            </span>
            <span>
              <span className="text-foreground-subtle">{selectedProgressItem.exitLabel}:</span>{' '}
              {formatCount(selectedProgressItem.exitCount)}
            </span>
            {selectedProgressItem.status === 'active' && (
              <span>
                <span className="text-foreground-subtle">Completion:</span>{' '}
                {selectedProgressItem.completionPct.toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
