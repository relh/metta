from collections import defaultdict
from uuid import UUID

from metta.app_backend.models.tournament import MatchStatus, PoolPlayer
from metta.app_backend.tournament.referees.base import MatchData, MatchRequest, RefereeBase
from metta.app_backend.tournament.referees.envs import make_shared_rewards_env

NUM_AGENTS = 4
MAX_FAILED_ATTEMPTS = 3


class SelfPlayReferee(RefereeBase):
    """Schedules self-play matches where a single policy controls all agents.

    Each player gets up to `matches_per_player` self-play matches to establish
    a baseline score before being considered for promotion to competition pools.
    Retries failed matches up to MAX_FAILED_ATTEMPTS times.
    """

    matches_per_player: int = 2
    description: str = "Self-play matches on Machina 1 Open World"

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

            # Use completed + match_i so each player plays on the same sequence of maps
            seed = 42
            needed = self.matches_per_player - completed
            for match_i in range(needed):
                requests.append(
                    MatchRequest(
                        pool_player_ids=[pp_id],
                        assignments=[0, 0, 0, 0],
                        env=make_shared_rewards_env(seed + completed + match_i, NUM_AGENTS),
                        seed=seed,
                        episode_tags={"match_type": "self_play"},
                    )
                )

        return requests
