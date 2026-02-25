from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import col, select

from metta.app_backend.database import get_db
from metta.app_backend.models.tournament import Match, MatchPlayer, MatchStatus, Pool, PoolPlayer
from metta.app_backend.tournament.referees.base import MatchRequest

logger = logging.getLogger(__name__)


class MockMatchExecutionMixin:
    """Executes matches locally with deterministic mock scores."""

    def _mock_policy_skill(self, policy_version_id: UUID) -> float:
        season_name = getattr(self, "season_name", "mock")
        key = f"{season_name}:{policy_version_id}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big") / float(2**64)

    def _mock_match_jitter(self, request: MatchRequest, policy_version_id: UUID) -> float:
        key = f"{request.seed}:{request.assignments}:{request.team_id}:{policy_version_id}"
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return (int.from_bytes(digest[:8], byteorder="big") / float(2**64) - 0.5) * 0.04

    def _compute_mock_scores(self, policy_version_ids: list[UUID], request: MatchRequest) -> dict[UUID, float]:
        unique_ids = list(dict.fromkeys(policy_version_ids))
        base_scores = {pv_id: self._mock_policy_skill(pv_id) for pv_id in unique_ids}
        team_mean = (sum(base_scores.values()) / len(base_scores)) if base_scores else 0.0

        scores: dict[UUID, float] = {}
        for pv_id in unique_ids:
            raw = 0.8 * team_mean + 0.2 * base_scores[pv_id] + self._mock_match_jitter(request, pv_id)
            scores[pv_id] = max(0.0, min(1.0, raw))
        return scores

    async def _create_and_dispatch_match(
        self,
        pool: Pool,
        request: MatchRequest,
    ) -> bool:
        session = get_db()

        pool_players = await session.execute(
            select(PoolPlayer.id, PoolPlayer.policy_version_id).where(col(PoolPlayer.id).in_(request.pool_player_ids))
        )
        pp_to_pv = {row[0]: row[1] for row in pool_players.all()}

        missing = set(request.pool_player_ids) - set(pp_to_pv)
        if missing:
            logger.error(
                "Mock match skipped because PoolPlayers were missing: %s",
                sorted(str(pp) for pp in missing),
            )
            return False

        policy_ids = [pp_to_pv[pool_player_id] for pool_player_id in request.pool_player_ids]
        scores = self._compute_mock_scores(policy_ids, request)

        match = Match(
            pool_id=pool.id,
            assignments=request.assignments,
            team_id=request.team_id,
            status=MatchStatus.completed,
            completed_at=datetime.now(UTC),
        )
        session.add(match)
        await session.flush()

        for idx, pool_player_id in enumerate(request.pool_player_ids):
            policy_id = pp_to_pv[pool_player_id]
            session.add(
                MatchPlayer(
                    match_id=match.id,
                    pool_player_id=pool_player_id,
                    policy_index=idx,
                    score=scores[policy_id],
                )
            )

        await session.commit()
        return True

    async def _sync_match_statuses(self) -> bool:
        return False
