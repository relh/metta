"use client";

import "highcharts/esm/highcharts-more.js";

import HighchartsReact from "highcharts-react-official";
import Highcharts from "highcharts/esm/highcharts.js";
import { FC, useMemo, useState } from "react";

import { getPolicyColor } from "./policyColor";
import { useFocusedPolicies } from "./useFocusedPolicies";

type ChartStage = {
  key: string;
  label: string;
};

type PolicyStagePoint = {
  stageKey: string;
  mean: number | null;
  stddev: number | null;
  matches: number;
};

export type PolicyStageSeries = {
  policyId: string;
  policyLabel: string;
  points: PolicyStagePoint[];
};

type PlayersStageScoreChartProps = {
  stages: ChartStage[];
  series: PolicyStageSeries[];
};

type ChartPointCustom = {
  policyId: string;
  policyLabel: string;
  stageLabel: string;
  rawMean: number | null;
  percentile: number | null;
  stddev: number | null;
  matches: number;
};

type ScoreMode = "percentile" | "raw";

const formatScore = (
  value: number | null | undefined,
  digits: number = 4,
): string => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");

export const PlayersStageScoreChart: FC<PlayersStageScoreChartProps> = ({
  stages,
  series,
}) => {
  const [scoreMode, setScoreMode] = useState<ScoreMode>("percentile");
  const [hoveredPolicyId, setHoveredPolicyId] = useState<string | null>(null);

  const stageLabelByKey = useMemo(
    () => new Map(stages.map((stage) => [stage.key, stage.label] as const)),
    [stages],
  );

  const allPolicyIds = useMemo(
    () => series.map((policy) => policy.policyId),
    [series],
  );
  const {
    focusedPolicyIds,
    focusedPolicyIdSet,
    hasFocusedPolicies,
    toggleFocusedPolicy,
  } = useFocusedPolicies({
    validPolicyIds: allPolicyIds,
    orderedPolicyIds: allPolicyIds,
  });
  const activePolicyId =
    hoveredPolicyId &&
    (!hasFocusedPolicies || focusedPolicyIdSet.has(hoveredPolicyId))
      ? hoveredPolicyId
      : (focusedPolicyIds[0] ?? null);

  const percentileByStageAndPolicy = useMemo(() => {
    const byStage = new Map<string, Map<string, number>>();
    for (const [stageIndex, stage] of stages.entries()) {
      const stageValues: Array<{ policyId: string; value: number }> = [];
      for (const policy of series) {
        const value = policy.points[stageIndex]?.mean;
        if (value === null || value === undefined || Number.isNaN(value)) {
          continue;
        }
        stageValues.push({ policyId: policy.policyId, value });
      }

      if (stageValues.length === 0) {
        byStage.set(stage.key, new Map());
        continue;
      }

      const percentiles = new Map<string, number>();
      if (stageValues.length === 1) {
        percentiles.set(stageValues[0].policyId, 100);
        byStage.set(stage.key, percentiles);
        continue;
      }

      stageValues.sort((left, right) => left.value - right.value);
      let start = 0;
      while (start < stageValues.length) {
        let end = start;
        while (
          end + 1 < stageValues.length &&
          stageValues[end + 1].value === stageValues[start].value
        ) {
          end += 1;
        }
        const rank = (start + end) / 2;
        const percentile = (rank / (stageValues.length - 1)) * 100;
        for (let index = start; index <= end; index += 1) {
          percentiles.set(stageValues[index].policyId, percentile);
        }
        start = end + 1;
      }

      byStage.set(stage.key, percentiles);
    }
    return byStage;
  }, [series, stages]);

  const yDomain = useMemo<[number, number]>(() => {
    if (scoreMode === "percentile") {
      return [0, 100];
    }

    let minValue = Number.POSITIVE_INFINITY;
    let maxValue = Number.NEGATIVE_INFINITY;

    series.forEach((policy) => {
      policy.points.forEach((point) => {
        if (
          point.mean === null ||
          point.mean === undefined ||
          Number.isNaN(point.mean)
        ) {
          return;
        }

        minValue = Math.min(minValue, point.mean);
        maxValue = Math.max(maxValue, point.mean);
      });
    });

    if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
      return [0, 1];
    }

    const range = maxValue - minValue;
    const minimumRange = 0.04;
    const effectiveRange = Math.max(range, minimumRange);
    const padding = Math.max(effectiveRange * 0.11, 0.01);
    const lower = minValue - padding;
    const upper = maxValue + padding;
    const boundedLower = minValue >= 0 && lower < 0 ? 0 : lower;
    const boundedUpper = maxValue <= 1 && upper > 1 ? 1 : upper;

    if (boundedLower === boundedUpper) {
      return [boundedLower - 0.02, boundedUpper + 0.02];
    }

    return [boundedLower, boundedUpper];
  }, [scoreMode, series]);

  const yAxisDigits =
    scoreMode === "percentile" ? 0 : yDomain[1] - yDomain[0] < 0.2 ? 3 : 2;

  const chartOptions = useMemo<Highcharts.Options>(() => {
    const chartSeries: Highcharts.SeriesOptionsType[] = [];

    series.forEach((policy, index) => {
      const isSelected = focusedPolicyIdSet.has(policy.policyId);
      const isFocused = hasFocusedPolicies && isSelected;
      const isHighlighted = hasFocusedPolicies
        ? isSelected
        : activePolicyId === policy.policyId;
      const isDimmed = hasFocusedPolicies
        ? !isSelected
        : activePolicyId !== null && !isHighlighted;
      const strokeColor = isDimmed ? "var(--fg-muted)" : getPolicyColor(index);
      const lineSeriesId = `policy-${policy.policyId}`;

      chartSeries.push({
        type: "spline",
        id: lineSeriesId,
        name: policy.policyLabel,
        data: policy.points.map((point, stageIndex) => ({
          x: stageIndex,
          y:
            scoreMode === "percentile"
              ? point.mean === null
                ? null
                : (percentileByStageAndPolicy
                    .get(point.stageKey)
                    ?.get(policy.policyId) ?? null)
              : point.mean,
          custom: {
            policyId: policy.policyId,
            policyLabel: policy.policyLabel,
            stageLabel: stageLabelByKey.get(point.stageKey) ?? point.stageKey,
            rawMean: point.mean,
            percentile:
              point.mean === null
                ? null
                : (percentileByStageAndPolicy
                    .get(point.stageKey)
                    ?.get(policy.policyId) ?? null),
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
        findNearestPointBy: "xy",
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
              setHoveredPolicyId(policy.policyId);
            }
          },
          mouseOut: () =>
            setHoveredPolicyId((current) =>
              current === policy.policyId ? null : current,
            ),
        },
      } satisfies Highcharts.SeriesSplineOptions);

      const errorBarData: Array<
        [number | string, number, number] | Highcharts.PointOptionsObject
      > = [];
      policy.points.forEach((point, stageIndex) => {
        if (
          point.mean === null ||
          point.stddev === null ||
          point.stddev === undefined ||
          Number.isNaN(point.mean) ||
          Number.isNaN(point.stddev)
        ) {
          return;
        }

        errorBarData.push([
          stageIndex,
          point.mean - point.stddev,
          point.mean + point.stddev,
        ]);
      });

      if (scoreMode === "raw" && errorBarData.length > 0) {
        chartSeries.push({
          type: "errorbar",
          linkedTo: lineSeriesId,
          name: `${policy.policyLabel} stddev`,
          data: errorBarData,
          color: strokeColor,
          lineWidth: 1.2,
          whiskerLength: "30%",
          animation: false,
          showInLegend: false,
          enableMouseTracking: false,
          stickyTracking: false,
          opacity: isDimmed ? 0.08 : isHighlighted ? 0.85 : 0.24,
          zIndex: 0,
        } satisfies Highcharts.SeriesErrorbarOptions);
      }
    });

    return {
      chart: {
        type: "spline",
        backgroundColor: "transparent",
        animation: false,
        spacingTop: 14,
        spacingRight: 20,
        spacingBottom: 10,
        spacingLeft: 16,
        marginLeft: 72,
        marginBottom: 52,
      },
      title: { text: undefined },
      credits: { enabled: false },
      legend: { enabled: false },
      xAxis: {
        categories: stages.map((stage) => stage.label),
        lineColor: "var(--border-subtle)",
        tickColor: "var(--border-subtle)",
        labels: {
          y: 18,
          style: {
            color: "var(--fg-muted)",
            fontSize: "12px",
          },
        },
      },
      yAxis: {
        title: {
          text: scoreMode === "percentile" ? "Percentile" : "Raw score",
          margin: 18,
          style: {
            color: "var(--fg-muted)",
            fontSize: "12px",
            fontWeight: "500",
          },
        },
        min: yDomain[0],
        max: yDomain[1],
        gridLineColor: "var(--border-subtle)",
        labels: {
          style: {
            color: "var(--fg-muted)",
            fontSize: "12px",
          },
          formatter() {
            return formatScore(Number(this.value), yAxisDigits);
          },
        },
      },
      tooltip: {
        shared: false,
        useHTML: true,
        shadow: false,
        borderWidth: 0,
        padding: 0,
        backgroundColor: "transparent",
        hideDelay: 0,
        formatter() {
          const custom = this.options.custom as ChartPointCustom | undefined;
          if (!custom) {
            return false;
          }
          if (hasFocusedPolicies && !focusedPolicyIdSet.has(custom.policyId)) {
            return false;
          }

          return `<div style="border:1px solid var(--border);background:var(--surface);border-radius:6px;padding:8px 12px;box-shadow:0 4px 12px rgba(0,0,0,0.16);">
            <div style="font-size:12px;color:var(--fg-muted);">${escapeHtml(custom.stageLabel)}</div>
            <div style="margin-top:4px;font-size:14px;font-weight:600;color:var(--fg);">${escapeHtml(custom.policyLabel)}</div>
            <div style="margin-top:4px;font-size:12px;color:var(--fg-muted);line-height:1.35;">
              <div>Percentile: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${formatScore(custom.percentile, 1)}</span></div>
              <div>Raw mean: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${formatScore(custom.rawMean)}</span></div>
              <div>Stddev: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${custom.stddev === null ? "n/a" : formatScore(custom.stddev)}</span></div>
              <div>Matches: <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation Mono','Courier New',monospace;color:var(--fg);">${custom.matches}</span></div>
            </div>
          </div>`;
        },
      },
      plotOptions: {
        series: {
          animation: false,
          stickyTracking: false,
          findNearestPointBy: "xy",
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
    };
  }, [
    activePolicyId,
    focusedPolicyIdSet,
    hasFocusedPolicies,
    percentileByStageAndPolicy,
    scoreMode,
    series,
    stageLabelByKey,
    stages,
    toggleFocusedPolicy,
    yAxisDigits,
    yDomain,
  ]);

  if (series.length === 0 || stages.length === 0) {
    return null;
  }

  return (
    <div className="border-border-subtle bg-surface-alt rounded-lg border">
      <div className="border-border-subtle flex items-center justify-end gap-2 border-b px-3 py-2">
        <button
          type="button"
          onClick={() => setScoreMode("percentile")}
          aria-pressed={scoreMode === "percentile"}
          className={`rounded px-2 py-1 text-xs ${
            scoreMode === "percentile"
              ? "bg-indigo-600 text-white"
              : "bg-surface text-foreground-muted hover:text-foreground"
          }`}
        >
          Percentile
        </button>
        <button
          type="button"
          onClick={() => setScoreMode("raw")}
          aria-pressed={scoreMode === "raw"}
          className={`rounded px-2 py-1 text-xs ${
            scoreMode === "raw"
              ? "bg-indigo-600 text-white"
              : "bg-surface text-foreground-muted hover:text-foreground"
          }`}
        >
          Raw score
        </button>
      </div>
      <div
        className="h-[420px] w-full"
        onMouseLeave={() => setHoveredPolicyId(null)}
      >
        <HighchartsReact
          highcharts={Highcharts}
          options={chartOptions}
          immutable
          containerProps={{ style: { height: "100%", width: "100%" } }}
        />
      </div>
    </div>
  );
};
