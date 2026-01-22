from abc import abstractmethod
from collections import defaultdict
from uuid import UUID

from metta.app_backend.models.tournament import MatchStatus, PoolPlayer
from metta.app_backend.tournament.referees.base import MatchData, MatchRequest, RefereeBase
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
        matches: list[MatchData],
    ) -> list[MatchRequest]:
        player_ids = {p.id for p in players}
        completed_counts: dict[UUID, int] = defaultdict(int)
        failed_counts: dict[UUID, int] = defaultdict(int)
        in_progress_counts: dict[UUID, int] = defaultdict(int)

        for md in matches:
            pp_set = set(md.pool_player_ids)
            if len(pp_set) == 1 and md.pool_player_ids:
                pp_id = md.pool_player_ids[0]
                if pp_id in player_ids:
                    if md.status == MatchStatus.completed:
                        completed_counts[pp_id] += 1
                    elif md.status == MatchStatus.failed:
                        failed_counts[pp_id] += 1
                    elif md.status in (MatchStatus.pending, MatchStatus.scheduled, MatchStatus.running):
                        in_progress_counts[pp_id] += 1

        requests: list[MatchRequest] = []
        for player in players:
            pp_id = player.id
            completed = completed_counts[pp_id]
            failed = failed_counts[pp_id]
            in_progress = in_progress_counts[pp_id]

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
                        pool_player_ids=[pp_id],
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
