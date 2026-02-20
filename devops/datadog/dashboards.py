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
                "layout": {"x": 0, "y": 0, "width": 12, "height": 5},
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
                "layout": {"x": 0, "y": 5, "width": 12, "height": 6},
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
                "layout": {"x": 0, "y": 11, "width": 12, "height": 4},
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
                "layout": {"x": 0, "y": 15, "width": 12, "height": 4},
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
                "layout": {"x": 0, "y": 19, "width": 6, "height": 4},
            },
            {
                "definition": {
                    "type": "toplist",
                    "title": "Latest Raw Status by Job (1=ok,0=skipped,-1=fail)",
                    "requests": [
                        {"q": (f"top(max:{STABLE_CHECK_RAW_STATUS_METRIC}{{*}} by {{job}}, 50, 'last', 'desc')")}
                    ],
                    "time": {"live_span": STABLE_TIMEFRAME},
                },
                "layout": {"x": 6, "y": 19, "width": 6, "height": 4},
            },
        ],
    }


ALL_DASHBOARDS = [
    skills_leaderboard_dashboard,
    stable_runner_health_dashboard,
]


def get_all_dashboard_configs() -> list[dict]:
    return [d() for d in ALL_DASHBOARDS]
