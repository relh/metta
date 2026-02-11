import pytest
import torch

from metta.rl.training.core import _tensorize_requested_env_info


def test_tensorize_requested_env_info_flattens_nested_payloads() -> None:
    info_rows = [
        {"env_collective": {"cogs": {"aligned.junction.held": 1.25}}},
        {"env_collective": {"cogs": {"aligned.junction.held": 2.75}}},
    ]

    env_info_td = _tensorize_requested_env_info(
        info_rows=info_rows,
        requested_keys={"env_collective/cogs/aligned.junction.held"},
        batch_size=2,
        num_env_rows=2,
        agents_per_env=1,
        device=torch.device("cpu"),
    )

    torch.testing.assert_close(
        env_info_td["env_collective/cogs/aligned.junction.held"],
        torch.tensor([1.25, 2.75], dtype=torch.float32),
    )


def test_tensorize_requested_env_info_raises_when_key_missing() -> None:
    info_rows = [{"foo": 1.0}, {"foo": 2.0}]

    with pytest.raises(RuntimeError, match="Missing requested env info key"):
        _tensorize_requested_env_info(
            info_rows=info_rows,
            requested_keys={"bar"},
            batch_size=2,
            num_env_rows=2,
            agents_per_env=1,
            device=torch.device("cpu"),
        )


def test_tensorize_requested_env_info_raises_on_batch_mismatch() -> None:
    info_rows = [{"foo": 1.0}, {"foo": 2.0}]

    with pytest.raises(RuntimeError, match="expected rollout batch to match"):
        _tensorize_requested_env_info(
            info_rows=info_rows,
            requested_keys={"foo"},
            batch_size=3,
            num_env_rows=2,
            agents_per_env=2,
            device=torch.device("cpu"),
        )


def test_tensorize_requested_env_info_broadcasts_per_env_rows_to_agents() -> None:
    info_rows = [{"foo": 1.0}, {"foo": 2.0}]

    env_info_td = _tensorize_requested_env_info(
        info_rows=info_rows,
        requested_keys={"foo"},
        batch_size=4,
        num_env_rows=2,
        agents_per_env=2,
        device=torch.device("cpu"),
    )

    torch.testing.assert_close(
        env_info_td["foo"],
        torch.tensor([1.0, 1.0, 2.0, 2.0], dtype=torch.float32),
    )


def test_tensorize_requested_env_info_raises_on_aggregated_single_row_for_multi_env_batch() -> None:
    info_rows = [{"foo": 1.5}]

    with pytest.raises(RuntimeError, match="single aggregated info row"):
        _tensorize_requested_env_info(
            info_rows=info_rows,
            requested_keys={"foo"},
            batch_size=4,
            num_env_rows=2,
            agents_per_env=2,
            device=torch.device("cpu"),
        )


def test_tensorize_requested_env_info_supports_agent_keys() -> None:
    info_rows = [
        {"_per_agent_infos": [{"held": 1.0}, {"held": 2.0}]},
        {"_per_agent_infos": [{"held": 3.0}, {"held": 4.0}]},
    ]

    env_info_td = _tensorize_requested_env_info(
        info_rows=info_rows,
        requested_keys={"agent/held"},
        batch_size=4,
        num_env_rows=2,
        agents_per_env=2,
        device=torch.device("cpu"),
    )

    torch.testing.assert_close(
        env_info_td["agent/held"],
        torch.tensor([1.0, 2.0, 3.0, 4.0], dtype=torch.float32),
    )


def test_tensorize_requested_env_info_supports_agent_keys_dict_payload() -> None:
    info_rows = [
        {"_per_agent_infos": {"0": {"held": 1.0}, "1": {"held": 2.0}}},
        {"_per_agent_infos": {"0": {"held": 3.0}, "1": {"held": 4.0}}},
    ]

    env_info_td = _tensorize_requested_env_info(
        info_rows=info_rows,
        requested_keys={"agent/held"},
        batch_size=4,
        num_env_rows=2,
        agents_per_env=2,
        device=torch.device("cpu"),
    )

    torch.testing.assert_close(
        env_info_td["agent/held"],
        torch.tensor([1.0, 2.0, 3.0, 4.0], dtype=torch.float32),
    )


def test_tensorize_requested_env_info_supports_env_prefix_alias() -> None:
    info_rows = [{"collective": {"cogs": {"aligned.junction.held": 1.25}}}]

    env_info_td = _tensorize_requested_env_info(
        info_rows=info_rows,
        requested_keys={"env_collective/cogs/aligned.junction.held"},
        batch_size=1,
        num_env_rows=1,
        agents_per_env=1,
        device=torch.device("cpu"),
    )

    torch.testing.assert_close(
        env_info_td["env_collective/cogs/aligned.junction.held"],
        torch.tensor([1.25], dtype=torch.float32),
    )


def test_tensorize_requested_env_info_raises_when_agent_rows_missing() -> None:
    info_rows = [{"foo": 1.0}, {"foo": 2.0}]

    with pytest.raises(RuntimeError, match="_per_agent_infos"):
        _tensorize_requested_env_info(
            info_rows=info_rows,
            requested_keys={"agent/held"},
            batch_size=4,
            num_env_rows=2,
            agents_per_env=2,
            device=torch.device("cpu"),
        )


def test_tensorize_requested_env_info_single_agent_reads_embedded_agent_rows() -> None:
    info_rows = [{"_per_agent_infos": [{"reward_step": 1.5}]}]

    env_info_td = _tensorize_requested_env_info(
        info_rows=info_rows,
        requested_keys={"agent/reward_step"},
        batch_size=1,
        num_env_rows=1,
        agents_per_env=1,
        device=torch.device("cpu"),
    )

    torch.testing.assert_close(
        env_info_td["agent/reward_step"],
        torch.tensor([1.5], dtype=torch.float32),
    )
