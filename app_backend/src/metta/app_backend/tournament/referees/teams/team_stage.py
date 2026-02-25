from typing import Callable
from uuid import UUID

from pydantic import BaseModel

from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.referees.base import (
    EpisodeTags,
    MatchCountEntry,
    MatchCounts,
    MatchRequest,
    RefereeBase,
)
from metta.app_backend.tournament.referees.envs import GameEnvGenerator
from metta.app_backend.tournament.referees.teams.constants import MAX_FAILED_ATTEMPTS
from mettagrid.config.mettagrid_config import MettaGridConfig


class TeamConfig(BaseModel):
    team_id: UUID
    pool_player_ids: list[UUID]
    assignments: list[int]


def build_pending_team_match_schedule(
    teams: list[TeamConfig],
    *,
    matches_per_team: int,
    get_counts: Callable[[TeamConfig], MatchCountEntry],
    max_failed_attempts: int = MAX_FAILED_ATTEMPTS,
    limit: int = 0,
) -> list[tuple[TeamConfig, int]]:
    pending: list[tuple[int, TeamConfig, int]] = []
    for team in teams:
        counts = get_counts(team)
        if counts.failed >= max_failed_attempts:
            continue
        needed = matches_per_team - counts.completed - counts.in_progress
        for match_i in range(needed):
            seed_offset = counts.completed + counts.in_progress + match_i
            pending.append((counts.completed + counts.in_progress + match_i, team, seed_offset))

    pending.sort(key=lambda row: row[0])
    if limit > 0:
        pending = pending[:limit]
    return [(team, seed_offset) for _, team, seed_offset in pending]


class TeamStageReferee(RefereeBase):
    description: str = "Team evaluation rounds"

    def __init__(
        self,
        *,
        matches_per_team: int,
        teams: list[TeamConfig],
        game: GameEnvGenerator,
        max_failed_attempts: int = MAX_FAILED_ATTEMPTS,
    ) -> None:
        self.matches_per_team = matches_per_team
        self.teams = teams
        self.game = game
        self.env_name = game.env_name
        self.max_failed_attempts = max_failed_attempts

    def make_env(self, seed: int) -> MettaGridConfig:
        return self.game.make_env(seed)

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:  # type: ignore[unused-arg]
        zero_counts = MatchCountEntry.zero()
        pending = build_pending_team_match_schedule(
            self.teams,
            matches_per_team=self.matches_per_team,
            get_counts=lambda team: match_counts.get(
                (tuple(sorted(team.pool_player_ids)), tuple(team.assignments)),
                zero_counts,
            ),
            max_failed_attempts=self.max_failed_attempts,
            limit=limit,
        )

        seed = 42
        return [
            MatchRequest(
                pool_player_ids=team.pool_player_ids,
                assignments=team.assignments,
                map_seed=seed + seed_offset,
                episode_tags=EpisodeTags(match_type="team_elimination", team_id=team.team_id),
                seed=seed,
                team_id=team.team_id,
            )
            for team, seed_offset in pending
        ]
