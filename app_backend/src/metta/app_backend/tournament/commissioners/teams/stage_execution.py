from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import select

# pyright: reportAttributeAccessIssue=false
from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.tournament import MembershipAction, Pool, PoolPlayer, Season, Team
from metta.app_backend.tournament.commissioners.base import MembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.config import (
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
)
from metta.app_backend.tournament.commissioners.teams.db_helpers import TeamMembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.sampling import sample_teams
from metta.app_backend.tournament.commissioners.teams.stage_planning import StageBinding
from metta.app_backend.tournament.referees.base import MatchCountEntry, RefereeBase
from metta.app_backend.tournament.referees.teams.team_stage import TeamStageReferee
from metta.app_backend.tournament.settings import MAX_OUTSTANDING_MATCHES_PER_SEASON
from metta.app_backend.tournament.teams.scoring import compute_policy_placement_scores, rank_teams_by_score

logger = logging.getLogger(__name__)


class TeamStageExecutionMixin:
    @staticmethod
    def _require_pool_name(pool: Pool) -> str:
        pool_name = pool.name
        if pool_name is None:
            raise AssertionError("Policy stage input pool must have a name")
        return pool_name

    def _failed_out_policy_ids(
        self,
        *,
        current_players: list[PoolPlayer],
        policy_scores: dict[UUID, float],
        policy_counts: dict[UUID, MatchCountEntry],
    ) -> set[UUID]:
        zero_counts = MatchCountEntry.zero()
        return {
            player.policy_version_id
            for player in current_players
            if player.policy_version_id not in policy_scores
            and policy_counts.get(player.id, zero_counts).failed >= self.config.max_failed_attempts
        }

    def _build_policy_stage_membership_changes(
        self,
        *,
        input_pool_name: str,
        output_pool_name: str,
        survivor_ids: set[UUID],
        failed_out_policy_ids: set[UUID],
        demoted_ids: set[UUID] | None = None,
    ) -> list[MembershipChangeRequest]:
        changes = [
            MembershipChangeRequest(
                pool_name=output_pool_name,
                policy_version_id=policy_version_id,
                action=MembershipAction.add,
                notes=f"Advanced from {input_pool_name}",
            )
            for policy_version_id in sorted(survivor_ids)
        ]
        changes.extend(
            MembershipChangeRequest(
                pool_name=input_pool_name,
                policy_version_id=policy_version_id,
                action=MembershipAction.remove,
                notes=(
                    f"Failed out in {input_pool_name}: reached {self.config.max_failed_attempts} "
                    "failed attempts without score"
                ),
            )
            for policy_version_id in sorted(failed_out_policy_ids)
        )
        if demoted_ids:
            changes.extend(
                MembershipChangeRequest(
                    pool_name=output_pool_name,
                    policy_version_id=policy_version_id,
                    action=MembershipAction.remove,
                    notes=f"Demoted from {output_pool_name}: no longer in top survivors from {input_pool_name}",
                )
                for policy_version_id in sorted(demoted_ids)
            )
        return changes

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
        slots = max(0, MAX_OUTSTANDING_MATCHES_PER_SEASON - outstanding)
        if slots <= 0:
            return 0

        requests = referee.get_matches_to_schedule(active_players, match_counts, limit=slots)
        self._require_pool_env_config(pool)
        total = 0
        for req in requests:
            if await self._create_and_dispatch_match(pool, req):
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

    def _required_output_policies(self, binding: StageBinding) -> int:
        if not isinstance(binding.stage, PolicyEvalStage):
            raise AssertionError("required output policies only apply to policy stages")

        policy_bindings = [b for b in self._stage_bindings() if isinstance(b.stage, PolicyEvalStage)]
        required_by_index: dict[int, int] = {}
        required_output = self.config.sample_stage.team_size
        for policy_binding in reversed(policy_bindings):
            required_by_index[policy_binding.index] = required_output
            required_output = max(policy_binding.stage.min_policies or 0, required_output)

        return required_by_index[binding.index]

    async def _advance_policy_stage(
        self,
        season: Season,
        input_pool: Pool,
        output_pool_name: str,
        stage: PolicyEvalStage,
        output_pool: Pool | None = None,
    ) -> bool:
        session = get_db()
        input_pool_name = self._require_pool_name(input_pool)
        current_players = await self._get_pool_players(input_pool.id)
        policy_scores = await self._compute_policy_scores(input_pool.id)

        player_ids = {player.id for player in current_players}
        policy_counts = await self._get_policy_match_counts(input_pool.id, player_ids)
        failed_out_policy_ids = self._failed_out_policy_ids(
            current_players=current_players,
            policy_scores=policy_scores,
            policy_counts=policy_counts,
        )

        if stage.elim is None:
            survivors = {pp.policy_version_id for pp in current_players}
        elif not policy_scores:
            survivors = set()
        else:
            elim_result = stage.elim.apply(policy_scores)
            survivors = elim_result.survivors
            if elim_result.eliminated:
                logger.info(
                    "[%s] policy stage %s: eliminated %s policies: %s",
                    self.season_name,
                    input_pool_name,
                    len(elim_result.eliminated),
                    {str(pv_id)[:8]: reason for pv_id, reason in elim_result.eliminated.items()},
                )

        if failed_out_policy_ids:
            survivors -= failed_out_policy_ids
            logger.info(
                "[%s] policy stage %s: %s failed out (>= %s failures without score)",
                self.season_name,
                input_pool_name,
                len(failed_out_policy_ids),
                self.config.max_failed_attempts,
            )

        created_output_pool = output_pool is None
        if output_pool is None:
            output_pool = Pool(season_id=season.id, name=output_pool_name)
            session.add(output_pool)
            await session.commit()
        else:
            await session.commit()

        if created_output_pool:
            existing_output_policy_ids = set()
        else:
            existing_output_policy_ids = {
                row[0]
                for row in (
                    await session.execute(
                        select(PoolPlayer.policy_version_id).where(PoolPlayer.pool_id == output_pool.id)
                    )
                ).all()
            }

        survivor_ids = {pp.policy_version_id for pp in current_players if pp.policy_version_id in survivors}
        new_survivor_ids = survivor_ids - existing_output_policy_ids
        demoted_ids = existing_output_policy_ids - survivor_ids
        changes = self._build_policy_stage_membership_changes(
            input_pool_name=input_pool_name,
            output_pool_name=output_pool_name,
            survivor_ids=new_survivor_ids,
            failed_out_policy_ids=failed_out_policy_ids,
            demoted_ids=demoted_ids,
        )
        await self._apply_membership_changes(changes)

        changed = created_output_pool or bool(new_survivor_ids) or bool(failed_out_policy_ids) or bool(demoted_ids)
        if changed:
            logger.info(
                "[%s] policy stage advanced: %s -> %s (%s survivors, %s newly promoted, %s demoted)",
                self.season_name,
                input_pool_name,
                output_pool_name,
                len(survivors),
                len(new_survivor_ids),
                len(demoted_ids),
            )
        return changed

    async def _advance_team_stage(
        self,
        season: Season,
        input_pool: Pool,
        output_pool_name: str,
        alive_teams: list[Team],
        cull_fraction: float,
    ) -> None:
        session = get_db()
        team_ids = {team.id for team in alive_teams}
        team_scores = await self._compute_team_scores(input_pool.id, team_ids)
        team_counts = await self._get_team_match_counts(input_pool.id, team_ids)
        zero_counts = MatchCountEntry.zero()

        failed_out_teams: list[Team] = []
        ranked: list[Team] = []
        for team in alive_teams:
            if team.id in team_scores:
                team.score = team_scores[team.id]
                ranked.append(team)
                continue

            counts = team_counts.get(team.id, zero_counts)
            if counts.failed >= self.config.max_failed_attempts:
                failed_out_teams.append(team)
                continue

            raise AssertionError(
                f"Team {team.id} in {input_pool.name} has no score and has not exhausted retry attempts"
            )

        ranked.sort(key=lambda team: team_scores[team.id], reverse=True)

        cutoff = max(1, int(len(ranked) * (1 - cull_fraction))) if ranked else 0
        survivors = ranked[:cutoff]
        eliminated = ranked[cutoff:] + failed_out_teams

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
            "[%s] team stage advanced: %s -> %s (%s survivors, %s eliminated, %s failed out)",
            self.season_name,
            input_pool.name,
            output_pool_name,
            len(survivors),
            len(eliminated),
            len(failed_out_teams),
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

        output_pool = pools.get(binding.output_pool)
        changed = await self._advance_policy_stage(
            season,
            input_pool,
            binding.output_pool,
            stage,
            output_pool=output_pool,
        )

        pools = await self._get_pools(season.id)
        output_pool = pools[binding.output_pool]

        required_output = self._required_output_policies(binding)

        output_players = await self._get_pool_players(output_pool.id)
        if len(output_players) < required_output:
            logger.info(
                "[%s] %s waiting for promoted policies in %s: %s/%s",
                self.season_name,
                binding.input_pool,
                binding.output_pool,
                len(output_players),
                required_output,
            )
            return changed, False

        return changed, True

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

        team_pool_players = await self._get_pool_players(output_pool.id)
        available_pv_ids = {pp.policy_version_id for pp in team_pool_players}
        scores = {pv_id: score for pv_id, score in scores.items() if pv_id in available_pv_ids}

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
            if binding.output_pool in pools:
                return False, True
            await self._advance_team_stage(season, input_pool, binding.output_pool, [], stage.cull_fraction)
            return True, True

        baseline_referee = TeamStageReferee(
            matches_per_team=stage.matches_per_team,
            teams=[],
            game=self.config.game,
            max_failed_attempts=self.config.max_failed_attempts,
            fixed_map_seed=self.config.fixed_map_seed,
        )
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
        created_output_pool = False
        if output_pool is None:
            output_pool = Pool(season_id=season.id, name=binding.output_pool)
            session.add(output_pool)
            await session.flush()
            created_output_pool = True

        existing_scores = await self._get_pool_players(output_pool.id)
        if existing_scores:
            return False, True

        teams = await self._get_teams(input_pool.id)
        if not teams:
            if created_output_pool:
                await session.commit()
            return created_output_pool, True

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
