from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cog_cyborg.analysis.trajectory import (
        AgentMotifSummary,
        ResourceVector,
        RoleCounts,
        RoleDistanceSummary,
        TrajectoryCheckpoint,
        TrajectoryComparison,
        TrajectoryMilestones,
        TrajectoryReport,
        analyze_cogsguard_policy,
        compare_cogsguard_policies,
        render_trajectory_comparison,
        render_trajectory_report,
    )

__all__ = [
    "AgentMotifSummary",
    "ResourceVector",
    "RoleCounts",
    "RoleDistanceSummary",
    "TrajectoryCheckpoint",
    "TrajectoryComparison",
    "TrajectoryMilestones",
    "TrajectoryReport",
    "analyze_cogsguard_policy",
    "compare_cogsguard_policies",
    "render_trajectory_comparison",
    "render_trajectory_report",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    trajectory = importlib.import_module("cog_cyborg.analysis.trajectory")
    return getattr(trajectory, name)
