from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from metta.app_backend.tournament.commissioners.teams.config import TeamTournamentStageKind


class StageStats(BaseModel):
    name: str = Field(
        description="Pool identifier for this stage row (Pool.name), such as 'stage-1', 'sample-1', or 'team-round-2'"
    )
    policy_count: int = Field(
        default=0,
        description="Number of policy memberships (PoolPlayer rows) counted for this pool under the endpoint rules",
    )
    match_count: int = Field(default=0, description="Total number of matches in this pool across all statuses")
    completion_pct: float = Field(
        default=0.0,
        description="Completed-match percentage for this pool: completed / total_matches * 100",
    )
    team_count: int | None = Field(
        default=None,
        description="Number of team records in this pool (null when this pool has no teams)",
    )
    eliminated_count: int | None = Field(
        default=None,
        description="Number of teams in this pool with eliminated=true (null when team_count is null)",
    )


class ProgressStage(BaseModel):
    index: int = Field(description="1-indexed position of this stage in TeamTournamentConfig.stages")
    name: str = Field(description="Human-readable stage title for UI display")
    kind: TeamTournamentStageKind = Field(
        description="Configured stage kind: policy_eval, sample_teams, team_eval, or score_policies"
    )
    description: str = Field(description="Resolved stage description derived from configured stage parameters")
    input_pool: str = Field(description="Name of the pool this stage reads from")
    output_pool: str = Field(description="Name of the pool this stage materializes/writes when complete")
    status: Literal["complete", "active", "pending"] = Field(
        description=(
            "Progress marker: complete = stage completion condition satisfied "
            "(output materialized/populated), active = first incomplete stage, pending = later stages"
        )
    )


class TeamTournamentProgress(BaseModel):
    phase: TeamTournamentStageKind | Literal["complete"] = Field(
        description="Current workflow phase: first incomplete stage kind, or 'complete' when all stages are complete"
    )
    phase_detail: dict[str, str | int] = Field(
        default_factory=dict,
        description=(
            "Phase metadata. When phase != 'complete', includes "
            "{'pool': input_pool_name, 'stage_index': 1-indexed stage index}; otherwise {}"
        ),
    )
    stages: list[StageStats] = Field(
        description="Stage statistics for each configured stage input pool, plus the score pool"
    )
    stage_flow: list[ProgressStage] = Field(
        default_factory=list,
        description="Ordered stage plan derived from TeamTournamentConfig.stages with current completion state",
    )
    started: bool = Field(
        default=False,
        description="Whether Season.started_at is set (entry policy-eval waits until this is true)",
    )
