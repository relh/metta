import random
from collections.abc import Callable
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlmodel import col, func, select

import metta.app_backend.tournament.settings as tournament_settings
from metta.app_backend.database import db_session, get_db
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import (
    Match,
    MatchPlayer,
    MatchStatus,
    MettagridEnvConfig,
    Pool,
    PoolPlayer,
    Season,
    Team,
    TeamPolicyVersion,
)
from metta.app_backend.tournament.commissioners.teams.base import (
    TeamCommissionerBase,
    _weighted_sample_with_replacement,
    sample_teams,
)
from metta.app_backend.tournament.commissioners.teams.config import (
    FractionElim,
    GameEnvGenerator,
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
    TeamTournamentConfig,
    ThresholdElim,
)
from metta.app_backend.tournament.commissioners.teams.db_helpers import TeamMembershipChangeRequest
from metta.app_backend.tournament.commissioners.teams.stage_planning import _policy_pool, _score_pool, _team_pool
from metta.app_backend.tournament.referees.base import MatchCountEntry, MatchRequest, RefereeBase
from metta.app_backend.tournament.referees.teams.constants import MAX_FAILED_ATTEMPTS
from metta.app_backend.tournament.referees.teams.policy_stage import (
    PolicyStageReferee,
    _generate_combos,
    make_assignments,
)
from metta.app_backend.tournament.referees.teams.score_stage import ScoreStageReferee
from metta.app_backend.tournament.referees.teams.team_stage import TeamConfig, TeamStageReferee

GameModel = Callable[[list[UUID], list[int]], dict[UUID, float]]


def _make_policy_referee(
    *,
    policies_per_team: int = 1,
    matches_per_combo: int = 10,
    num_agents: int = 8,
) -> PolicyStageReferee:
    return PolicyStageReferee(
        stage=PolicyEvalStage(
            policies_per_team=policies_per_team,
            matches_per_combo=matches_per_combo,
        ),
        game=GameEnvGenerator(num_agents=num_agents),
    )


class DryRunTeamCommissioner(TeamCommissionerBase):
    """Commissioner that resolves matches instantly via a synthetic game model."""

    season_name = "teams"
    display_name = "Teams"
    summary = "Test team tournament"
    entry_pool = _policy_pool(1)
    leaderboard_pool = _score_pool()
    referees = {
        entry_pool: _make_policy_referee(policies_per_team=1),
        leaderboard_pool: ScoreStageReferee(source_team_pool_name=_team_pool(1), top_k=1),
    }
    initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(policies_per_team=1),
            SampleStage(team_size=8, num_teams=16),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=1),
        ],
    )

    def __init__(self, game_model: GameModel, season_id: UUID):
        super().__init__(season_id=season_id)
        self._game_model = game_model

    async def _create_and_dispatch_match(
        self,
        pool: Pool,
        request: MatchRequest,
    ) -> bool:
        session = get_db()
        pv_result = await session.execute(
            select(PoolPlayer.id, PoolPlayer.policy_version_id).where(col(PoolPlayer.id).in_(request.pool_player_ids))
        )
        pp_to_pv = {row[0]: row[1] for row in pv_result.all()}

        pv_ids = [pp_to_pv[pp_id] for pp_id in request.pool_player_ids]
        scores = self._game_model(pv_ids, request.assignments)

        match = Match(
            pool_id=pool.id,
            assignments=request.assignments,
            team_id=request.team_id,
            status=MatchStatus.completed,
        )
        session.add(match)
        await session.flush()

        for idx, pp_id in enumerate(request.pool_player_ids):
            pv_id = pp_to_pv[pp_id]
            session.add(
                MatchPlayer(
                    match_id=match.id,
                    pool_player_id=pp_id,
                    policy_index=idx,
                    score=scores.get(pv_id, 0.0),
                )
            )
        await session.commit()
        return True

    async def _sync_match_statuses(self) -> bool:
        return False


def _make_player(pool_id=None) -> PoolPlayer:
    return PoolPlayer(id=uuid4(), pool_id=pool_id or uuid4(), policy_version_id=uuid4())


def _assert_json_serializable(requests: list[MatchRequest]) -> None:
    for req in requests:
        req.model_dump()


# -- make_assignments --


@pytest.mark.parametrize(
    ("policies_per_team", "expected"),
    [
        (1, [0] * 8),
        (2, [0, 0, 0, 0, 1, 1, 1, 1]),
        (4, [0, 0, 1, 1, 2, 2, 3, 3]),
        (8, [0, 1, 2, 3, 4, 5, 6, 7]),
    ],
    ids=["solo", "pairs", "quads", "full"],
)
def test_make_assignments_variants(policies_per_team, expected):
    assert make_assignments(8, policies_per_team) == expected


# -- CogsGuardGame --


def test_cogsguard_game_make_env():
    game = GameEnvGenerator(num_agents=8)
    env = game.generate(seed=42)
    assert env.game.num_agents == 8


def test_game_registry_rejects_mismatched_num_agents():
    with pytest.raises(ValueError, match="fixed num_agents"):
        GameEnvGenerator(env_name="cogsguard_10agents", num_agents=8)


def test_game_registry_rejects_unknown_env():
    with pytest.raises(ValueError, match="Unknown tournament game"):
        GameEnvGenerator(env_name="not-a-real-game", num_agents=8)


# -- PolicyStageReferee: combo generation --


@pytest.mark.parametrize(
    ("policies_per_team", "expected_combo_count", "expected_assignments"),
    [
        (1, 16, [0] * 8),
        (2, 120, [0, 0, 0, 0, 1, 1, 1, 1]),
        (4, 1820, [0, 0, 1, 1, 2, 2, 3, 3]),
    ],
    ids=["team-size-1", "team-size-2", "team-size-4"],
)
def test_generate_combos_team_size(
    policies_per_team: int,
    expected_combo_count: int,
    expected_assignments: list[int],
):
    player_ids = [uuid4() for _ in range(16)]
    combos = _generate_combos(player_ids, policies_per_team=policies_per_team)
    assert len(combos) == expected_combo_count
    for pp_ids, assignments in combos:
        assert len(pp_ids) == policies_per_team
        assert assignments == expected_assignments


