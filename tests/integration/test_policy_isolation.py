import json
import shutil

import pytest

from cogames.cli.mission import get_mission
from mettagrid.runner.episode_runner import EpisodeResult, run_episode
from mettagrid.runner.job_specs import SingleEpisodeJob
from mettagrid.runner.pure_single_episode_runner import PureSingleEpisodeResult


@pytest.fixture
def env_config():
    _, env_cfg, _ = get_mission("evals.diagnostic_chest_navigation1", variants_arg=None, cogs=2)
    env_cfg.game.max_steps = 10
    return env_cfg


def test_run_episode_with_noop_policy(env_config):
    num_agents = env_config.game.num_agents
    job = SingleEpisodeJob(
        policy_uris=["mock://noop"],
        assignments=[0] * num_agents,
        env=env_config,
        seed=42,
    )

    episode = run_episode(job, capture_replay=True)
    try:
        assert isinstance(episode, EpisodeResult)
        assert isinstance(episode.result, PureSingleEpisodeResult)
        assert episode.result.steps > 0
        assert len(episode.result.rewards) == num_agents
        assert len(episode.result.action_timeouts) == num_agents
        assert episode.results_path.exists()
        assert episode.replay_path is not None
        assert episode.replay_path.exists()

        saved = PureSingleEpisodeResult.model_validate_json(episode.results_path.read_text())
        assert saved.steps == episode.result.steps
        assert saved.rewards == episode.result.rewards
    finally:
        shutil.rmtree(episode.results_path.parent, ignore_errors=True)


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

    episode = run_episode(job)
    try:
        assert isinstance(episode.result, PureSingleEpisodeResult)
        assert episode.result.steps > 0
        assert len(episode.result.rewards) == num_agents
    finally:
        shutil.rmtree(episode.results_path.parent, ignore_errors=True)


def test_run_episode_output_written_to_file(env_config):
    num_agents = env_config.game.num_agents
    job = SingleEpisodeJob(
        policy_uris=["mock://noop"],
        assignments=[0] * num_agents,
        env=env_config,
        seed=123,
    )

    episode = run_episode(job)
    try:
        assert episode.results_path.exists()
        data = json.loads(episode.results_path.read_text())
        assert "rewards" in data
        assert "steps" in data
        assert data["steps"] == episode.result.steps
    finally:
        shutil.rmtree(episode.results_path.parent, ignore_errors=True)
