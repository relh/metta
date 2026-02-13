import torch

from mettagrid.policy.loader import initialize_or_load_policy
from mettagrid.policy.policy import PolicySpec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from recipes.experiment import cogsguard


def test_puffer_default_policy_forward_eval_updates_state() -> None:
    env_cfg = cogsguard.make_env(num_agents=2, max_steps=10)
    env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)

    policy = initialize_or_load_policy(
        env_info,
        PolicySpec(class_path="puffer", data_path=None),
        device_override="cpu",
    )
    net = policy.network()
    assert net is not None

    obs = torch.zeros((2, *env_info.observation_shape), dtype=torch.uint8)
    state = {"lstm_h": torch.zeros((2, 256)), "lstm_c": torch.zeros((2, 256))}

    logits, values = net.forward_eval(obs, state)  # type: ignore[call-arg]
    assert logits.shape == (2, len(env_info.action_names))
    assert values.shape == (2, 1)
    assert state["lstm_h"] is not None
    assert state["lstm_c"] is not None
    assert state["lstm_h"].shape == (2, 256)
    assert state["lstm_c"].shape == (2, 256)
