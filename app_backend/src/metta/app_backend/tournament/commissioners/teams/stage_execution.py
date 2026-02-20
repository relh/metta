from __future__ import annotations

import logging
from uuid import UUID

# pyright: reportAttributeAccessIssue=false
from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.tournament import MembershipAction, Pool, PoolPlayer, Season, Team
from metta.app_backend.tournament.commissioners.base import MembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.config import (
    FractionElim,
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
    ThresholdElim,
)
from metta.app_backend.tournament.commissioners.teams.db_helpers import TeamMembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.sampling import sample_teams
from metta.app_backend.tournament.commissioners.teams.stage_planning import StageBinding
from metta.app_backend.tournament.referees.base import RefereeBase
from metta.app_backend.tournament.referees.teams.team_stage import TeamStageReferee
from metta.app_backend.tournament.teams.scoring import compute_policy_placement_scores, rank_teams_by_score

logger = logging.getLogger(__name__)


class TeamStageExecutionMixin:
    async def _schedule_with_referee(
        self,
        season: Season,
        pool: Pool,
        referee: RefereeBase,
        *,
        players: list[PoolPlayer] | None = None,
    ) -> int:
        active_players = players if players is not None else await self._get_pool_players(pool.id)
        if not active_players:
            return 0

        active_ids = {p.id for p in active_players}
        match_counts = await self._get_match_counts(pool.id, active_ids)

        outstanding = await self._count_outstanding_matches()
        slots = max(0, self.config.max_outstanding_matches - outstanding)
        if slots <= 0:
            return 0

        requests = referee.get_matches_to_schedule(active_players, match_counts, limit=slots)
        total = 0
        for req in requests:
            if await self._create_and_dispatch_match(pool.id, req, season.compat_version):
                total += 1

        return total

    async def _policy_stage_complete(
        self,
        pool: Pool,
        stage: PolicyEvalStage,
        players: list[PoolPlayer],
    ) -> bool:
        if not players:
            return False

        active_ids = {p.id for p in players}
        match_counts = await self._get_match_counts(pool.id, active_ids)
        referee = self._policy_referee(stage)
        remaining = referee.get_matches_to_schedule(players, match_counts)

        in_flight = await self._count_in_flight_matches(pool.id)
        return not remaining and in_flight == 0

    async def _advance_policy_stage(
        self,
        season: Season,
        input_pool: Pool,
        output_pool_name: str,
        stage: PolicyEvalStage,
    ) -> None:
        session = get_db()
        current_players = await self._get_pool_players(input_pool.id)

        if stage.elim is None:
            survivors = {pp.policy_version_id for pp in current_players}
        else:
            scores = await self._compute_policy_scores(input_pool.id)
            assert scores, f"No scores for {input_pool.name} after stage completion"

            match stage.elim:
                case ThresholdElim(min_score=threshold):
                    survivors = {pv_id for pv_id, score in scores.items() if score >= threshold}
                case FractionElim(fraction=fraction):
                    ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
                    cutoff = max(1, int(len(ranked) * (1 - fraction)))
                    survivors = {pv_id for pv_id, _ in ranked[:cutoff]}

        next_pool = Pool(season_id=season.id, name=output_pool_name)
        session.add(next_pool)
        await session.commit()

        survivor_ids = {pp.policy_version_id for pp in current_players if pp.policy_version_id in survivors}
        changes = [
            MembershipChangeRequest(
                pool_name=output_pool_name,
                policy_version_id=policy_version_id,
                action=MembershipAction.add,
                notes=f"Advanced from {input_pool.name}",
            )
            for policy_version_id in sorted(survivor_ids)
        ]
        await self._apply_membership_changes(changes)

        logger.info(
            "[%s] policy stage advanced: %s -> %s (%s survivors)",
            self.season_name,
            input_pool.name,
            output_pool_name,
            len(survivors),
        )

    async def _advance_team_stage(
        self,
        season: Season,
        input_pool: Pool,
        output_pool_name: str,
        alive_teams: list[Team],
        cull_fraction: float,
    ) -> None:
        session = get_db()
        team_scores = await self._compute_team_scores(input_pool.id, {t.id for t in alive_teams})

        ranked = sorted(alive_teams, key=lambda t: team_scores[t.id], reverse=True)
        for team in ranked:
            team.score = team_scores[team.id]

        cutoff = max(1, int(len(ranked) * (1 - cull_fraction)))
        survivors = ranked[:cutoff]
        eliminated = ranked[cutoff:]

        for team in eliminated:
            team.eliminated = True

        next_pool = Pool(season_id=season.id, name=output_pool_name)
        session.add(next_pool)
        await session.flush()

        await self._copy_pool_players(input_pool.id, next_pool.id)

        changes = [
            TeamMembershipChangeRequest(
                pool_name=output_pool_name,
                cog_specs=[(tpv.policy_version_id, tpv.position) for tpv in team.policy_versions],
                parent_team_id=team.id,
                notes=f"Forked from {input_pool.name} (score={team_scores[team.id]})",
            )
            for team in survivors
        ]

        await session.commit()
        await self._apply_team_membership_changes(changes)

        logger.info(
            "[%s] team stage advanced: %s -> %s (%s survivors, %s eliminated)",
            self.season_name,
            input_pool.name,
            output_pool_name,
            len(survivors),
            len(eliminated),
        )

    async def _compute_final_scores(self, pools: dict[str, Pool]) -> dict[UUID, float]:
        score_binding = self._stage_bindings()[-1]
        assert isinstance(score_binding.stage, ScoreStage)
        score_source_pool = score_binding.score_source_pool or score_binding.input_pool
        team_pool = pools[score_source_pool]
        return await self._compute_policy_scores_from_teams(team_pool.id, score_binding.stage.top_k)

    async def _compute_policy_scores_from_teams(self, team_pool_id: UUID, top_k: int) -> dict[UUID, float]:
        teams = await self._get_teams(team_pool_id)
        if not teams:
            return {}

        team_scores = await self._compute_team_scores(team_pool_id, {team.id for team in teams})
        ranked = rank_teams_by_score(teams, team_scores, require_score=True)
        placement_scores = compute_policy_placement_scores(ranked, top_k=top_k)
        return {policy_version_id: score for policy_version_id, (score, _) in placement_scores.items()}

    async def _run_policy_eval_stage(
        self,
        season: Season,
        pools: dict[str, Pool],
        binding: StageBinding,
        stage: PolicyEvalStage,
    ) -> tuple[bool, bool]:
        input_pool = pools.get(binding.input_pool)
        if input_pool is None:
            return False, False

        referee = self._policy_referee(stage)
        await self._ensure_pools_exist(season, {binding.input_pool: referee})

        players = await self._get_pool_players(input_pool.id)

        if binding.input_pool == self.entry_pool and season.started_at is None:
            logger.info(
                "[%s] %s waiting for manual start (%s policies)",
                self.season_name,
                binding.input_pool,
                len(players),
            )
            return False, False

        if stage.min_policies is not None and len(players) < stage.min_policies:
            logger.info(
                "[%s] %s waiting for policies: %s/%s",
                self.season_name,
                binding.input_pool,
                len(players),
                stage.min_policies,
            )
            return False, False

        if not await self._policy_stage_complete(input_pool, stage, players):
            scheduled = await self._schedule_with_referee(season, input_pool, referee, players=players)
            if scheduled > 0:
                logger.info(
                    "[%s] scheduled %s policy eval matches for %s",
                    self.season_name,
                    scheduled,
                    input_pool.name,
                )
            return scheduled > 0, False

        if binding.output_pool in pools:
            return False, True

        await self._advance_policy_stage(season, input_pool, binding.output_pool, stage)
        return True, True

    async def _run_sample_stage(
        self,
        season: Season,
        pools: dict[str, Pool],
        binding: StageBinding,
        stage: SampleStage,
    ) -> tuple[bool, bool]:
        input_pool = pools.get(binding.input_pool)
        if input_pool is None:
            return False, False

        session = get_db()
        output_pool = pools.get(binding.output_pool)
        if output_pool is None:
            output_pool = await self._create_team_pool(season.id, binding.output_pool)
            await self._copy_pool_players(input_pool.id, output_pool.id)
            await session.commit()
            pools = await self._get_pools(season.id)
            output_pool = pools[binding.output_pool]

        existing_teams = await self._get_teams(output_pool.id)
        if existing_teams:
            return False, True

        score_pool_name = binding.score_source_pool or binding.input_pool
        scores = await self._compute_policy_scores(pools[score_pool_name].id)
        sampled_teams = sample_teams(
            scores,
            team_size=stage.team_size,
            num_teams=stage.num_teams,
            min_teams_per_policy=self.config.min_teams_per_policy,
        )

        changes = [
            TeamMembershipChangeRequest(
                pool_name=binding.output_pool,
                cog_specs=[(pv_id, pos) for pos, pv_id in enumerate(team_pvs)],
                notes=f"Sampled from {binding.input_pool}",
            )
            for team_pvs in sampled_teams
        ]

        await self._apply_team_membership_changes(changes)
        logger.info(
            "[%s] sampled %s teams into %s",
            self.season_name,
            len(sampled_teams),
            binding.output_pool,
        )

        return True, True

    async def _run_team_eval_stage(
        self,
        season: Season,
        pools: dict[str, Pool],
        binding: StageBinding,
        stage: TeamEvalStage,
    ) -> tuple[bool, bool]:
        input_pool = pools.get(binding.input_pool)
        if input_pool is None:
            return False, False

        alive_teams = await self._get_alive_teams(input_pool.id)
        if not alive_teams:
            return False, False

        baseline_referee = TeamStageReferee(matches_per_team=stage.matches_per_team, teams=[], game=self.config.game)
        await self._ensure_pools_exist(season, {binding.input_pool: baseline_referee})

        if not await self._all_teams_done(input_pool.id, alive_teams, stage.matches_per_team):
            team_configs = await self._build_team_configs(input_pool.id, alive_teams)
            scheduled = await self._schedule_team_eval_matches(season, input_pool, team_configs, stage.matches_per_team)
            if scheduled > 0:
                logger.info(
                    "[%s] scheduled %s team eval matches for %s",
                    self.season_name,
                    scheduled,
                    input_pool.name,
                )
            return scheduled > 0, False

        if binding.output_pool in pools:
            return False, True

        await self._advance_team_stage(season, input_pool, binding.output_pool, alive_teams, stage.cull_fraction)
        return True, True

    async def _run_score_stage(
        self,
        season: Season,
        pools: dict[str, Pool],
        binding: StageBinding,
        stage: ScoreStage,
    ) -> tuple[bool, bool]:  # type: ignore[unused-arg]
        input_pool = pools.get(binding.input_pool)
        if input_pool is None:
            return False, False

        session = get_db()
        output_pool = pools.get(binding.output_pool)
        if output_pool is None:
            output_pool = Pool(season_id=season.id, name=binding.output_pool)
            session.add(output_pool)
            await session.flush()

        existing_scores = await self._get_pool_players(output_pool.id)
        if existing_scores:
            return False, True

        teams = await self._get_teams(input_pool.id)
        if not teams:
            return False, False

        policy_ids = sorted({tpv.policy_version_id for team in teams for tpv in team.policy_versions})
        for pv_id in policy_ids:
            session.add(PoolPlayer(pool_id=output_pool.id, policy_version_id=pv_id))

        await session.commit()
        logger.info(
            "[%s] materialized score pool %s with %s policies",
            self.season_name,
            binding.output_pool,
            len(policy_ids),
        )
        return True, True

    async def _run_stage(self, season: Season, pools: dict[str, Pool], binding: StageBinding) -> tuple[bool, bool]:
        match binding.stage:
            case PolicyEvalStage() as stage:
                return await self._run_policy_eval_stage(season, pools, binding, stage)
            case SampleStage() as stage:
                return await self._run_sample_stage(season, pools, binding, stage)
            case TeamEvalStage() as stage:
                return await self._run_team_eval_stage(season, pools, binding, stage)
            case ScoreStage() as stage:
                return await self._run_score_stage(season, pools, binding, stage)

    @with_db
    async def _run_cycle(self) -> bool:
        season = await self._resolve_target_season()
        if season is None:
            raise ValueError(f"Season '{self.season_name}' not found")
        await self._load_config()
        status_changed = await self._sync_match_statuses()
        had_activity = status_changed

        first_policy_stage = self.config.policy_eval_stages[0]
        await self._ensure_pools_exist(season, {self.entry_pool: self._policy_referee(first_policy_stage)})

        for binding in self._stage_bindings():
            pools = await self._get_pools(season.id)
            changed, complete = await self._run_stage(season, pools, binding)
            had_activity = had_activity or changed
            if not complete:
                return had_activity

        return had_activity