def test_generate_combos_assignments_structure():
    player_ids = [uuid4() for _ in range(4)]

    for policies_per_team in (1, 2, 4):
        combos = _generate_combos(player_ids, policies_per_team=policies_per_team)
        for pp_ids, assignments in combos:
            assert len(assignments) == 8
            assert len(pp_ids) == policies_per_team
            assert set(assignments) == set(range(policies_per_team))


@pytest.mark.parametrize(
    ("policies_per_team", "expected_requests"),
    [
        (1, 4 * 2),  # C(4,1) * 2
        (2, 6 * 2),  # C(4,2) * 2
        (4, 1 * 2),  # C(4,4) * 2
    ],
    ids=["team-size-1", "team-size-2", "team-size-4"],
)
def test_eval_referee_schedules_combos_for_team_size(policies_per_team: int, expected_requests: int):
    players = [_make_player() for _ in range(4)]
    referee = _make_policy_referee(policies_per_team=policies_per_team, matches_per_combo=2)
    requests = referee.get_matches_to_schedule(players, {})
    assert len(requests) == expected_requests


def test_eval_referee_skips_completed():
    players = [_make_player() for _ in range(2)]
    referee = _make_policy_referee(policies_per_team=2, matches_per_combo=3)

    p0, p1 = sorted([players[0].id, players[1].id])
    counts = {
        ((p0, p1), (0, 0, 0, 0, 1, 1, 1, 1)): MatchCountEntry(3, 0, 0),
    }
    requests = referee.get_matches_to_schedule(players, counts)
    assert len(requests) == 0


def test_eval_referee_skips_exhausted_failed_combos():
    players = [_make_player() for _ in range(2)]
    referee = _make_policy_referee(policies_per_team=2, matches_per_combo=10)

    p0, p1 = sorted([players[0].id, players[1].id])
    counts = {
        ((p0, p1), (0, 0, 0, 0, 1, 1, 1, 1)): MatchCountEntry(0, MAX_FAILED_ATTEMPTS, 0),
    }
    requests = referee.get_matches_to_schedule(players, counts)
    assert len(requests) == 0


def test_eval_referee_produces_serializable_jobs():
    players = [_make_player() for _ in range(3)]
    referee = _make_policy_referee(policies_per_team=1, matches_per_combo=1)
    requests = referee.get_matches_to_schedule(players, {})
    assert len(requests) > 0
    _assert_json_serializable(requests)


def test_eval_referee_respects_limit():
    players = [_make_player() for _ in range(4)]
    referee = _make_policy_referee(policies_per_team=1, matches_per_combo=10)
    requests = referee.get_matches_to_schedule(players, {}, limit=5)
    assert len(requests) == 5


def test_eval_referee_env_agent_count():
    referee = _make_policy_referee()
    env = referee.make_env(seed=42)
    assert env.game.num_agents == 8


def test_eval_referee_episode_tags_include_team_size():
    players = [_make_player() for _ in range(2)]
    referee = _make_policy_referee(policies_per_team=2, matches_per_combo=1)
    requests = referee.get_matches_to_schedule(players, {})
    assert len(requests) == 1
    assert requests[0].episode_tags.team_size == 2


# -- _sample_teams --


def test_weighted_sample_with_replacement_allows_duplicates():
    policy_id = uuid4()
    sample = _weighted_sample_with_replacement([policy_id], [1.0], 8)
    assert sample == [policy_id] * 8


def test_sample_allows_duplicate_policies_within_team():
    policy_id = uuid4()
    teams = sample_teams({policy_id: 1.0}, team_size=8, num_teams=3, min_teams_per_policy=1)
    assert len(teams) >= 3
    for team in teams:
        assert team == [policy_id] * 8


def test_sample_ensures_min_coverage():
    policy_ids = [uuid4() for _ in range(10)]
    scores = {pid: 1.0 for pid in policy_ids}
    teams = sample_teams(scores, team_size=8, num_teams=20, min_teams_per_policy=5)

    policy_counts: dict = {pid: 0 for pid in policy_ids}
    for team in teams:
        for pid in set(team):
            policy_counts[pid] += 1

    for pid in policy_ids:
        assert policy_counts[pid] >= 5


def test_sample_handles_zero_scores():
    policy_ids = [uuid4() for _ in range(10)]
    scores = {pid: 0.0 for pid in policy_ids}
    teams = sample_teams(scores, team_size=8, num_teams=10, min_teams_per_policy=1)
    assert len(teams) >= 10


def test_sample_rejects_zero_policies():
    with pytest.raises(ValueError):
        sample_teams({}, team_size=8, num_teams=10, min_teams_per_policy=1)


def test_sample_weighted_toward_high_scorers():
    random.seed(42)
    policy_ids = [uuid4() for _ in range(10)]
    scores = {pid: 0.01 for pid in policy_ids}
    top_policy = policy_ids[0]
    scores[top_policy] = 100.0

    teams = sample_teams(scores, team_size=8, num_teams=100, min_teams_per_policy=1)

    top_count = sum(1 for team in teams if top_policy in team)
    assert top_count > 50  # should appear in most teams


# -- TeamStageReferee --


