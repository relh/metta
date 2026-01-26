import torch

from metta.agent.policies.fast import FastConfig
from metta.rl.torch_init import seed_everything_distributed_aware
from mettagrid.config.mettagrid_config import MettaGridConfig
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


def _build_policy_state(seed: int) -> tuple[str, dict[str, torch.Tensor]]:
    seed_everything_distributed_aware(seed)
    env_cfg = MettaGridConfig.EmptyRoom(num_agents=1, width=5, height=5, border_width=1, with_walls=True)
    env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)
    config = FastConfig()
    policy = config.make_policy(env_info)
    policy.initialize_to_environment(env_info, device=torch.device("cpu"))
    return config.to_spec(), {k: v.clone() for k, v in policy.state_dict().items()}


def test_seeded_policy_weights_and_config_match() -> None:
    spec_a, state_a = _build_policy_state(123)
    spec_b, state_b = _build_policy_state(123)

    assert spec_a == spec_b
    assert state_a.keys() == state_b.keys()
    for key in state_a:
        assert torch.equal(state_a[key], state_b[key]), f"Mismatch for parameter {key}"
