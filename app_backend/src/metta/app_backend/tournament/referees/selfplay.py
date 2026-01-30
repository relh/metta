from abc import abstractmethod

from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.referees.base import MatchCounts, MatchRequest, RefereeBase
from metta.app_backend.tournament.referees.envs import make_shared_rewards_env
from mettagrid.config.mettagrid_config import MettaGridConfig

MAX_FAILED_ATTEMPTS = 3


class SelfPlayRefereeBase(RefereeBase):
    num_agents: int
    matches_per_player: int = 2
    game_tag: str | None = None
    skip_replay: bool = False

    @abstractmethod
    def make_env(self, seed: int) -> MettaGridConfig:
        pass

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
    ) -> list[MatchRequest]:
        assignments = tuple([0] * self.num_agents)
        requests: list[MatchRequest] = []
        for player in players:
            key = ((player.id,), assignments)
            completed, failed, in_progress = match_counts.get(key, (0, 0, 0))

            if failed >= MAX_FAILED_ATTEMPTS:
                continue
            if in_progress > 0:
                continue

            seed = 42
            needed = self.matches_per_player - completed
            episode_tags = {"match_type": "self_play"}
            if self.game_tag:
                episode_tags["game"] = self.game_tag

            for match_i in range(needed):
                requests.append(
                    MatchRequest(
                        pool_player_ids=[player.id],
                        assignments=[0] * self.num_agents,
                        env=self.make_env(seed + completed + match_i),
                        seed=seed,
                        episode_tags=episode_tags,
                        skip_replay=self.skip_replay,
                    )
                )

        return requests


class SelfPlayReferee(SelfPlayRefereeBase):
    num_agents: int = 4
    description: str = "Self-play matches on Machina 1 Open World"

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_shared_rewards_env(seed, self.num_agents)