def test_elimination_schedules_for_teams():
    pp1, pp2 = uuid4(), uuid4()
    team_cfg = TeamConfig(
        team_id=uuid4(),
        pool_player_ids=[pp1, pp2],
        assignments=[0, 0, 0, 0, 1, 1, 1, 1],
    )
    referee = TeamStageReferee(matches_per_team=5, teams=[team_cfg], game=GameEnvGenerator())
    requests = referee.get_matches_to_schedule([], {})
    assert len(requests) == 5
    for req in requests:
        assert req.pool_player_ids == [pp1, pp2]
        assert req.assignments == [0, 0, 0, 0, 1, 1, 1, 1]
        assert req.team_id == team_cfg.team_id


def test_elimination_skips_completed_teams():
    pp1, pp2 = uuid4(), uuid4()
    team_cfg = TeamConfig(
        team_id=uuid4(),
        pool_player_ids=[pp1, pp2],
        assignments=[0, 0, 0, 0, 1, 1, 1, 1],
    )
    referee = TeamStageReferee(matches_per_team=5, teams=[team_cfg], game=GameEnvGenerator())
    key = (tuple(sorted([pp1, pp2])), (0, 0, 0, 0, 1, 1, 1, 1))
    counts = {key: MatchCountEntry(5, 0, 0)}
    requests = referee.get_matches_to_schedule([], counts)
    assert len(requests) == 0


def test_elimination_skips_exhausted_failed_teams():
    pp1, pp2 = uuid4(), uuid4()
    team_cfg = TeamConfig(
        team_id=uuid4(),
        pool_player_ids=[pp1, pp2],
        assignments=[0, 0, 0, 0, 1, 1, 1, 1],
    )
    referee = TeamStageReferee(matches_per_team=10, teams=[team_cfg], game=GameEnvGenerator())
    key = (tuple(sorted([pp1, pp2])), (0, 0, 0, 0, 1, 1, 1, 1))
    counts = {key: MatchCountEntry(0, MAX_FAILED_ATTEMPTS, 0)}
    requests = referee.get_matches_to_schedule([], counts)
    assert len(requests) == 0


def test_elimination_multiple_teams():
    teams = []
    for _ in range(3):
        pp = uuid4()
        teams.append(
            TeamConfig(
                team_id=uuid4(),
                pool_player_ids=[pp],
                assignments=[0] * 8,
            )
        )
    referee = TeamStageReferee(matches_per_team=2, teams=teams, game=GameEnvGenerator())
    requests = referee.get_matches_to_schedule([], {})
    assert len(requests) == 6  # 3 teams * 2 matches


@pytest.mark.asyncio
async def test_team_eval_schedules_duplicate_team_compositions_per_team(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {pv_id: 1.0 for pv_id in set(pv_ids)}

    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-dup-{uuid4().hex[:8]}"
    commissioner.initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(policies_per_team=1, matches_per_combo=1),
            SampleStage(team_size=8, num_teams=2, min_per_policy=1),
            TeamEvalStage(matches_per_team=2, cull_fraction=0.0),
            ScoreStage(top_k=1),
        ],
    )

    season_id: UUID
    pool_id: UUID

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        season_id = season.id
        commissioner.season_id = season.id

        env_config = MettagridEnvConfig(
            config_hash=uuid4().hex,
            config={"game": {"map_builder": {"seed": 0}}},
        )
        session.add(env_config)
        await session.flush()

        pool = Pool(season_id=season.id, name="team-round-1", env_config_id=env_config.id)
        session.add(pool)
        await session.flush()
        pool_id = pool.id

        policy_a = Policy(name=f"dup-policy-a-{uuid4().hex[:8]}", user_id="test")
        policy_b = Policy(name=f"dup-policy-b-{uuid4().hex[:8]}", user_id="test")
        session.add(policy_a)
        session.add(policy_b)
        await session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        session.add(pv_a)
        session.add(pv_b)
        await session.flush()

        session.add(PoolPlayer(pool_id=pool.id, policy_version_id=pv_a.id))
        session.add(PoolPlayer(pool_id=pool.id, policy_version_id=pv_b.id))
        await session.flush()

        for _ in range(2):
            team = Team(pool_id=pool.id)
            session.add(team)
            await session.flush()

            for pos, pv_id in enumerate([pv_a.id] * 4 + [pv_b.id] * 4):
                session.add(TeamPolicyVersion(team_id=team.id, policy_version_id=pv_id, position=pos))

        await session.commit()

    async with db_session() as session:
        season = (await session.execute(select(Season).where(Season.id == season_id))).scalar_one()
        pool = (await session.execute(select(Pool).where(Pool.id == pool_id))).scalar_one()
        pool.env_config = (
            await session.execute(select(MettagridEnvConfig).where(MettagridEnvConfig.id == pool.env_config_id))
        ).scalar_one()
        await commissioner._load_config()

        alive_teams = await commissioner._get_alive_teams(pool.id)
        team_configs = await commissioner._build_team_configs(pool.id, alive_teams)
        scheduled = await commissioner._schedule_team_eval_matches(season, pool, team_configs, matches_per_team=2)
        assert scheduled == 4
        assert await commissioner._all_teams_done(pool.id, alive_teams, matches_per_team=2)

        count_rows = await session.execute(
            select(col(Match.team_id), func.count())
            .where(Match.pool_id == pool.id)
            .where(Match.status == MatchStatus.completed)
            .group_by(col(Match.team_id))
        )
        per_team_counts = {row[0]: row[1] for row in count_rows.all()}
        assert sorted(per_team_counts.values()) == [2, 2]


