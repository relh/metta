from __future__ import annotations

from devops.stable.stable_check_metrics import (
    STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC,
    STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC,
    STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC,
    STABLE_CHECK_COMPLETED_AT_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_METRIC,
    STABLE_CHECK_RAW_STATUS_METRIC,
)

METRIC = "metta.skills.usage"
TIMEFRAME = "2d"
STABLE_TIMEFRAME = "1w"


def _toplist_widget(title: str, *, group_by: str, x: int = 0, y: int = 0, width: int = 6, height: int = 4) -> dict:
    return {
        "definition": {
            "type": "toplist",
            "title": title,
            "requests": [{"q": f"top(sum:{METRIC}{{*}} by {{{group_by}}}.as_count(), 25, 'sum', 'desc')"}],
            "time": {"live_span": TIMEFRAME},
        },
        "layout": {"x": x, "y": y, "width": width, "height": height},
    }


def _timeseries_widget(title: str, *, group_by: str, x: int = 0, y: int = 0, width: int = 12, height: int = 4) -> dict:
    return {
        "definition": {
            "type": "timeseries",
            "title": title,
            "requests": [
                {
                    "q": f"sum:{METRIC}{{*}} by {{{group_by}}}.as_count()",
                    "display_type": "bars",
                }
            ],
            "time": {"live_span": TIMEFRAME},
        },
        "layout": {"x": x, "y": y, "width": width, "height": height},
    }


def _section_header(title: str, *, x: int, y: int, width: int = 12, height: int = 2) -> dict:
    return {
        "definition": {
            "type": "note",
            "content": title,
            "font_size": "24",
            "text_align": "center",
            "vertical_align": "center",
            "show_tick": False,
            "has_padding": True,
        },
        "layout": {"x": x, "y": y, "width": width, "height": height},
    }


def _offset_widgets(widgets: list[dict], *, y_offset: int) -> list[dict]:
    return [
        {
            **widget,
            "layout": {
                **widget["layout"],
                "y": widget["layout"]["y"] + y_offset,
            },
        }
        for widget in widgets
    ]


def skills_leaderboard_dashboard() -> dict:
    return {
        "title": "Claude Code Skills Leaderboard",
        "description": "Claude Code skill usage across the team",
        "layout_type": "ordered",
        "tags": ["team:dev"],
        "widgets": [
            {
                "definition": {
                    "type": "query_value",
                    "title": "Total Invocations",
                    "requests": [{"q": f"sum:{METRIC}{{*}}.as_count()", "aggregator": "sum"}],
                    "time": {"live_span": TIMEFRAME},
                    "precision": 0,
                },
                "layout": {"x": 0, "y": 0, "width": 2, "height": 3},
            },
            _toplist_widget(
                "Usage by Category",
                group_by="skill_prefix",
                x=2,
                y=0,
                width=4,
                height=3,
            ),
            _toplist_widget(
                "Top Skills",
                group_by="skill",
                x=6,
                y=0,
                width=4,
                height=3,
            ),
            _toplist_widget(
                "Top Users",
                group_by="user",
                x=10,
                y=0,
                width=2,
                height=3,
            ),
            _timeseries_widget(
                "Usage Timeline by User",
                group_by="user",
                x=0,
                y=3,
                width=12,
                height=4,
            ),
            _timeseries_widget(
                "Usage Timeline by Skill",
                group_by="skill",
                x=0,
                y=7,
                width=12,
                height=4,
            ),
        ],
    }


