import torch
import torch._dynamo
from tensordict import TensorDict

from metta.agent.policies.puffer_lstm import PufferLSTMConfig
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from recipes.experiment import cogsguard


def test_puffer_lstm_policy_forward_rollout_and_training() -> None:
    torch._dynamo.config.suppress_errors = True

    env_cfg = cogsguard.make_env(num_agents=8, max_steps=10)
    env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)

    cfg = PufferLSTMConfig(hidden_size=64, num_layers=1)
    policy = cfg.make_policy(env_info)
    policy.initialize_to_environment(env_info, torch.device("cpu"))

    # TT == 1 rollout path
    B = 4
    TT = 1
    device = torch.device("cpu")
    total = B * TT
    obs = torch.randint(0, 256, (total, *env_info.observation_shape), dtype=torch.uint8, device=device)
    td = TensorDict(
        {
            "env_obs": obs,
            "dones": torch.zeros((total,), dtype=torch.float32, device=device),
            "truncateds": torch.zeros((total,), dtype=torch.float32, device=device),
            "agent_slot_ids": torch.arange(B, dtype=torch.long, device=device).view(B, 1),
            "row_id": torch.arange(total, dtype=torch.long, device=device),
            "t_in_row": torch.zeros((total,), dtype=torch.long, device=device),
            "batch": torch.full((total,), B, dtype=torch.long, device=device),
            "bptt": torch.full((total,), TT, dtype=torch.long, device=device),
        },
        batch_size=[total],
        device=device,
    )
    out = policy.forward(td)
    assert out["logits"].shape == (B, int(env_info.action_space.n))
    assert out["values"].shape == (B,)
    assert out["h_values"].shape == (B,)
    assert out["actions"].shape == (B,)
    assert out["act_log_prob"].shape == (B,)

    # TT > 1 training path
    B = 2
    TT = 3
    total = B * TT
    obs2 = torch.randint(0, 256, (total, *env_info.observation_shape), dtype=torch.uint8, device=device)
    td2 = TensorDict(
        {
            "env_obs": obs2,
            "dones": torch.zeros((total,), dtype=torch.float32, device=device),
            "truncateds": torch.zeros((total,), dtype=torch.float32, device=device),
            "agent_slot_ids": torch.zeros((total, 1), dtype=torch.long, device=device),
            "row_id": torch.arange(total, dtype=torch.long, device=device),
            "t_in_row": torch.zeros((total,), dtype=torch.long, device=device),
            "batch": torch.full((total,), B, dtype=torch.long, device=device),
            "bptt": torch.full((total,), TT, dtype=torch.long, device=device),
        },
        batch_size=[total],
        device=device,
    )
    actions = torch.zeros((total,), dtype=torch.long, device=device)
    out2 = policy.forward(td2, action=actions)
    assert out2["logits"].shape == (total, int(env_info.action_space.n))
    assert out2["values"].shape == (total,)
    assert out2["h_values"].shape == (total,)
    assert out2["act_log_prob"].shape == (total,)
    assert out2["entropy"].shape == (total,)