@pytest.mark.asyncio
async def test_all_teams_done_when_retries_exhausted(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(_pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {}

    fail_cap = 1
    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-fail-cap-{uuid4().hex[:8]}"
    commissioner.initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(policies_per_team=1, matches_per_combo=1),
            SampleStage(team_size=8, num_teams=1, min_per_policy=1),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
            ScoreStage(top_k=1),
        ],
        max_failed_attempts=fail_cap,
    )

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

        pool = Pool(season_id=season.id, name="team-round-1")
        session.add(pool)
        await session.flush()

        team = Team(pool_id=pool.id)
        session.add(team)
        await session.flush()

        for _ in range(fail_cap):
            session.add(
                Match(
                    pool_id=pool.id,
                    team_id=team.id,
                    assignments=[0] * 8,
                    status=MatchStatus.failed,
                )
            )

        await session.commit()
        await commissioner._load_config()
        assert await commissioner._all_teams_done(pool.id, [team], matches_per_team=10)


@pytest.mark.asyncio
async def test_schedule_team_eval_matches_uses_configured_failure_cap(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(_pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {}

    fail_cap = 1
    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-schedule-fail-cap-{uuid4().hex[:8]}"
    commissioner.initial_config = commissioner.initial_config.model_copy(update={"max_failed_attempts": fail_cap})

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

        pool = Pool(season_id=season.id, name="team-round-1")
        session.add(pool)
        await session.flush()

        policy = Policy(name=f"teams-schedule-policy-{uuid4().hex[:8]}", user_id="test")
        session.add(policy)
        await session.flush()

        policy_version = PolicyVersion(policy_id=policy.id, version=1)
        session.add(policy_version)
        await session.flush()

        pool_player = PoolPlayer(pool_id=pool.id, policy_version_id=policy_version.id)
        session.add(pool_player)
        await session.flush()

        team = Team(pool_id=pool.id)
        session.add(team)
        await session.flush()

        for pos in range(8):
            session.add(TeamPolicyVersion(team_id=team.id, policy_version_id=policy_version.id, position=pos))

        for _ in range(fail_cap):
            session.add(
                Match(
                    pool_id=pool.id,
                    team_id=team.id,
                    assignments=[0] * 8,
                    status=MatchStatus.failed,
                )
            )

        await session.commit()
        await commissioner._load_config()

        alive_teams = await commissioner._get_alive_teams(pool.id)
        team_configs = await commissioner._build_team_configs(pool.id, alive_teams)
        scheduled = await commissioner._schedule_team_eval_matches(season, pool, team_configs, matches_per_team=2)

        completed_matches = (
            await session.execute(
                select(func.count())
                .select_from(Match)
                .where(Match.pool_id == pool.id)
                .where(Match.status == MatchStatus.completed)
            )
        ).scalar_one()

        assert scheduled == 0
        assert completed_matches == 0


@pytest.mark.asyncio
async def test_score_stage_completes_when_team_input_pool_is_empty(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(_pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {}

    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-empty-score-stage-{uuid4().hex[:8]}"

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

        session.add(Pool(season_id=season.id, name="team-round-1"))
        await session.commit()
        await commissioner._load_config()

        bindings = commissioner._stage_bindings()
        team_binding = next(binding for binding in bindings if isinstance(binding.stage, TeamEvalStage))
        score_binding = next(binding for binding in bindings if isinstance(binding.stage, ScoreStage))
        team_stage = team_binding.stage
        score_stage = score_binding.stage
        assert isinstance(team_stage, TeamEvalStage)
        assert isinstance(score_stage, ScoreStage)

        pools = await commissioner._get_pools(season.id)
        changed, complete = await commissioner._run_team_eval_stage(season, pools, team_binding, team_stage)
        assert changed is True
        assert complete is True

        pools = await commissioner._get_pools(season.id)
        changed, complete = await commissioner._run_score_stage(season, pools, score_binding, score_stage)
        assert changed is True
        assert complete is True

        pools = await commissioner._get_pools(season.id)
        changed, complete = await commissioner._run_score_stage(season, pools, score_binding, score_stage)
        assert changed is False
        assert complete is True


@pytest.mark.asyncio
async def test_policy_stage_reopens_until_downstream_minimum_is_met(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(_pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {}

    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-policy-min-output-{uuid4().hex[:8]}"
    commissioner.initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(policies_per_team=1, matches_per_combo=1, min_policies=1),
            PolicyEvalStage(policies_per_team=1, matches_per_combo=1, min_policies=3),
            SampleStage(team_size=1, num_teams=1, min_per_policy=1),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=1),
        ],
    )

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            started_at=datetime.now(timezone.utc),
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

        stage_1 = Pool(season_id=season.id, name="stage-1")
        stage_2 = Pool(season_id=season.id, name="stage-2")
        session.add(stage_1)
        session.add(stage_2)
        await session.flush()

        policy_a = Policy(name=f"policy-a-{uuid4().hex[:8]}", user_id="test")
        policy_b = Policy(name=f"policy-b-{uuid4().hex[:8]}", user_id="test")
        session.add(policy_a)
        session.add(policy_b)
        await session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        session.add(pv_a)
        session.add(pv_b)
        await session.flush()

        pp_a_stage_1 = PoolPlayer(pool_id=stage_1.id, policy_version_id=pv_a.id)
        pp_b_stage_1 = PoolPlayer(pool_id=stage_1.id, policy_version_id=pv_b.id)
        pp_a_stage_2 = PoolPlayer(pool_id=stage_2.id, policy_version_id=pv_a.id)
        pp_b_stage_2 = PoolPlayer(pool_id=stage_2.id, policy_version_id=pv_b.id)
        session.add(pp_a_stage_1)
        session.add(pp_b_stage_1)
        session.add(pp_a_stage_2)
        session.add(pp_b_stage_2)
        await session.flush()

        for pp in (pp_a_stage_1, pp_b_stage_1):
            match = Match(pool_id=stage_1.id, assignments=[0] * 8, status=MatchStatus.completed)
            session.add(match)
            await session.flush()
            session.add(MatchPlayer(match_id=match.id, pool_player_id=pp.id, policy_index=0, score=1.0))

        await session.commit()
        await commissioner._load_config()

        binding = commissioner._stage_bindings()[0]
        assert isinstance(binding.stage, PolicyEvalStage)

        pools = await commissioner._get_pools(season.id)
        changed, complete = await commissioner._run_policy_eval_stage(season, pools, binding, binding.stage)
        assert changed is False
        assert complete is False
        progress = await commissioner.get_progress()
        assert progress.stage_flow[0].status == "active"
        assert progress.stage_flow[1].status == "pending"

        policy_c = Policy(name=f"policy-c-{uuid4().hex[:8]}", user_id="test")
        session.add(policy_c)
        await session.flush()
        pv_c = PolicyVersion(policy_id=policy_c.id, version=1)
        session.add(pv_c)
        await session.flush()
        pp_c_stage_1 = PoolPlayer(pool_id=stage_1.id, policy_version_id=pv_c.id)
        session.add(pp_c_stage_1)
        await session.flush()

        match_c = Match(pool_id=stage_1.id, assignments=[0] * 8, status=MatchStatus.completed)
        session.add(match_c)
        await session.flush()
        session.add(MatchPlayer(match_id=match_c.id, pool_player_id=pp_c_stage_1.id, policy_index=0, score=1.0))
        await session.commit()

        pools = await commissioner._get_pools(season.id)
        changed, complete = await commissioner._run_policy_eval_stage(season, pools, binding, binding.stage)
        assert changed is True
        assert complete is True

        stage_2_players = await commissioner._get_pool_players(stage_2.id)
        assert {pp.policy_version_id for pp in stage_2_players} == {pv_a.id, pv_b.id, pv_c.id}


@pytest.mark.asyncio
async def test_advance_policy_stage_excludes_failed_out_policies(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(_pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {}

    fail_cap = 1
    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-policy-failout-{uuid4().hex[:8]}"
    commissioner.initial_config = commissioner.initial_config.model_copy(update={"max_failed_attempts": fail_cap})

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

        stage_1 = Pool(season_id=season.id, name="stage-1")
        stage_2 = Pool(season_id=season.id, name="stage-2")
        session.add(stage_1)
        session.add(stage_2)
        await session.flush()

        policy_ok = Policy(name=f"policy-ok-{uuid4().hex[:8]}", user_id="test")
        policy_fail = Policy(name=f"policy-fail-{uuid4().hex[:8]}", user_id="test")
        session.add(policy_ok)
        session.add(policy_fail)
        await session.flush()

        pv_ok = PolicyVersion(policy_id=policy_ok.id, version=1)
        pv_fail = PolicyVersion(policy_id=policy_fail.id, version=1)
        session.add(pv_ok)
        session.add(pv_fail)
        await session.flush()

        pp_ok = PoolPlayer(pool_id=stage_1.id, policy_version_id=pv_ok.id)
        pp_fail = PoolPlayer(pool_id=stage_1.id, policy_version_id=pv_fail.id)
        pp_ok_retired_stage_2 = PoolPlayer(pool_id=stage_2.id, policy_version_id=pv_ok.id, retired=True)
        session.add(pp_ok)
        session.add(pp_fail)
        session.add(pp_ok_retired_stage_2)
        await session.flush()

        # Failed-out policy: MAX_FAILED_ATTEMPTS failures and no score.
        for _ in range(fail_cap):
            failed_match = Match(pool_id=stage_1.id, assignments=[0] * 8, status=MatchStatus.failed)
            session.add(failed_match)
            await session.flush()
            session.add(MatchPlayer(match_id=failed_match.id, pool_player_id=pp_fail.id, policy_index=0))

        # Healthy policy: at least one completed scored match.
        completed_match = Match(pool_id=stage_1.id, assignments=[0] * 8, status=MatchStatus.completed)
        session.add(completed_match)
        await session.flush()
        session.add(MatchPlayer(match_id=completed_match.id, pool_player_id=pp_ok.id, policy_index=0, score=1.0))
        await session.commit()
        await commissioner._load_config()

        await commissioner._advance_policy_stage(
            season=season,
            input_pool=stage_1,
            output_pool_name="stage-2",
            stage=PolicyEvalStage(policies_per_team=1, matches_per_combo=10),
            output_pool=stage_2,
        )
        stage_2_pvs = {
            row[0]
            for row in (
                await session.execute(select(PoolPlayer.policy_version_id).where(PoolPlayer.pool_id == stage_2.id))
            ).all()
        }
        stage_2_rows = (
            (
                await session.execute(
                    select(PoolPlayer).where(
                        PoolPlayer.pool_id == stage_2.id,
                        PoolPlayer.policy_version_id == pv_ok.id,
                    )
                )
            )
            .scalars()
            .all()
        )

        assert pv_ok.id in stage_2_pvs
        assert pv_fail.id not in stage_2_pvs
        assert len(stage_2_rows) == 1
        assert stage_2_rows[0].retired is True
        pp_ok_after = await session.get(PoolPlayer, pp_ok.id)
        pp_fail_after = await session.get(PoolPlayer, pp_fail.id)
        assert pp_ok_after is not None
        assert pp_fail_after is not None
        assert pp_ok_after.retired is False
        assert pp_fail_after.retired is True


@pytest.mark.asyncio
async def test_advance_team_stage_excludes_failed_out_teams(stats_repo: str) -> None:  # noqa: ARG001
    def game_model(_pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {}

    fail_cap = 1
    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.season_name = f"teams-team-failout-{uuid4().hex[:8]}"
    commissioner.initial_config = commissioner.initial_config.model_copy(update={"max_failed_attempts": fail_cap})

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

        round_1 = Pool(season_id=season.id, name="team-round-1")
        session.add(round_1)
        await session.flush()

        policy_ok = Policy(name=f"team-policy-ok-{uuid4().hex[:8]}", user_id="test")
        policy_fail = Policy(name=f"team-policy-fail-{uuid4().hex[:8]}", user_id="test")
        session.add(policy_ok)
        session.add(policy_fail)
        await session.flush()

        pv_ok = PolicyVersion(policy_id=policy_ok.id, version=1)
        pv_fail = PolicyVersion(policy_id=policy_fail.id, version=1)
        session.add(pv_ok)
        session.add(pv_fail)
        await session.flush()

        pp_ok = PoolPlayer(pool_id=round_1.id, policy_version_id=pv_ok.id)
        pp_fail = PoolPlayer(pool_id=round_1.id, policy_version_id=pv_fail.id)
        session.add(pp_ok)
        session.add(pp_fail)
        await session.flush()

        team_ok = Team(pool_id=round_1.id)
        team_fail = Team(pool_id=round_1.id)
        session.add(team_ok)
        session.add(team_fail)
        await session.flush()

        for pos in range(8):
            session.add(TeamPolicyVersion(team_id=team_ok.id, policy_version_id=pv_ok.id, position=pos))
            session.add(TeamPolicyVersion(team_id=team_fail.id, policy_version_id=pv_fail.id, position=pos))
        await session.flush()

        completed_match = Match(
            pool_id=round_1.id,
            team_id=team_ok.id,
            assignments=[0] * 8,
            status=MatchStatus.completed,
        )
        session.add(completed_match)
        await session.flush()
        session.add(MatchPlayer(match_id=completed_match.id, pool_player_id=pp_ok.id, policy_index=0, score=1.0))

        for _ in range(fail_cap):
            session.add(
                Match(
                    pool_id=round_1.id,
                    team_id=team_fail.id,
                    assignments=[0] * 8,
                    status=MatchStatus.failed,
                )
            )

        await session.commit()
        await session.refresh(team_ok)
        await session.refresh(team_fail)
        await commissioner._load_config()

        await commissioner._advance_team_stage(
            season=season,
            input_pool=round_1,
            output_pool_name="team-round-2",
            alive_teams=[team_ok, team_fail],
            cull_fraction=0.0,
        )

        round_2 = (
            await session.execute(select(Pool).where(Pool.season_id == season.id, Pool.name == "team-round-2"))
        ).scalar_one()
        transitioned = (await session.execute(select(Team).where(Team.pool_id == round_2.id))).scalars().all()

        assert len(transitioned) == 1
        assert team_fail.eliminated is True
        assert team_ok.eliminated is False


def test_elimination_respects_limit():
    teams = [TeamConfig(team_id=uuid4(), pool_player_ids=[uuid4()], assignments=[0] * 8) for _ in range(5)]
    referee = TeamStageReferee(matches_per_team=10, teams=teams, game=GameEnvGenerator())
    requests = referee.get_matches_to_schedule([], {}, limit=3)
    assert len(requests) == 3


def test_elimination_produces_serializable_jobs():
    team_cfg = TeamConfig(
        team_id=uuid4(),
        pool_player_ids=[uuid4()],
        assignments=[0] * 8,
    )
    referee = TeamStageReferee(matches_per_team=1, teams=[team_cfg], game=GameEnvGenerator())
    requests = referee.get_matches_to_schedule([], {})
    assert len(requests) == 1
    _assert_json_serializable(requests)


# -- TeamMembershipChangeRequest --


def test_team_membership_change_request_add():
    pv1, pv2 = uuid4(), uuid4()
    change = TeamMembershipChangeRequest(
        pool_name="sample-1-round-1",
        cog_specs=[(pv1, i) for i in range(4)] + [(pv2, i) for i in range(4, 8)],
    )
    assert len(change.cog_specs) == 8
    assert change.parent_team_id is None


def test_team_membership_change_request_with_parent():
    parent_id = uuid4()
    change = TeamMembershipChangeRequest(
        pool_name="sample-1-round-2",
        cog_specs=[(uuid4(), i) for i in range(8)],
        parent_team_id=parent_id,
        notes="Forked from round 1",
    )
    assert change.parent_team_id == parent_id


# -- Team / TeamPolicyVersion model construction --


def test_team_policy_version_creation():
    pv_id = uuid4()
    tpv = TeamPolicyVersion(team_id=uuid4(), policy_version_id=pv_id, position=0)
    assert tpv.policy_version_id == pv_id
    assert tpv.position == 0


def test_team_policy_version_positions():
    pool_id = uuid4()
    team = Team(pool_id=pool_id)
    assert team.eliminated is False
    assert team.score is None

    pv_ids = [uuid4() for _ in range(8)]
    team_policy_versions = [
        TeamPolicyVersion(team_id=team.id, policy_version_id=pv_id, position=i) for i, pv_id in enumerate(pv_ids)
    ]
    assert len(team_policy_versions) == 8
    assert [tpv.position for tpv in team_policy_versions] == list(range(8))


# -- Config types --


DEFAULT_TEST_CONFIG = TeamTournamentConfig(
    game=GameEnvGenerator(num_agents=8),
    stages=[
        PolicyEvalStage(policies_per_team=1, elim=ThresholdElim(min_score=0.01)),
        PolicyEvalStage(policies_per_team=2, elim=FractionElim(fraction=0.25)),
        PolicyEvalStage(policies_per_team=4),
        SampleStage(team_size=8, num_teams=1000),
        TeamEvalStage(matches_per_team=10, cull_fraction=0.5),
        TeamEvalStage(matches_per_team=10, cull_fraction=0.5),
        TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
        ScoreStage(top_k=10),
    ],
)


def test_config_eval_stages():
    config = DEFAULT_TEST_CONFIG
    assert len(config.policy_eval_stages) == 3
    assert config.policy_eval_stages[0].policies_per_team == 1
    assert isinstance(config.policy_eval_stages[0].elim, ThresholdElim)
    assert config.policy_eval_stages[1].policies_per_team == 2
    assert isinstance(config.policy_eval_stages[1].elim, FractionElim)
    assert config.policy_eval_stages[2].policies_per_team == 4
    assert config.policy_eval_stages[2].elim is None


def test_config_sample_and_elim_stages():
    config = DEFAULT_TEST_CONFIG
    assert config.sample_stage.team_size == 8
    assert config.sample_stage.num_teams == 1000
    assert len(config.team_eval_stages) == 3
    assert config.team_eval_stages[0].cull_fraction == 0.5


def test_config_min_teams_per_policy_defaults_to_top_k():
    config = DEFAULT_TEST_CONFIG.model_copy(update={"stages": [*DEFAULT_TEST_CONFIG.stages[:-1], ScoreStage(top_k=7)]})
    assert config.min_teams_per_policy == 7


def test_config_min_teams_per_policy_override():
    config = TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=1),
            SampleStage(team_size=8, num_teams=100, min_per_policy=20),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
            ScoreStage(top_k=10),
        ],
    )
    assert config.min_teams_per_policy == 20


def test_config_legacy_snapshot_defaults_failed_attempt_cap():
    legacy_snapshot = {
        "game": {"kind": "cogsguard", "num_agents": 8},
        "stages": [
            {"kind": "policy_eval", "policies_per_team": 1},
            {"kind": "sample_teams", "team_size": 8, "num_teams": 100},
            {"kind": "team_eval", "matches_per_team": 10, "cull_fraction": 0.0},
            {"kind": "score_policies", "top_k": 10},
        ],
        "max_outstanding_matches": 20,
    }

    config = TeamTournamentConfig.model_validate(legacy_snapshot)
    assert config.max_failed_attempts == MAX_FAILED_ATTEMPTS


def test_config_validates_num_agents_divisibility():
    with pytest.raises(ValueError, match="divisible"):
        TeamTournamentConfig(
            game=GameEnvGenerator(num_agents=8),
            stages=[
                PolicyEvalStage(policies_per_team=3),
                SampleStage(team_size=8, num_teams=10),
                TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
                ScoreStage(top_k=10),
            ],
        )


def test_config_validates_team_formation_divisibility():
    with pytest.raises(ValueError, match="divisible"):
        TeamTournamentConfig(
            game=GameEnvGenerator(num_agents=8),
            stages=[
                PolicyEvalStage(policies_per_team=1),
                SampleStage(team_size=3, num_teams=10),
                TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
                ScoreStage(top_k=10),
            ],
        )


@pytest.mark.asyncio
async def test_get_progress_uses_season_config_snapshot(stats_repo: str) -> None:  # noqa: ARG001
    commissioner = DryRunTeamCommissioner(
        lambda pv_ids, _assignments: {pv_id: 1.0 for pv_id in set(pv_ids)},
        season_id=uuid4(),
    )
    commissioner.season_name = f"teams-progress-config-{uuid4().hex[:8]}"

    season_config = TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=2),
            SampleStage(team_size=8, num_teams=24),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=2),
        ],
    )
    commissioner.initial_config = TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=4),
            SampleStage(team_size=8, num_teams=24),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=9),
        ],
    )

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=season_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        season_id = season.id
        commissioner.season_id = season.id
        session.add(Pool(season_id=season_id, name="stage-1"))

    progress = await commissioner.get_progress()
    assert len(progress.stage_flow) == len(season_config.stages)
    assert progress.stage_flow[0].kind == "policy_eval"
    assert progress.stage_flow[0].name == "Play-ins: two-player"
    assert progress.stage_flow[2].name == "Playoffs: eight-player"
    assert progress.stage_flow[-1].kind == "score_policies"


