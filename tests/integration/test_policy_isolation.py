import json

import pytest

from cogames.cli.mission import get_mission
from metta.sim.single_episode_runner import run_episode
from mettagrid.runner.job_specs import SingleEpisodeJob
from mettagrid.runner.pure_single_episode_runner import PureSingleEpisodeResult


@pytest.fixture
def env_config():
    _, env_cfg, _ = get_mission("evals.diagnostic_chest_navigation1", variants_arg=None, cogs=2)
    env_cfg.game.max_steps = 10
    return env_cfg


def test_run_episode_with_noop_policy(env_config, tmp_path):
    num_agents = env_config.game.num_agents
    job = SingleEpisodeJob(
        policy_uris=["mock://noop"],
        assignments=[0] * num_agents,
        env=env_config,
        seed=42,
    )

    results_path = tmp_path / "results.json"
    replay_path = tmp_path / "replay.json.z"

    result = run_episode(
        job,
        upload_results_uri=f"file://{results_path}",
        upload_replay_uri=f"file://{replay_path}",
    )

    assert isinstance(result, PureSingleEpisodeResult)
    assert result.steps > 0
    assert len(result.rewards) == num_agents
    assert len(result.action_timeouts) == num_agents
    assert results_path.exists()
    assert replay_path.exists()

    saved = PureSingleEpisodeResult.model_validate_json(results_path.read_text())
    assert saved.steps == result.steps
    assert saved.rewards == result.rewards


def test_run_episode_with_two_different_policies(env_config):
    num_agents = env_config.game.num_agents
    assert num_agents >= 2, "Need at least 2 agents for this test"

    assignments = [i % 2 for i in range(num_agents)]
    job = SingleEpisodeJob(
        policy_uris=["mock://noop", "mock://random"],
        assignments=assignments,
        env=env_config,
        seed=42,
    )

    result = run_episode(job)

    assert isinstance(result, PureSingleEpisodeResult)
    assert result.steps > 0
    assert len(result.rewards) == num_agents


def test_run_episode_output_written_to_file(env_config, tmp_path):
    num_agents = env_config.game.num_agents
    job = SingleEpisodeJob(
        policy_uris=["mock://noop"],
        assignments=[0] * num_agents,
        env=env_config,
        seed=123,
    )

    results_path = tmp_path / "results.json"
    result = run_episode(job, upload_results_uri=f"file://{results_path}")

    assert results_path.exists()
    data = json.loads(results_path.read_text())
    assert "rewards" in data
    assert "steps" in data
    assert data["steps"] == result.steps
