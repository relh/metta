from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlmodel import select

# pyright: reportArgumentType=false
# SQLModel Relationship() type annotations cause false positives on join() calls.
from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.tournament import MembershipAction, Pool, Season
from metta.app_backend.tournament.commissioners.base import CommissionerBase, MembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.config import (
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
    TeamTournamentConfig,
)
from metta.app_backend.tournament.commissioners.teams.db_helpers import TeamDbHelpersMixin
from metta.app_backend.tournament.commissioners.teams.sampling import (
    _weighted_sample_without_replacement,
    sample_teams,
)
from metta.app_backend.tournament.commissioners.teams.stage_execution import TeamStageExecutionMixin
from metta.app_backend.tournament.commissioners.teams.stage_planning import (
    TeamStagePlanningMixin,
    _score_pool,
)
from metta.app_backend.tournament.progress import ProgressStage, TeamTournamentProgress
from metta.app_backend.tournament.referees.base import RefereeBase
from metta.app_backend.tournament.stage_stats import build_stage_stats_row, load_stage_stats_counts


class TeamCommissionerBase(
    TeamStageExecutionMixin,
    TeamDbHelpersMixin,
    TeamStagePlanningMixin,
    CommissionerBase,
):
    leaderboard_pool: str
    entry_pool: str
    roll_copy_existing_pools = False
    referees: dict[str, RefereeBase]
    initial_config: TeamTournamentConfig
    _config: TeamTournamentConfig | None

    def __init__(self, season_id: UUID) -> None:
        super().__init__(season_id=season_id)
        self._config = None

    @property
    def config(self) -> TeamTournamentConfig:
        if self._config is None:
            raise ValueError("Team tournament config has not been loaded")
        return self._config

    @with_db
    async def _load_config(self) -> TeamTournamentConfig:
        if self._config is not None:
            return self._config

        session = get_db()
        season = (await session.execute(select(Season).where(Season.id == self.season_id))).scalar_one_or_none()
        if season is None:
            raise ValueError(f"Season '{self.season_name}' not found")

        config_snapshot = season.team_tournament_config
        if config_snapshot is None:
            raise ValueError(f"Season '{season.name}:v{season.version}' is missing team_tournament_config")

        self._config = TeamTournamentConfig.model_validate(config_snapshot)
        return self._config

    @classmethod
    def get_initial_season_fields(cls) -> dict[str, Any]:
        return {"team_tournament_config": cls.initial_config.model_dump()}

    def get_new_submission_membership_changes(self, policy_version_id: UUID) -> list[MembershipChangeRequest]:
        return [
            MembershipChangeRequest(
                pool_name=self.entry_pool,
                policy_version_id=policy_version_id,
                action=MembershipAction.add,
                notes="Seed policy for team tournament",
            )
        ]

    async def get_membership_changes(self, pools: dict[str, Pool]) -> list[MembershipChangeRequest]:  # type: ignore[unused-arg]
        return []

    @with_db
    async def get_progress(self) -> TeamTournamentProgress:
        session = get_db()
        season = await self._resolve_target_season()
        if season is None:
            raise ValueError(f"Season '{self.season_name}' not found")
        await self._load_config()
        pools = await self._get_pools(season.id)
        stage_bindings = self._stage_bindings()
        score_pool_name = _score_pool()

        relevant_pool_names = {binding.input_pool for binding in stage_bindings}
        relevant_pool_names.add(score_pool_name)
        relevant_pool_ids = {pool.id for name, pool in pools.items() if name in relevant_pool_names}

        counts = await load_stage_stats_counts(
            session,
            relevant_pool_ids,
            include_retired_policies=False,
        )

        stage_stats = [
            build_stage_stats_row(binding.input_pool, pools.get(binding.input_pool), counts)
            for binding in stage_bindings
        ]
        stage_stats.append(build_stage_stats_row(score_pool_name, pools.get(score_pool_name), counts))

        stage_flow: list[ProgressStage] = []
        phase = "complete"
        phase_detail: dict[str, str | int] = {}
        active_found = False
        for binding in stage_bindings:
            match binding.stage:
                case PolicyEvalStage():
                    output_pool = pools.get(binding.output_pool)
                    required_output = self._required_output_policies(binding)
                    is_complete = (
                        output_pool is not None and counts.policy_counts.get(output_pool.id, 0) >= required_output
                    )
                case SampleStage():
                    output_pool = pools.get(binding.output_pool)
                    is_complete = output_pool is not None and counts.team_counts.get(output_pool.id, 0) > 0
                case TeamEvalStage():
                    is_complete = binding.output_pool in pools
                case ScoreStage():
                    output_pool = pools.get(binding.output_pool)
                    is_complete = output_pool is not None and counts.policy_counts.get(output_pool.id, 0) > 0

            if is_complete:
                status = "complete"
            elif not active_found:
                status = "active"
                active_found = True
            else:
                status = "pending"

            stage_flow.append(
                ProgressStage(
                    index=binding.index + 1,
                    kind=binding.stage.kind,
                    description=binding.stage.description,
                    input_pool=binding.input_pool,
                    output_pool=binding.output_pool,
                    status=status,
                )
            )

            if not is_complete and phase == "complete":
                phase = binding.stage.kind
                phase_detail = {"pool": binding.input_pool, "stage_index": binding.index + 1}

        return TeamTournamentProgress(
            phase=phase,
            phase_detail=phase_detail,
            stages=stage_stats,
            stage_flow=stage_flow,
            started=season.started_at is not None,
        )


__all__ = [
    "TeamCommissionerBase",
    "sample_teams",
    "_weighted_sample_without_replacement",
]