@pytest.mark.asyncio
async def test_run_cycle_uses_season_config_snapshot(stats_repo: str) -> None:  # noqa: ARG001
    commissioner = DryRunTeamCommissioner(
        lambda pv_ids, _assignments: {pv_id: 1.0 for pv_id in set(pv_ids)},
        season_id=uuid4(),
    )
    commissioner.season_name = f"teams-cycle-config-{uuid4().hex[:8]}"

    season_config = TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=2),
            SampleStage(team_size=8, num_teams=16),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=2),
        ],
    )
    commissioner.initial_config = TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=4),
            SampleStage(team_size=8, num_teams=16),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=2),
        ],
    )

    async with db_session() as session:
        season = Season(
            name=commissioner.season_name,
            canonical=True,
            team_tournament_config=season_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        commissioner.season_id = season.id

    captured: dict[str, int] = {}

    async def fake_ensure_pools_exist(season: Season, referees: dict[str, RefereeBase]) -> dict[str, Pool]:  # type: ignore[unused-arg]
        entry_referee = referees[commissioner.entry_pool]
        assert isinstance(entry_referee, PolicyStageReferee)
        captured["policies_per_team"] = entry_referee.policies_per_team
        return {}

    commissioner._sync_match_statuses = AsyncMock(return_value=False)
    commissioner._ensure_pools_exist = fake_ensure_pools_exist
    commissioner._run_stage = AsyncMock(return_value=(False, False))

    changed = await commissioner._run_cycle()
    assert changed is False
    assert captured["policies_per_team"] == 2


@pytest.mark.asyncio
async def test_get_progress_errors_when_season_team_config_missing(stats_repo: str) -> None:  # noqa: ARG001
    commissioner = DryRunTeamCommissioner(
        lambda pv_ids, _assignments: {pv_id: 1.0 for pv_id in set(pv_ids)},
        season_id=uuid4(),
    )
    commissioner.season_name = f"teams-progress-backfill-{uuid4().hex[:8]}"
    commissioner.initial_config = TeamTournamentConfig(
        stages=[
            PolicyEvalStage(policies_per_team=1),
            SampleStage(team_size=8, num_teams=16),
            TeamEvalStage(matches_per_team=1, cull_fraction=0.0),
            ScoreStage(top_k=3),
        ],
    )

    async with db_session() as session:
        season = Season(name=commissioner.season_name, canonical=True, team_tournament_config=None)
        session.add(season)
        await session.flush()
        season_id = season.id
        commissioner.season_id = season.id
        session.add(Pool(season_id=season_id, name="stage-1"))

    with pytest.raises(ValueError, match="missing team_tournament_config"):
        await commissioner.get_progress()


# -- Integration test: full tournament dry run --


@pytest.mark.asyncio
async def test_full_tournament_dry_run(stats_repo: str, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: ARG001
    random.seed(42)
    monkeypatch.setattr(tournament_settings, "MAX_OUTSTANDING_MATCHES_PER_SEASON", 10000)

    policy_skills: dict[UUID, float] = {}

    def game_model(pv_ids: list[UUID], _assignments: list[int]) -> dict[UUID, float]:
        return {pv_id: policy_skills.get(pv_id, 0.0) for pv_id in set(pv_ids)}

    commissioner = DryRunTeamCommissioner(game_model, season_id=uuid4())
    commissioner.initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(policies_per_team=1, matches_per_combo=1, elim=ThresholdElim(min_score=0.01)),
            PolicyEvalStage(policies_per_team=2, matches_per_combo=1, elim=FractionElim(fraction=0.1)),
            PolicyEvalStage(policies_per_team=4, matches_per_combo=1),
            SampleStage(team_size=4, num_teams=20, min_per_policy=3),
            TeamEvalStage(matches_per_team=2, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=2, cull_fraction=0.0),
            ScoreStage(top_k=3),
        ],
    )

    skills = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]
    pv_by_skill: dict[float, UUID] = {}
    season_id: UUID

    async with db_session() as session:
        from datetime import datetime, timezone  # noqa: PLC0415

        season = Season(
            name="teams",
            canonical=True,
            started_at=datetime.now(timezone.utc),
            team_tournament_config=commissioner.initial_config.model_dump(mode="json"),
        )
        session.add(season)
        await session.flush()
        season_id = season.id
        commissioner.season_id = season.id

        pool = Pool(season_id=season.id, name="stage-1")
        session.add(pool)
        await session.flush()

        for i, skill in enumerate(skills):
            policy = Policy(name=f"policy-{i}-{uuid4().hex[:8]}", user_id="test")
            session.add(policy)
            await session.flush()

            pv = PolicyVersion(policy_id=policy.id, version=1)
            session.add(pv)
            await session.flush()

            session.add(PoolPlayer(pool_id=pool.id, policy_version_id=pv.id))
            policy_skills[pv.id] = skill
            pv_by_skill[skill] = pv.id

    # Run the tournament to completion
    for _ in range(100):
        changed = await commissioner._run_cycle()

        async with db_session():
            pools = await commissioner._get_pools(season_id)

        if "policy-scores-1" in pools and not changed:
            break
    else:
        pytest.fail("Tournament did not complete within 100 cycles")

    # --- Elimination dynamics ---
    async with db_session() as session:
        pools_result = await session.execute(select(Pool).join(Pool.season).where(Season.name == "teams"))  # pyright: ignore[reportArgumentType]
        pools_map = {p.name: p for p in pools_result.scalars().all() if p.name}

        # Zero-skill policy eliminated after stage 1
        stage_2_pvs = set(
            (
                await session.execute(
                    select(PoolPlayer.policy_version_id).where(PoolPlayer.pool_id == pools_map["stage-2"].id)
                )
            )
            .scalars()
            .all()
        )
        assert pv_by_skill[0.0] not in stage_2_pvs
        assert pv_by_skill[1.1] in stage_2_pvs

        # Progressive narrowing: stage-1 > stage-2 > sample-1
        stage_1_pvs = set(
            (
                await session.execute(
                    select(PoolPlayer.policy_version_id).where(PoolPlayer.pool_id == pools_map["stage-1"].id)
                )
            )
            .scalars()
            .all()
        )
        sample_1_pvs = set(
            (
                await session.execute(
                    select(PoolPlayer.policy_version_id).where(PoolPlayer.pool_id == pools_map["sample-1"].id)
                )
            )
            .scalars()
            .all()
        )
        assert len(stage_1_pvs) > len(stage_2_pvs) >= len(sample_1_pvs) >= 8
        assert pv_by_skill[1.1] in sample_1_pvs

        # --- Team rounds structure ---
        tr1 = pools_map.get("team-round-1")
        assert tr1 is not None
        teams_r1 = list((await session.execute(select(Team).where(Team.pool_id == tr1.id))).scalars().all())
        assert len(teams_r1) >= 20

        tr2 = pools_map.get("team-round-2")
        assert tr2 is not None
        teams_r2 = list((await session.execute(select(Team).where(Team.pool_id == tr2.id))).scalars().all())
        assert len(teams_r2) < len(teams_r1)  # Culling reduced team count

        tr3 = pools_map.get("team-round-3")
        assert tr3 is not None
        teams_r3 = list((await session.execute(select(Team).where(Team.pool_id == tr3.id))).scalars().all())
        assert len(teams_r3) == len(teams_r2)

        # --- Final scores ---
        final_scores = await commissioner._compute_final_scores(pools_map)
        assert len(final_scores) > 0

        # Top-skill policy should have a better (lower) score than bottom survivors
        surviving_skills = sorted(s for s in pv_by_skill if pv_by_skill[s] in sample_1_pvs)
        top_pv = pv_by_skill[max(surviving_skills)]
        bottom_pv = pv_by_skill[min(surviving_skills)]
        if top_pv in final_scores and bottom_pv in final_scores:
            assert final_scores[top_pv] <= final_scores[bottom_pv]
