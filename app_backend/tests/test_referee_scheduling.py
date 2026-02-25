from uuid import uuid4

import pytest

from metta.app_backend.models.tournament import PoolPlayer
from metta.app_backend.tournament.referees.base import MatchCountEntry, MatchRequest
from metta.app_backend.tournament.referees.cogsguard import CogsguardPairingReferee, CogsguardSelfPlayReferee
from metta.app_backend.tournament.referees.pairing import PairingReferee
from metta.app_backend.tournament.referees.selfplay import SelfPlayReferee


def _make_player(pool_id=None) -> PoolPlayer:
    return PoolPlayer(id=uuid4(), pool_id=pool_id or uuid4(), policy_version_id=uuid4())


def _assert_match_requests_serializable(requests: list[MatchRequest]) -> None:
    for req in requests:
        req.model_dump()


SELF_PLAY_REFEREES = [SelfPlayReferee(), CogsguardSelfPlayReferee()]
PAIRING_REFEREES = [PairingReferee(), CogsguardPairingReferee()]
ALL_REFEREES = SELF_PLAY_REFEREES + PAIRING_REFEREES


# -- serialization --


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_schedule_produces_serializable_jobs(referee):
    requests = referee.get_matches_to_schedule([_make_player()], {})
    assert len(requests) > 0
    _assert_match_requests_serializable(requests)


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_schedule_produces_serializable_jobs(referee):
    requests = referee.get_matches_to_schedule([_make_player(), _make_player()], {})
    assert len(requests) > 0
    _assert_match_requests_serializable(requests)


# -- self-play correctness --


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_schedules_correct_count(referee):
    p1, p2 = _make_player(), _make_player()
    requests = referee.get_matches_to_schedule([p1, p2], {})
    assert len(requests) == 2 * referee.matches_per_player
    for req in requests:
        assert len(req.pool_player_ids) == 1
        assert req.assignments == [0] * referee.num_agents


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_skips_completed_players(referee):
    p = _make_player()
    assignments = (0,) * referee.num_agents
    counts = {((p.id,), assignments): MatchCountEntry(referee.matches_per_player, 0, 0)}
    requests = referee.get_matches_to_schedule([p], counts)
    assert len(requests) == 0


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_skips_in_progress_players(referee):
    p = _make_player()
    assignments = (0,) * referee.num_agents
    counts = {((p.id,), assignments): MatchCountEntry(0, 0, 1)}
    requests = referee.get_matches_to_schedule([p], counts)
    assert len(requests) == 0


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_skips_after_max_failures(referee):
    p = _make_player()
    assignments = (0,) * referee.num_agents
    counts = {((p.id,), assignments): MatchCountEntry(0, 3, 0)}
    requests = referee.get_matches_to_schedule([p], counts)
    assert len(requests) == 0


@pytest.mark.parametrize("referee", SELF_PLAY_REFEREES, ids=lambda r: type(r).__name__)
def test_selfplay_tags(referee):
    requests = referee.get_matches_to_schedule([_make_player()], {})
    for req in requests:
        assert req.episode_tags.match_type == "self_play"


# -- pairing correctness --


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_schedules_correct_count(referee):
    p1, p2 = _make_player(), _make_player()
    requests = referee.get_matches_to_schedule([p1, p2], {})
    expected = len(referee.match_configurations) * referee.matches_per_config
    assert len(requests) == expected
    for req in requests:
        assert len(req.pool_player_ids) == 2
        assert len(req.assignments) == referee.num_agents


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_covers_all_configurations(referee):
    p1, p2 = _make_player(), _make_player()
    requests = referee.get_matches_to_schedule([p1, p2], {})
    seen_configs = {tuple(req.assignments) for req in requests}
    expected_configs = {tuple(c) for c in referee.match_configurations}
    assert seen_configs == expected_configs


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_skips_completed_config(referee):
    p1, p2 = _make_player(), _make_player()
    config = referee.match_configurations[0]
    combo = tuple(sorted([p1.id, p2.id]))
    counts = {(combo, tuple(config)): MatchCountEntry(referee.matches_per_config, 0, 0)}
    requests = referee.get_matches_to_schedule([p1, p2], counts)
    remaining_configs = {tuple(req.assignments) for req in requests}
    assert tuple(config) not in remaining_configs


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_skips_in_progress_config(referee):
    p1, p2 = _make_player(), _make_player()
    config = referee.match_configurations[0]
    combo = tuple(sorted([p1.id, p2.id]))
    counts = {(combo, tuple(config)): MatchCountEntry(0, 0, 1)}
    requests = referee.get_matches_to_schedule([p1, p2], counts)
    remaining_configs = {tuple(req.assignments) for req in requests}
    assert tuple(config) not in remaining_configs


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_skips_after_max_failures(referee):
    p1, p2 = _make_player(), _make_player()
    config = referee.match_configurations[0]
    combo = tuple(sorted([p1.id, p2.id]))
    counts = {(combo, tuple(config)): MatchCountEntry(0, 1, 0)}
    requests = referee.get_matches_to_schedule([p1, p2], counts)
    remaining_configs = {tuple(req.assignments) for req in requests}
    assert tuple(config) not in remaining_configs


@pytest.mark.parametrize("referee", PAIRING_REFEREES, ids=lambda r: type(r).__name__)
def test_pairing_tags(referee):
    requests = referee.get_matches_to_schedule([_make_player(), _make_player()], {})
    for req in requests:
        assert req.episode_tags.match_type == "pairing"


# -- env config correctness --


@pytest.mark.parametrize("referee", ALL_REFEREES, ids=lambda r: type(r).__name__)
def test_env_has_correct_agent_count(referee):
    env = referee.make_env(seed=42)
    assert env.game.num_agents == referee.num_agents