def stable_runner_health_dashboard() -> dict:
    stable_widgets = [
        {
            "definition": {
                "type": "query_table",
                "title": "Latest Summary Status by Job (-1=red,0=yellow,1=green)",
                "requests": [
                    {
                        "response_format": "scalar",
                        "queries": [
                            {
                                "name": "latest_status",
                                "data_source": "metrics",
                                "query": (f"max:{STABLE_CHECK_EFFECTIVE_STATUS_METRIC}{{*}} by {{job}}"),
                            },
                            {
                                "name": "latest_status_at",
                                "data_source": "metrics",
                                "query": (f"max:{STABLE_CHECK_COMPLETED_AT_METRIC}{{*}} by {{job}}"),
                            },
                        ],
                        "formulas": [
                            {
                                "formula": "latest_status",
                                "alias": "LATEST STATUS",
                                "conditional_formats": [
                                    {"comparator": "<", "value": 0, "palette": "white_on_red"},
                                    {"comparator": "=", "value": 0, "palette": "white_on_yellow"},
                                    {"comparator": ">", "value": 0, "palette": "white_on_green"},
                                ],
                            },
                            {
                                "formula": "latest_status_at",
                                "alias": "LAST STATUS AT (UTC EPOCH)",
                            },
                        ],
                    }
                ],
                "has_search_bar": "auto",
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": 2, "width": 12, "height": 5},
        },
        {
            "definition": {
                "type": "query_table",
                "title": "Stable Runner - Key Metrics",
                "requests": [
                    {
                        "response_format": "scalar",
                        "queries": [
                            {
                                "name": "value",
                                "data_source": "metrics",
                                "query": f"avg:{STABLE_CHECK_ACCEPTANCE_CRITERION_VALUE_METRIC}{{*}} by "
                                "{job,criterion}",
                            },
                            {
                                "name": "target",
                                "data_source": "metrics",
                                "query": f"avg:{STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC}{{*}} by "
                                "{job,criterion}",
                            },
                            {
                                "name": "pass_fail",
                                "data_source": "metrics",
                                "query": f"max:{STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC}{{*}} by "
                                "{job,criterion}",
                            },
                        ],
                        "formulas": [
                            {"formula": "value", "alias": "VALUE"},
                            {"formula": "target", "alias": "TARGET (FROM CODE)"},
                            {
                                "formula": "pass_fail",
                                "alias": "PASS/FAIL",
                                "conditional_formats": [
                                    {"comparator": "<", "value": 1, "palette": "white_on_red"},
                                    {"comparator": ">=", "value": 1, "palette": "white_on_green"},
                                ],
                            },
                        ],
                    }
                ],
                "has_search_bar": "auto",
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": 7, "width": 12, "height": 6},
        },
        {
            "definition": {
                "type": "timeseries",
                "title": "Runs Success by Job",
                "requests": [
                    {
                        "q": (
                            f"avg:{STABLE_CHECK_ACCEPTANCE_CRITERION_STATUS_METRIC}"
                            "{criterion:runs_success} by {job}"
                        ),
                        "display_type": "line",
                    }
                ],
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": 13, "width": 12, "height": 4},
        },
        {
            "definition": {
                "type": "timeseries",
                "title": "Run Activity by Job",
                "requests": [
                    {
                        "q": (
                            f"sum:{STABLE_CHECK_ACCEPTANCE_CRITERION_TARGET_METRIC}"
                            "{criterion:runs_success} by {job}"
                        ),
                        "display_type": "bars",
                    }
                ],
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": 17, "width": 12, "height": 4},
        },
        {
            "definition": {
                "type": "toplist",
                "title": "Latest Completion Timestamp (UTC Epoch) by Job",
                "requests": [
                    {"q": (f"top(max:{STABLE_CHECK_COMPLETED_AT_METRIC}{{*}} by {{job}}, 50, 'last', 'desc')")}
                ],
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": 21, "width": 6, "height": 4},
        },
        {
            "definition": {
                "type": "toplist",
                "title": "Latest Raw Status by Job (1=ok,0=skipped,-1=fail)",
                "requests": [{"q": (f"top(max:{STABLE_CHECK_RAW_STATUS_METRIC}{{*}} by {{job}}, 50, 'last', 'desc')")}],
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 6, "y": 21, "width": 6, "height": 4},
        },
        {
            "definition": {
                "type": "manage_status",
                "title": "Stable Monitor Alerts",
                "query": "tag:service:stable-runner tag:managed-by:code",
                "summary_type": "monitors",
                "display_format": "countsAndList",
                "sort": "status,desc",
                "count": 50,
                "show_priority": True,
                "show_last_triggered": True,
                "color_preference": "background",
            },
            "layout": {"x": 0, "y": 25, "width": 12, "height": 5},
        },
    ]

    stable_monitor_alerts_widget = stable_widgets.pop()
    stable_monitor_alerts_widget = {
        **stable_monitor_alerts_widget,
        "layout": {**stable_monitor_alerts_widget["layout"], "y": 2},
    }

    non_stable_monitor_alerts_widget = {
        "definition": {
            "type": "manage_status",
            "title": "Non-Stable Monitor Alerts",
            "query": "tag:managed-by:code -tag:service:stable-runner",
            "summary_type": "monitors",
            "display_format": "countsAndList",
            "sort": "status,desc",
            "count": 50,
            "hide_zero_counts": False,
            "show_priority": True,
            "show_last_triggered": True,
            "color_preference": "background",
        },
        "layout": {"x": 0, "y": 8, "width": 12, "height": 6},
    }
    stable_section_header_y = (
        non_stable_monitor_alerts_widget["layout"]["y"] + non_stable_monitor_alerts_widget["layout"]["height"] + 1
    )
    stable_widgets = _offset_widgets(stable_widgets, y_offset=stable_section_header_y)
    runtime_section_header_y = max(widget["layout"]["y"] + widget["layout"]["height"] for widget in stable_widgets) + 1
    runtime_metrics_start_y = runtime_section_header_y + 2

    runtime_widgets = [
        {
            "definition": {
                "title": "Concurrent Running Jobs",
                "type": "timeseries",
                "requests": [
                    {
                        "queries": [
                            {
                                "data_source": "metrics",
                                "name": "running",
                                "query": (
                                    "avg:job.running_count{service:observatory-backend,env:production,job_type:episode}"
                                ),
                            }
                        ],
                        "formulas": [{"formula": "running", "alias": "running"}],
                        "response_format": "timeseries",
                        "display_type": "line",
                    }
                ],
                "yaxis": {"include_zero": True},
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": runtime_metrics_start_y, "width": 12, "height": 4},
        },
        {
            "definition": {
                "title": "Job Status Transitions (count)",
                "type": "timeseries",
                "requests": [
                    {
                        "queries": [
                            {
                                "data_source": "metrics",
                                "name": "completed",
                                "query": (
                                    "sum:job.state_transition{to_status:completed,service:observatory-backend,"
                                    "env:production,job_type:episode}.as_count().rollup(sum, 60)"
                                ),
                            },
                            {
                                "data_source": "metrics",
                                "name": "running",
                                "query": (
                                    "sum:job.state_transition{to_status:running,service:observatory-backend,"
                                    "env:production,job_type:episode}.as_count().rollup(sum, 60)"
                                ),
                            },
                            {
                                "data_source": "metrics",
                                "name": "dispatched",
                                "query": (
                                    "sum:job.state_transition{to_status:dispatched,service:observatory-backend,"
                                    "env:production,job_type:episode}.as_count().rollup(sum, 60)"
                                ),
                            },
                            {
                                "data_source": "metrics",
                                "name": "failed",
                                "query": (
                                    "sum:job.state_transition{to_status:failed,service:observatory-backend,"
                                    "env:production,job_type:episode}.as_count().rollup(sum, 60)"
                                ),
                            },
                        ],
                        "formulas": [
                            {"formula": "completed", "alias": "completed"},
                            {"formula": "running", "alias": "running"},
                            {"formula": "dispatched", "alias": "dispatched"},
                            {"formula": "failed", "alias": "failed"},
                        ],
                        "response_format": "timeseries",
                        "display_type": "bars",
                    }
                ],
                "yaxis": {"include_zero": True},
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": runtime_metrics_start_y + 4, "width": 12, "height": 4},
        },
        {
            "definition": {
                "title": "Stage Durations (p50 / p90)",
                "type": "query_table",
                "requests": [
                    {
                        "queries": [
                            {
                                "data_source": "metrics",
                                "name": "p50_stage",
                                "query": (
                                    "p50:job.stage_duration{service:observatory-backend,env:production,"
                                    "job_type:episode} by {stage}"
                                ),
                            },
                            {
                                "data_source": "metrics",
                                "name": "p90_stage",
                                "query": (
                                    "p90:job.stage_duration{service:observatory-backend,env:production,"
                                    "job_type:episode} by {stage}"
                                ),
                            },
                        ],
                        "response_format": "scalar",
                        "sort": {
                            "count": 500,
                            "order_by": [{"type": "formula", "index": 1, "order": "desc"}],
                        },
                        "formulas": [
                            {
                                "formula": "p50_stage",
                                "alias": "p50",
                                "cell_display_mode": "bar",
                                "number_format": {
                                    "unit": {
                                        "type": "canonical_unit",
                                        "unit_name": "second",
                                    }
                                },
                            },
                            {
                                "formula": "p90_stage",
                                "alias": "p90",
                                "cell_display_mode": "bar",
                                "number_format": {
                                    "unit": {
                                        "type": "canonical_unit",
                                        "unit_name": "second",
                                    }
                                },
                            },
                        ],
                    }
                ],
                "has_search_bar": "auto",
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": runtime_metrics_start_y + 8, "width": 12, "height": 6},
        },
        {
            "definition": {
                "title": "Failure Breakdown",
                "type": "timeseries",
                "requests": [
                    {
                        "queries": [
                            {
                                "data_source": "metrics",
                                "name": "failures",
                                "query": (
                                    "sum:job.state_transition{to_status:failed,"
                                    "service:observatory-backend,env:production,job_type:episode} "
                                    "by {error_type}.as_count().rollup(sum, 60)"
                                ),
                            }
                        ],
                        "formulas": [{"formula": "failures"}],
                        "response_format": "timeseries",
                        "style": {
                            "palette": "warm",
                            "line_type": "solid",
                            "line_width": "normal",
                        },
                        "display_type": "bars",
                    }
                ],
                "yaxis": {"include_zero": True},
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 0, "y": runtime_metrics_start_y + 14, "width": 12, "height": 4},
        },
        {
            "definition": {
                "type": "query_value",
                "title": "Episode Length (10m avg)",
                "requests": [
                    {
                        "q": "avg:episode.length{service:observatory-backend,env:production,job_type:episode}",
                        "aggregator": "avg",
                    }
                ],
                "time": {"live_span": STABLE_TIMEFRAME},
                "precision": 0,
            },
            "layout": {"x": 0, "y": runtime_metrics_start_y + 18, "width": 4, "height": 3},
        },
        {
            "definition": {
                "title": "Episode Length Trend (episode jobs)",
                "type": "timeseries",
                "requests": [
                    {
                        "q": "avg:episode.length{service:observatory-backend,env:production,job_type:episode}",
                        "display_type": "line",
                    }
                ],
                "time": {"live_span": STABLE_TIMEFRAME},
            },
            "layout": {"x": 4, "y": runtime_metrics_start_y + 18, "width": 8, "height": 3},
        },
    ]

    return {
        "title": "Stable Runner V2",
        "description": (
            "Status and freshness for stable checks. "
            "check.effective_status values: -1=red(failed), 0=yellow(quarantined/not_implemented), 1=green(passed). "
            "check.completed_at is unix epoch seconds (UTC)."
        ),
        "layout_type": "ordered",
        "tags": ["team:infra"],
        "widgets": [
            _section_header("Managed Monitors", x=0, y=0),
            stable_monitor_alerts_widget,
            non_stable_monitor_alerts_widget,
            _section_header("Stable Runner Checks", x=0, y=stable_section_header_y),
            *stable_widgets,
            _section_header("Episode + Job Runtime Health", x=0, y=runtime_section_header_y),
            *runtime_widgets,
        ],
    }


_PROD_FILTER = "service:observatory-backend,env:production,job_type:episode"
_LIVE_SPAN = "4h"


def _flow_qv_sum(title: str, queries: list[str], formula: str, *, precision: int = 0, unit: str = "") -> dict:
    named_queries = [{"data_source": "metrics", "name": f"q{i}", "query": q} for i, q in enumerate(queries)]
    fmt: dict = {"formula": formula}
    if unit:
        fmt["number_format"] = {"unit": {"type": "canonical_unit", "unit_name": unit}}
    return {
        "definition": {
            "type": "query_value",
            "title": title,
            "title_size": "13",
            "requests": [
                {
                    "queries": named_queries,
                    "formulas": [fmt],
                    "response_format": "scalar",
                }
            ],
            "timeseries_background": {"type": "area"},
            "time": {"live_span": _LIVE_SPAN},
            "precision": precision,
            "autoscale": True,
        },
    }


def _flow_qv(title: str, query: str, *, precision: int = 0, unit: str = "") -> dict:
    return _flow_qv_sum(title, [query], "q0", precision=precision, unit=unit)


def _flow_group(title: str, widgets: list[dict], *, x: int, y: int, width: int, height: int) -> dict:
    return {
        "definition": {
            "type": "group",
            "title": title,
            "layout_type": "ordered",
            "widgets": widgets,
        },
        "layout": {"x": x, "y": y, "width": width, "height": height},
    }


def pipeline_dashboard() -> dict:
    y = 0
    _TREND_SPAN = "1mo"

    # ── Pipeline Flow (live) ──
    def _at(widget: dict, *, x: int, y: int, w: int, h: int) -> dict:
        return {**widget, "layout": {"x": x, "y": y, "width": w, "height": h}}

    _arrow: dict = {
        "definition": {
            "type": "note",
            "content": "\u2794",
            "font_size": "36",
            "text_align": "center",
            "vertical_align": "center",
            "background_color": "transparent",
            "show_tick": False,
            "has_padding": False,
        },
    }

    flow_widgets = [
        _at(
            _flow_qv_sum(
                "Queued Jobs",
                [
                    f"avg:job.outstanding_count{{{_PROD_FILTER},status:pending}}",
                    f"avg:job.outstanding_count{{{_PROD_FILTER},status:dispatched}}",
                ],
                "q0 + q1",
            ),
            x=0,
            y=0,
            w=3,
            h=2,
        ),
        _at(
            _flow_qv_sum(
                "Avg Wait",
                [
                    f"avg:job.stage_duration{{{_PROD_FILTER},stage:pending}}",
                    f"avg:job.stage_duration{{{_PROD_FILTER},stage:dispatched}}",
                ],
                "q0 + q1",
                unit="second",
                precision=1,
            ),
            x=0,
            y=2,
            w=3,
            h=2,
        ),
        _at(_arrow, x=3, y=0, w=1, h=4),
        _at(
            _flow_qv(
                "Running Jobs",
                f"avg:job.outstanding_count{{{_PROD_FILTER},status:running}}",
            ),
            x=4,
            y=0,
            w=3,
            h=2,
        ),
        _at(
            _flow_qv(
                "Avg Duration",
                f"avg:job.stage_duration{{{_PROD_FILTER},stage:running}}",
                unit="second",
                precision=1,
            ),
            x=4,
            y=2,
            w=3,
            h=2,
        ),
        _at(_arrow, x=7, y=0, w=1, h=4),
        _at(
            _flow_qv(
                "Completed /hr",
                f"sum:job.state_transition{{{_PROD_FILTER},to_status:completed}}.as_count().rollup(sum, 3600)",
            ),
            x=8,
            y=0,
            w=2,
            h=2,
        ),
        _at(
            _flow_qv(
                "Failed /hr",
                f"sum:job.state_transition{{{_PROD_FILTER},to_status:failed}}.as_count().rollup(sum, 3600)",
            ),
            x=10,
            y=0,
            w=2,
            h=2,
        ),
    ]
    flow_group = _flow_group(
        "Current Pipeline",
        flow_widgets,
        x=0,
        y=y,
        width=12,
        height=6,
    )
    y += 6

    # ── Per-job averages (top row: 5 small charts) ──
    _dur_fmt = {"number_format": {"unit": {"type": "canonical_unit", "unit_name": "second"}}}

    def _trend_ts(title: str, queries: list[dict], formulas: list[dict], **kwargs) -> dict:
        defn: dict = {
            "title": title,
            "type": "timeseries",
            "requests": [
                {
                    "queries": queries,
                    "formulas": formulas,
                    "response_format": "timeseries",
                    "display_type": kwargs.get("display_type", "line"),
                }
            ],
            "yaxis": {"include_zero": True},
            "time": {"live_span": _TREND_SPAN},
        }
        if "style" in kwargs:
            defn["requests"][0]["style"] = kwargs["style"]
        return {"definition": defn}

    # Row 0: [Queued 0-3][Running 4-7][Time/Step 8-11]
    # Row 1: [Throughput 0-11]
    history_widgets = [
        _at(
            _trend_ts(
                "Avg Queued Time",
                [
                    {
                        "data_source": "metrics",
                        "name": "pend",
                        "query": f"avg:job.stage_duration{{{_PROD_FILTER},stage:pending}}",
                    },
                    {
                        "data_source": "metrics",
                        "name": "disp",
                        "query": f"avg:job.stage_duration{{{_PROD_FILTER},stage:dispatched}}",
                    },
                ],
                [{"formula": "pend + disp", "alias": "queued", **_dur_fmt}],
            ),
            x=0,
            y=0,
            w=4,
            h=4,
        ),
        _at(
            _trend_ts(
                "Avg Running Time",
                [
                    {
                        "data_source": "metrics",
                        "name": "run",
                        "query": f"avg:job.stage_duration{{{_PROD_FILTER},stage:running}}",
                    },
                ],
                [{"formula": "run", "alias": "running", **_dur_fmt}],
            ),
            x=4,
            y=0,
            w=4,
            h=4,
        ),
        _at(
            _trend_ts(
                "Avg Running Time per Step",
                [
                    {
                        "data_source": "metrics",
                        "name": "dur",
                        "query": f"avg:job.stage_duration{{{_PROD_FILTER},stage:running}}",
                    },
                    {"data_source": "metrics", "name": "steps", "query": f"avg:episode.length{{{_PROD_FILTER}}}"},
                ],
                [{"formula": "dur / steps", "alias": "per step", **_dur_fmt}],
            ),
            x=8,
            y=0,
            w=4,
            h=4,
        ),
        _at(
            _trend_ts(
                "Job Throughput (per day)",
                [
                    {
                        "data_source": "metrics",
                        "name": "ok",
                        "query": (
                            f"sum:job.state_transition{{{_PROD_FILTER},to_status:completed}}"
                            ".as_count().rollup(sum, 86400)"
                        ),
                    },
                    {
                        "data_source": "metrics",
                        "name": "fail",
                        "query": (
                            f"sum:job.state_transition{{{_PROD_FILTER},to_status:failed}}.as_count().rollup(sum, 86400)"
                        ),
                    },
                ],
                [
                    {"formula": "ok", "alias": "completed"},
                    {"formula": "fail", "alias": "failed", "style": {"palette": "warm"}},
                ],
                display_type="bars",
                style={"palette": "dog_classic"},
            ),
            x=0,
            y=4,
            w=12,
            h=4,
        ),
    ]
    averages_group = _flow_group(
        "History",
        history_widgets,
        x=0,
        y=y,
        width=12,
        height=9,
    )
    y += 9

    return {
        "title": "Tournament Pipeline",
        "description": (
            "Live pipeline flow, per-job duration/cost averages, and aggregate throughput and cost trends."
        ),
        "layout_type": "ordered",
        "tags": ["team:infra"],
        "widgets": [
            flow_group,
            averages_group,
        ],
    }


ALL_DASHBOARDS = [
    skills_leaderboard_dashboard,
    stable_runner_health_dashboard,
    pipeline_dashboard,
]


def get_all_dashboard_configs() -> list[dict]:
    return [d() for d in ALL_DASHBOARDS]
