from uuid import UUID

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

MAX_FAILED_ATTEMPTS = 1
DEFAULT_PAIRING_GAME = get_game("cogsguard_4agents")
DEFAULT_PAIRING_CONFIGURATIONS: tuple[tuple[int, ...], ...] = (
    (0, 1, 1, 1),  # 1v3
    (0, 0, 0, 1),  # 3v1
    (0, 0, 1, 1),  # 2v2
)
DEFAULT_PAIRING_DESCRIPTION = (
    "Pairwise matchups on Machina 1 Open World with varied agent splits (1+3, 3+1, 2+2) "
    "and shared rewards; scored by participation-weighted average"
)


class PairingRefereeBase(RefereeBase):
    game: GameEnvGenerator
    match_configurations: list[list[int]]
    matches_per_config: int = 5

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
        pending: list[tuple[int, UUID, UUID, list[int], int]] = []
        player_ids = [p.id for p in players]
        zero_counts = MatchCountEntry.zero()

        for i, pp1 in enumerate(player_ids):
            for pp2 in player_ids[i + 1 :]:
                combo = tuple(sorted([pp1, pp2]))

                for c_idx, config in enumerate(self.match_configurations):
                    key = (combo, tuple(config))
                    counts = match_counts.get(key, zero_counts)
                    if counts.failed >= MAX_FAILED_ATTEMPTS:
                        continue
                    if counts.in_progress > 0:
                        continue
                    completed = counts.completed
                    needed = self.matches_per_config - completed
                    for match_i in range(needed):
                        map_seed_offset = c_idx * 1000 + match_i + completed
                        pending.append((completed, pp1, pp2, config, map_seed_offset))
                        completed += 1

        pending.sort(key=lambda x: x[0])
        if limit > 0:
            pending = pending[:limit]
        seed = 42
        return [
            MatchRequest(
                pool_player_ids=[pp1, pp2],
                assignments=config,
                map_seed=seed + map_seed_offset,
                episode_tags=EpisodeTags(match_type="pairing", game=self.env_name, assignments=str(config)),
                seed=seed,
            )
            for _, pp1, pp2, config, map_seed_offset in pending
        ]


class PairingReferee(PairingRefereeBase):
    game = DEFAULT_PAIRING_GAME
    description = DEFAULT_PAIRING_DESCRIPTION
    match_configurations = [list(config) for config in DEFAULT_PAIRING_CONFIGURATIONS]
