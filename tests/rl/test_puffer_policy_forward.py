from typing import Protocol

import pytest
import torch
import torch._dynamo
from tensordict import TensorDict

from metta.agent.policies.puffer_default import PufferDefaultConfig
from metta.agent.policies.puffer_lstm import PufferLSTMConfig
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from recipes.experiment import cogsguard


class _PolicyConfig(Protocol):
    def make_policy(self, policy_env_info: PolicyEnvInterface) -> object: ...


def _make_metadata(*, batch_size: int, bptt_horizon: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    total = batch_size * bptt_horizon
    batch = torch.full((total,), batch_size, dtype=torch.long, device=device)
    bptt = torch.full((total,), bptt_horizon, dtype=torch.long, device=device)
    return batch, bptt


@pytest.mark.parametrize(
    ("policy_config", "training_tt"),
    [
        pytest.param(PufferDefaultConfig(hidden_size=64), 4, id="puffer_default"),
        pytest.param(PufferLSTMConfig(hidden_size=64, num_layers=1), 3, id="puffer_lstm"),
    ],
)
def test_puffer_policy_forward_rollout_and_training(policy_config: _PolicyConfig, training_tt: int) -> None:
    # Torch compile can fail on some macOS dev setups; for unit tests we just
    # need to verify shapes/keys, so allow Dynamo to fall back to eager.
    torch._dynamo.config.suppress_errors = True

    env_cfg = cogsguard.make_env(num_agents=8, max_steps=10)
    env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)

    policy = policy_config.make_policy(env_info)
    policy.initialize_to_environment(env_info, torch.device("cpu"))

    # TT == 1 rollout path
    batch_size = 4
    rollout_tt = 1
    device = torch.device("cpu")
    total = batch_size * rollout_tt
    batch, bptt = _make_metadata(batch_size=batch_size, bptt_horizon=rollout_tt, device=device)
    obs = torch.randint(0, 256, (total, *env_info.observation_shape), dtype=torch.uint8, device=device)
    td = TensorDict(
        {
            "env_obs": obs,
            "dones": torch.zeros((total,), dtype=torch.float32, device=device),
            "truncateds": torch.zeros((total,), dtype=torch.float32, device=device),
            "agent_slot_ids": torch.arange(batch_size, dtype=torch.long, device=device).view(batch_size, 1),
            "row_id": torch.arange(total, dtype=torch.long, device=device),
            "t_in_row": torch.zeros((total,), dtype=torch.long, device=device),
            "batch": batch,
            "bptt": bptt,
        },
        batch_size=[total],
        device=device,
    )

    rollout_out = policy(td)
    assert rollout_out["logits"].shape == (batch_size, int(env_info.action_space.n))
    assert rollout_out["values"].shape == (batch_size,)
    assert rollout_out["h_values"].shape == (batch_size,)
    assert rollout_out["actions"].shape == (batch_size,)
    assert rollout_out["act_log_prob"].shape == (batch_size,)

    # TT > 1 training path
    batch_size = 2
    total = batch_size * training_tt
    batch, bptt = _make_metadata(batch_size=batch_size, bptt_horizon=training_tt, device=device)
    obs_train = torch.randint(0, 256, (total, *env_info.observation_shape), dtype=torch.uint8, device=device)
    td_train = TensorDict(
        {
            "env_obs": obs_train,
            "dones": torch.zeros((total,), dtype=torch.float32, device=device),
            "truncateds": torch.zeros((total,), dtype=torch.float32, device=device),
            "agent_slot_ids": torch.zeros((total, 1), dtype=torch.long, device=device),
            "row_id": torch.arange(total, dtype=torch.long, device=device),
            "t_in_row": torch.zeros((total,), dtype=torch.long, device=device),
            "batch": batch,
            "bptt": bptt,
        },
        batch_size=[total],
        device=device,
    )
    actions = torch.zeros((total,), dtype=torch.long, device=device)
    train_out = policy(td_train, action=actions)
    assert train_out["logits"].shape == (total, int(env_info.action_space.n))
    assert train_out["values"].shape == (total,)
    assert train_out["h_values"].shape == (total,)
    assert train_out["act_log_prob"].shape == (total,)
    assert train_out["entropy"].shape == (total,)
