from itertools import combinations
from uuid import UUID

from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.commissioners.teams.config import PolicyEvalStage
from metta.app_backend.tournament.referees.base import (
    EpisodeTags,
    MatchCountEntry,
    MatchCounts,
    MatchRequest,
    RefereeBase,
)
from metta.app_backend.tournament.referees.envs import GameEnvGenerator
from metta.app_backend.tournament.referees.mock import MockLeaderboardMixin
from metta.app_backend.tournament.referees.teams.constants import MAX_FAILED_ATTEMPTS
from mettagrid.config.mettagrid_config import MettaGridConfig


def make_assignments(num_agents: int, policies_per_team: int) -> list[int]:
    agents_per = num_agents // policies_per_team
    return [i for i in range(policies_per_team) for _ in range(agents_per)]


def _generate_combos(
    player_ids: list[UUID], policies_per_team: int, num_agents: int = 8
) -> list[tuple[list[UUID], list[int]]]:
    assignments = make_assignments(num_agents, policies_per_team)
    return [(list(combo), assignments) for combo in combinations(player_ids, policies_per_team)]


class PolicyStageReferee(RefereeBase):
    game: GameEnvGenerator
    description: str = "Exhaustive team evaluation: all combinations of given team size"

    def __init__(
        self,
        *,
        stage: PolicyEvalStage,
        game: GameEnvGenerator,
        max_failed_attempts: int = MAX_FAILED_ATTEMPTS,
        fixed_map_seed: int | None = None,
    ) -> None:
        self.stage = stage
        self.policies_per_team = stage.policies_per_team
        self.matches_per_combo = stage.matches_per_combo
        self.game = game
        self.env_name = game.env_name
        self.max_failed_attempts = max_failed_attempts
        self.fixed_map_seed = fixed_map_seed

    def make_env(self, seed: int) -> MettaGridConfig:
        return self.game.generate(seed)

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:
        player_ids = sorted(p.id for p in players)
        combos = _generate_combos(player_ids, self.policies_per_team, self.game.num_agents)
        zero_counts = MatchCountEntry.zero()

        pending: list[tuple[int, list[UUID], list[int], int]] = []
        for pp_ids, assignments in combos:
            key = (tuple(sorted(pp_ids)), tuple(assignments))
            counts = match_counts.get(key, zero_counts)
            if counts.failed >= self.max_failed_attempts:
                continue
            needed = self.matches_per_combo - counts.completed - counts.in_progress
            for match_i in range(needed):
                seed_offset = counts.completed + counts.in_progress + match_i
                pending.append((counts.completed + counts.in_progress + match_i, pp_ids, assignments, seed_offset))

        pending.sort(key=lambda x: x[0])
        if limit > 0:
            pending = pending[:limit]

        seed = 42
        return [
            MatchRequest(
                pool_player_ids=pp_ids,
                assignments=assignments,
                map_seed=self.fixed_map_seed if self.fixed_map_seed is not None else seed + seed_offset,
                episode_tags=EpisodeTags(match_type="team_eval", team_size=self.policies_per_team),
                seed=seed,
            )
            for _, pp_ids, assignments, seed_offset in pending
        ]


class MockPolicyStageReferee(MockLeaderboardMixin, PolicyStageReferee):
    """Policy-stage referee with leaderboard support for mock match execution."""
