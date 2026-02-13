from unittest.mock import MagicMock
from uuid import UUID, uuid4

from metta.app_backend.queries.episode_stats import compute_episode_stats


def _make_episode(attributes: dict) -> MagicMock:
    ep = MagicMock()
    ep.attributes = attributes
    return ep


def _make_job_policy_version(position: int) -> MagicMock:
    pv = MagicMock()
    pv.position = position
    pv.policy_version = MagicMock()
    pv.policy_version.id = uuid4()
    pv.policy_version.policy.name = f"policy_{position}"
    pv.policy_version.version = 1
    return pv


def test_missing_policy_returns_sentinel_uuid():
    episode = _make_episode(
        {
            "rewards": [1.0, 2.0],
            "stats": {"agent": [{"hp": 10.0}, {"hp": 20.0}], "game": {"length": 5.0}},
        }
    )
    assignments = [0, 1]
    jpv0 = _make_job_policy_version(0)

    _, policy_results, _ = compute_episode_stats(episode, assignments, [jpv0])

    position_1_result = next(pr for pr in policy_results if pr.position == 1)
    assert position_1_result.policy.id == UUID(int=0)


def test_present_policy_has_uuid():
    episode = _make_episode(
        {
            "rewards": [1.0],
            "stats": {"agent": [{"hp": 10.0}], "game": {}},
        }
    )
    assignments = [0]
    jpv0 = _make_job_policy_version(0)

    _, policy_results, _ = compute_episode_stats(episode, assignments, [jpv0])

    assert len(policy_results) == 1
    assert policy_results[0].policy.id == jpv0.policy_version.id
