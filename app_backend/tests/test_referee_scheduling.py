import json
from uuid import uuid4

import pytest
from metta_alo.rollout import SingleEpisodeJob

from metta.app_backend.models.tournament import MatchStatus, PoolPlayer
from metta.app_backend.tournament.referees.base import MatchData, MatchRequest
from metta.app_backend.tournament.referees.cogsguard import CogsguardPairingReferee, CogsguardSelfPlayReferee
from metta.app_backend.tournament.referees.pairing import PairingReferee
from metta.app_backend.tournament.referees.selfplay import SelfPlayReferee


def _make_player(pool_id=None) -> PoolPlayer:
    return PoolPlayer(id=uuid4(), pool_id=pool_id or uuid4(), policy_version_id=uuid4())


def _make_match_data(pool_player_ids: list, status: MatchStatus, assignments: list[int] | None = None) -> MatchData:
    return MatchData(
        match_id=uuid4(),
        pool_id=uuid4(),
        status=status,
        pool_player_ids=pool_player_ids,
        assignments=assignments or [],
    )


def _to_job_spec(req: MatchRequest) -> dict:
    return SingleEpisodeJob(
        policy_uris=[f"metta://policy/{uuid4()}" for _ in req.pool_player_ids],
        assignments=req.assignments,
        env=req.env,
        seed=req.seed,
        episode_tags=req.episode_tags,
    ).model_dump()


def _assert_job_specs_json_serializable(requests: list[MatchRequest]) -> None:
    for req in requests:
        json.dumps(_to_job_spec(req))


SELF_PLAY_REFEREES = [SelfPlayReferee(), CogsguardSelfPlayReferee()]
PAIRING_REFEREES = [PairingReferee(), CogsguardPairingReferee()]
ALL_REFEREES = SELF_PLAY_REFEREES + PAIRING_REFEREES


# -- serialization --


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_schedule_produces_serializable_jobs(referee):
    requests = referee.get_matches_to_schedule([_make_player()], [])
    assert len(requests) > 0
    _assert_job_specs_json_serializable(requests)


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_schedule_produces_serializable_jobs(referee):
    requests = referee.get_matches_to_schedule([_make_player(), _make_player()], [])
    assert len(requests) > 0
    _assert_job_specs_json_serializable(requests)


# -- self-play correctness --


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_schedules_correct_count(referee):
    p1, p2 = _make_player(), _make_player()
    requests = referee.get_matches_to_schedule([p1, p2], [])
    assert len(requests) == 2 * referee.matches_per_player
    for req in requests:
        assert len(req.pool_player_ids) == 1
        assert req.assignments == [0] * referee.num_agents


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_skips_completed_players(referee):
    p = _make_player()
    prior = [_make_match_data([p.id], MatchStatus.completed) for _ in range(referee.matches_per_player)]
    requests = referee.get_matches_to_schedule([p], prior)
    assert len(requests) == 0


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_skips_in_progress_players(referee):
    p = _make_player()
    prior = [_make_match_data([p.id], MatchStatus.running)]
    requests = referee.get_matches_to_schedule([p], prior)
    assert len(requests) == 0


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_skips_after_max_failures(referee):
    p = _make_player()
    prior = [_make_match_data([p.id], MatchStatus.failed) for _ in range(3)]
    requests = referee.get_matches_to_schedule([p], prior)
    assert len(requests) == 0


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_tags(referee):
    requests = referee.get_matches_to_schedule([_make_player()], [])
    for req in requests:
        assert req.episode_tags["match_type"] == "self_play"
        if referee.game_tag:
            assert req.episode_tags["game"] == referee.game_tag


# -- pairing correctness --


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_schedules_correct_count(referee):
    p1, p2 = _make_player(), _make_player()
    requests = referee.get_matches_to_schedule([p1, p2], [])
    expected = len(referee.match_configurations) * referee.matches_per_config
    assert len(requests) == expected
    for req in requests:
        assert len(req.pool_player_ids) == 2
        assert len(req.assignments) == referee.num_agents


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_covers_all_configurations(referee):
    p1, p2 = _make_player(), _make_player()
    requests = referee.get_matches_to_schedule([p1, p2], [])
    seen_configs = {tuple(req.assignments) for req in requests}
    expected_configs = {tuple(c) for c in referee.match_configurations}
    assert seen_configs == expected_configs


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_skips_completed_config(referee):
    p1, p2 = _make_player(), _make_player()
    config = referee.match_configurations[0]
    prior = [
        _make_match_data(sorted([p1.id, p2.id]), MatchStatus.completed, config)
        for _ in range(referee.matches_per_config)
    ]
    requests = referee.get_matches_to_schedule([p1, p2], prior)
    remaining_configs = {tuple(req.assignments) for req in requests}
    assert tuple(config) not in remaining_configs


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_tags(referee):
    requests = referee.get_matches_to_schedule([_make_player(), _make_player()], [])
    for req in requests:
        assert req.episode_tags["match_type"] == "pairing"
        if referee.game_tag:
            assert req.episode_tags["game"] == referee.game_tag


# -- env config correctness --


@pytest.mark.parametrize("referee", ALL_REFEREES, ids=lambda r: type(r).__name__)
def test_env_has_correct_agent_count(referee):
    env = referee.make_env(seed=42)
    assert env.game.num_agents == referee.num_agents
