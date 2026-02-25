from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.referees.base import (
    EpisodeTags,
    MatchCountEntry,
    MatchCounts,
    MatchRequest,
    RefereeBase,
)
from metta.app_backend.tournament.referees.envs import GameEnvGenerator, get_game
from mettagrid.config.mettagrid_config import MettaGridConfig

MAX_FAILED_ATTEMPTS = 3
DEFAULT_SELF_PLAY_GAME = get_game("cogsguard_4agents")
DEFAULT_SELF_PLAY_DESCRIPTION = "Self-play matches on Machina 1 Open World"


class SelfPlayRefereeBase(RefereeBase):
    game: GameEnvGenerator
    matches_per_player: int = 2

    @property
    def num_agents(self) -> int:
        return self.game.num_agents

    @property
    def env_name(self) -> str:
        return self.game.env_name

    def make_env(self, seed: int) -> MettaGridConfig:
        return self.game.generate(seed)

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:
        assignments = (0,) * self.num_agents
        requests: list[MatchRequest] = []
        zero_counts = MatchCountEntry.zero()
        for player in players:
            key = ((player.id,), assignments)
            counts = match_counts.get(key, zero_counts)

            if counts.failed >= MAX_FAILED_ATTEMPTS:
                continue
            if counts.in_progress > 0:
                continue

            seed = 42
            needed = self.matches_per_player - counts.completed
            tags = EpisodeTags(match_type="self_play", game=self.env_name)

            for match_i in range(needed):
                requests.append(
                    MatchRequest(
                        pool_player_ids=[player.id],
                        assignments=[0] * self.num_agents,
                        map_seed=seed + counts.completed + match_i,
                        seed=seed,
                        episode_tags=tags,
                    )
                )
                if limit > 0 and len(requests) >= limit:
                    return requests

        return requests


class SelfPlayReferee(SelfPlayRefereeBase):
    game = DEFAULT_SELF_PLAY_GAME
    description = DEFAULT_SELF_PLAY_DESCRIPTION
