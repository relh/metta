from abc import abstractmethod
from collections import defaultdict
from typing import Tuple
from uuid import UUID

from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.referees.base import MatchData, MatchRequest, RefereeBase
from metta.app_backend.tournament.referees.envs import make_shared_rewards_env
from mettagrid.config.mettagrid_config import MettaGridConfig


class PairingRefereeBase(RefereeBase):
    num_agents: int
    match_configurations: list[list[int]]
    matches_per_config: int = 5
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
        config_counts: dict[Tuple[UUID, UUID, tuple[int, ...]], int] = defaultdict(int)

        for md in matches:
            pp_set = set(md.pool_player_ids)
            if len(pp_set) == 2 and md.assignments:
                pp_list = sorted(pp_set)
                pair: Tuple[UUID, UUID] = (pp_list[0], pp_list[1])
                config_counts[(pair[0], pair[1], tuple(md.assignments))] += 1

        pending: list[Tuple[int, UUID, UUID, list[int], int]] = []
        player_ids = [p.id for p in players]

        for i, pp1 in enumerate(player_ids):
            for pp2 in player_ids[i + 1 :]:
                pp_list = sorted([pp1, pp2])
                pair = (pp_list[0], pp_list[1])

                for c_idx, config in enumerate(self.match_configurations):
                    key = (pair[0], pair[1], tuple(config))
                    existing = config_counts[key]
                    needed = self.matches_per_config - existing
                    for match_i in range(needed):
                        map_seed_offset = c_idx * 1000 + match_i + existing
                        pending.append((existing, pp1, pp2, config, map_seed_offset))
                        existing += 1

        pending.sort(key=lambda x: x[0])
        seed = 42
        episode_tags_base = {"match_type": "pairing"}
        if self.game_tag:
            episode_tags_base["game"] = self.game_tag

        return [
            MatchRequest(
                pool_player_ids=[pp1, pp2],
                assignments=config,
                env=self.make_env(seed + map_seed_offset),
                episode_tags={**episode_tags_base, "assignments": str(config)},
                seed=seed,
                skip_replay=self.skip_replay,
            )
            for _, pp1, pp2, config, map_seed_offset in pending
        ]


class PairingReferee(PairingRefereeBase):
    num_agents: int = 4
    match_configurations: list[list[int]] = [
        [0, 1, 1, 1],  # 1v3
        [0, 0, 0, 1],  # 3v1
        [0, 0, 1, 1],  # 2v2
    ]
    description: str = (
        "Pairwise matchups on Machina 1 Open World with varied agent splits (1+3, 3+1, 2+2) "
        "and shared rewards; scored by participation-weighted average"
    )

    def make_env(self, seed: int) -> MettaGridConfig:
        return make_shared_rewards_env(seed, self.num_agents)
