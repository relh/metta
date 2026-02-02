from uuid import UUID

from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.referees.base import MatchCounts, MatchRequest, RefereeBase
from metta.app_backend.tournament.referees.envs import make_shared_rewards_env
from mettagrid.config.mettagrid_config import MettaGridConfig

MAX_FAILED_ATTEMPTS = 1


class PairingRefereeBase(RefereeBase):
    num_agents: int
    match_configurations: list[list[int]]
    matches_per_config: int = 5
    game_tag: str | None = None
    skip_replay: bool = False

    def get_matches_to_schedule(
        self,
        players: list[PoolPlayer],
        match_counts: MatchCounts,
        limit: int = 0,
    ) -> list[MatchRequest]:
        pending: list[tuple[int, UUID, UUID, list[int], int]] = []
        player_ids = [p.id for p in players]

        for i, pp1 in enumerate(player_ids):
            for pp2 in player_ids[i + 1 :]:
                combo = tuple(sorted([pp1, pp2]))

                for c_idx, config in enumerate(self.match_configurations):
                    key = (combo, tuple(config))
                    completed, failed, in_progress = match_counts.get(key, (0, 0, 0))
                    if failed >= MAX_FAILED_ATTEMPTS:
                        continue
                    if in_progress > 0:
                        continue
                    needed = self.matches_per_config - completed
                    for match_i in range(needed):
                        map_seed_offset = c_idx * 1000 + match_i + completed
                        pending.append((completed, pp1, pp2, config, map_seed_offset))
                        completed += 1

        pending.sort(key=lambda x: x[0])
        if limit > 0:
            pending = pending[:limit]
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
