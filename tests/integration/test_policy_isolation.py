import json
import tempfile
from pathlib import Path

import pytest

from cogames.cli.mission import get_mission
from mettagrid.runner.episode_runner import run_episode_isolated
from mettagrid.runner.types import EpisodeSpec, PureSingleEpisodeResult

RESULTS_FILENAME = "results.json"
REPLAY_FILENAME = "replay.json.z"


@pytest.fixture
def env_config():
    _, env_cfg, _ = get_mission("evals.diagnostic_chest_navigation1", variants_arg=None, cogs=2)
    env_cfg.game.max_steps = 10
    return env_cfg


def test_run_episode_with_noop_policy(env_config):
    num_agents = env_config.game.num_agents
    spec = EpisodeSpec(
        policy_uris=["mock://noop"],
        assignments=[0] * num_agents,
        env=env_config,
        seed=42,
    )

    with tempfile.TemporaryDirectory() as output_dir:
        output_path = Path(output_dir)
        results_path = output_path / RESULTS_FILENAME
        replay_path = output_path / REPLAY_FILENAME
        result = run_episode_isolated(spec, results_path, replay_path=replay_path)
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
    spec = EpisodeSpec(
        policy_uris=["mock://noop", "mock://random"],
        assignments=assignments,
        env=env_config,
        seed=42,
    )

    with tempfile.TemporaryDirectory() as output_dir:
        results_path = Path(output_dir) / RESULTS_FILENAME
        result = run_episode_isolated(spec, results_path)
        assert isinstance(result, PureSingleEpisodeResult)
        assert result.steps > 0
        assert len(result.rewards) == num_agents


def test_run_episode_output_written_to_file(env_config):
    num_agents = env_config.game.num_agents
    spec = EpisodeSpec(
        policy_uris=["mock://noop"],
        assignments=[0] * num_agents,
        env=env_config,
        seed=123,
    )

    with tempfile.TemporaryDirectory() as output_dir:
        results_path = Path(output_dir) / RESULTS_FILENAME
        result = run_episode_isolated(spec, results_path)
        assert results_path.exists()
        data = json.loads(results_path.read_text())
        assert "rewards" in data
        assert "steps" in data
        assert data["steps"] == result.steps
