from __future__ import annotations

METRIC = "metta.skills.usage"
TIMEFRAME = "2d"


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
        "title": "Skills Leaderboard",
        "description": "Claude Code skill usage across the team",
        "layout_type": "ordered",
        "tags": ["team:dev", "managed-by:code"],
        "widgets": [
            {
                "definition": {
                    "type": "query_value",
                    "title": "Total Invocations",
                    "requests": [{"q": f"sum:{METRIC}{{*}}.as_count()", "aggregator": "sum"}],
                    "time": {"live_span": TIMEFRAME},
                    "precision": 0,
                },
                "layout": {"x": 0, "y": 0, "width": 3, "height": 3},
            },
            _toplist_widget(
                "Top Users",
                group_by="user",
                x=3,
                y=0,
                width=4,
                height=3,
            ),
            _toplist_widget(
                "Top Skills",
                group_by="skill",
                x=7,
                y=0,
                width=5,
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
            _toplist_widget(
                "Usage by Category",
                group_by="skill_prefix",
                x=0,
                y=11,
                width=12,
                height=4,
            ),
        ],
    }


ALL_DASHBOARDS = [
    skills_leaderboard_dashboard,
]


def get_all_dashboard_configs() -> list[dict]:
    return [d() for d in ALL_DASHBOARDS]
