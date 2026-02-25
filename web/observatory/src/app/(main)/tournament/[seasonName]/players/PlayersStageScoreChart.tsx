'use client'

import Highcharts from 'highcharts/esm/highcharts.js'
import 'highcharts/esm/highcharts-more.js'
import HighchartsReact from 'highcharts-react-official'
import { FC, useMemo, useState } from 'react'

import { getPolicyColor } from './policyColor'
import { useFocusedPolicies } from './useFocusedPolicies'

type ChartStage = {
  key: string
  label: string
}

type PolicyStagePoint = {
  stageKey: string
  mean: number | null
  stddev: number | null
  matches: number
}

export type PolicyStageSeries = {
  policyId: string
  policyLabel: string
  points: PolicyStagePoint[]
}

type PlayersStageScoreChartProps = {
  stages: ChartStage[]
  series: PolicyStageSeries[]
}

type ChartPointCustom = {
  policyId: string
  policyLabel: string
  stageLabel: string
  stddev: number | null
  matches: number
}

const formatScore = (value: number | null | undefined, digits: number = 4): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '-'
  }
  return value.toFixed(digits)
}

const escapeHtml = (value: string): string =>
  value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;')

export const PlayersStageScoreChart: FC<PlayersStageScoreChartProps> = ({ stages, series }) => {
  const [hoveredPolicyId, setHoveredPolicyId] = useState<string | null>(null)

  const stageLabelByKey = useMemo(() => new Map(stages.map((stage) => [stage.key, stage.label] as const)), [stages])

  const allPolicyIds = useMemo(() => series.map((policy) => policy.policyId), [series])
  const { focusedPolicyIds, focusedPolicyIdSet, hasFocusedPolicies, toggleFocusedPolicy } = useFocusedPolicies({
    validPolicyIds: allPolicyIds,
    orderedPolicyIds: allPolicyIds,
  })
  const activePolicyId =
    hoveredPolicyId && (!hasFocusedPolicies || focusedPolicyIdSet.has(hoveredPolicyId))
      ? hoveredPolicyId
      : (focusedPolicyIds[0] ?? null)

  const yDomain = useMemo<[number, number]>(() => {
    let minValue = Number.POSITIVE_INFINITY
    let maxValue = Number.NEGATIVE_INFINITY

    series.forEach((policy) => {
      policy.points.forEach((point) => {
        if (point.mean === null || point.mean === undefined || Number.isNaN(point.mean)) {
          return
        }

        minValue = Math.min(minValue, point.mean)
        maxValue = Math.max(maxValue, point.mean)
      })
    })

    if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
      return [0, 1]
    }

    const range = maxValue - minValue
    const minimumRange = 0.04
    const effectiveRange = Math.max(range, minimumRange)
    const padding = Math.max(effectiveRange * 0.11, 0.01)
    const lower = minValue - padding
    const upper = maxValue + padding
    const boundedLower = minValue >= 0 && lower < 0 ? 0 : lower
    const boundedUpper = maxValue <= 1 && upper > 1 ? 1 : upper

    if (boundedLower === boundedUpper) {
      return [boundedLower - 0.02, boundedUpper + 0.02]
    }

    return [boundedLower, boundedUpper]
  }, [series])

  const yAxisDigits = yDomain[1] - yDomain[0] < 0.2 ? 3 : 2

  const chartOptions = useMemo<Highcharts.Options>(() => {
    const chartSeries: Highcharts.SeriesOptionsType[] = []

    series.forEach((policy, index) => {
      const isSelected = focusedPolicyIdSet.has(policy.policyId)
      const isFocused = hasFocusedPolicies && isSelected
      const isHighlighted = hasFocusedPolicies ? isSelected : activePolicyId === policy.policyId
      const isDimmed = hasFocusedPolicies ? !isSelected : activePolicyId !== null && !isHighlighted
      const strokeColor = isDimmed ? 'var(--fg-muted)' : getPolicyColor(index)
      const lineSeriesId = `policy-${policy.policyId}`

      chartSeries.push({
        type: 'spline',
        id: lineSeriesId,
        name: policy.policyLabel,
        data: policy.points.map((point, stageIndex) => ({
          x: stageIndex,
          y: point.mean,
          custom: {
            policyId: policy.policyId,
            policyLabel: policy.policyLabel,
            stageLabel: stageLabelByKey.get(point.stageKey) ?? point.stageKey,
            stddev: point.stddev,
            matches: point.matches,
          } satisfies ChartPointCustom,
        })),
        color: strokeColor,
        lineWidth: isFocused ? 4 : isHighlighted ? 3 : 1.5,
        opacity: isDimmed ? 0.18 : isHighlighted ? 1 : 0.72,
        connectNulls: false,
        showInLegend: false,
        animation: false,
        turboThreshold: 0,
        stickyTracking: false,
        findNearestPointBy: 'xy',
        marker: {
          enabled: false,
          states: {
            hover: {
              enabled: isHighlighted,
              radius: 4,
            },
          },
        },
        states: {
          hover: {
            lineWidthPlus: 0,
          },
        },
        events: {
          click: () => toggleFocusedPolicy(policy.policyId),
          mouseOver: () => {
            if (!hasFocusedPolicies || isSelected) {
              setHoveredPolicyId(policy.policyId)
            }
          },
          mouseOut: () => setHoveredPolicyId((current) => (current === policy.policyId ? null : current)),
        },
      } satisfies Highcharts.SeriesSplineOptions)

      const errorBarData: Array<[number | string, number, number] | Highcharts.PointOptionsObject> = []
      policy.points.forEach((point, stageIndex) => {
        if (
          point.mean === null ||
          point.stddev === null ||
          point.stddev === undefined ||
          Number.isNaN(point.mean) ||
          Number.isNaN(point.stddev)
        ) {
          return
        }

        errorBarData.push([stageIndex, point.mean - point.stddev, point.mean + point.stddev])
      })

      if (errorBarData.length > 0) {
        chartSeries.push({
          type: 'errorbar',
          linkedTo: lineSeriesId,
          name: `${policy.policyLabel} stddev`,
          data: errorBarData,
          color: strokeColor,
          lineWidth: 1.2,
          whiskerLength: '30%',
          animation: false,
          showInLegend: false,
          enableMouseTracking: false,
          stickyTracking: false,
          opacity: isDimmed ? 0.08 : isHighlighted ? 0.85 : 0.24,
          zIndex: 0,
        } satisfies Highcharts.SeriesErrorbarOptions)
      }
    })

    return {
      chart: {
        type: 'spline',
        backgroundColor: 'transparent',
        animation: false,
        spacingTop: 14,
        spacingRight: 20,
        spacingBottom: 8,
        spacingLeft: 16,
        marginLeft: 72,
      },
      title: { text: undefined },
      credits: { enabled: false },
      legend: { enabled: false },
      xAxis: {
        categories: stages.map((stage) => stage.label),
        lineColor: 'var(--border-subtle)',
        tickColor: 'var(--border-subtle)',
        labels: {
          y: 4,
          style: {
            color: 'var(--fg-muted)',
            fontSize: '12px',
          },
        },
      },
      yAxis: {
        title: {
          text: 'Score',
          margin: 18,
          style: {
            color: 'var(--fg-muted)',
            fontSize: '12px',
            fontWeight: '500',
          },
        },
        min: yDomain[0],
        max: yDomain[1],
        gridLineColor: 'var(--border-subtle)',
        labels: {
          style: {
            color: 'var(--fg-muted)',
            fontSize: '12px',
          },
          formatter() {
            return Number(this.value).toFixed(yAxisDigits)
          },
        },
      },
      tooltip: {
        shared: false,
        useHTML: true,
        shadow: false,
        borderWidth: 0,
        padding: 0,
        backgroundColor: 'transparent',
        hideDelay: 0,
        formatter() {
          const custom = this.options.custom as ChartPointCustom | undefined
          if (!custom) {
            return false
          }
          if (hasFocusedPolicies && !focusedPolicyIdSet.has(custom.policyId)) {
            return false
          }

          return `<div style="border:1px solid var(--border);background:var(--surface);border-radius:6px;padding:8px 12px;box-shadow:0 4px 12px rgba(0,0,0,0.16);">
            <div style="font-size:12px;color:var(--fg-muted);">${escapeHtml(custom.stageLabel)}</div>
            <div style="margin-top:4px;font-size:14px;font-weight:600;color:var(--fg);">${escapeHtml(custom.policyLabel)}</div>
            <div style="margin-top:4px;font-size:12px;color:var(--fg-muted);line-height:1.35;">
              <div>Mean: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${formatScore(this.y as number | null | undefined)}</span></div>
              <div>Stddev: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${custom.stddev === null ? 'n/a' : formatScore(custom.stddev)}</span></div>
              <div>Matches: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${custom.matches}</span></div>
            </div>
          </div>`
        },
      },
      plotOptions: {
        series: {
          animation: false,
          stickyTracking: false,
          findNearestPointBy: 'xy',
          states: {
            inactive: {
              opacity: 0.2,
            },
          },
        },
        errorbar: {
          enableMouseTracking: false,
          stickyTracking: false,
        },
      },
      series: chartSeries,
    }
  }, [
    activePolicyId,
    focusedPolicyIdSet,
    hasFocusedPolicies,
    series,
    stageLabelByKey,
    stages,
    toggleFocusedPolicy,
    yAxisDigits,
    yDomain,
  ])

  if (series.length === 0 || stages.length === 0) {
    return null
  }

  return (
    <div className="rounded-lg border border-border-subtle bg-surface-alt">
      <div className="h-[400px] w-full" onMouseLeave={() => setHoveredPolicyId(null)}>
        <HighchartsReact
          highcharts={Highcharts}
          options={chartOptions}
          immutable
          containerProps={{ style: { height: '100%', width: '100%' } }}
        />
      </div>
    </div>
  )
}
