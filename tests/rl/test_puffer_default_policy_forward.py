import torch
from tensordict import TensorDict

from metta.agent.policies.puffer_default import PufferDefaultConfig
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from recipes.experiment import cogsguard


def _make_metadata(*, B: int, TT: int, device: torch.device) -> tuple[torch.Tensor, torch.Tensor]:
    total = B * TT
    batch = torch.full((total,), B, dtype=torch.long, device=device)
    bptt = torch.full((total,), TT, dtype=torch.long, device=device)
    return batch, bptt


def test_puffer_default_policy_forward_rollout_and_training() -> None:
    # Torch compile can fail on some macOS dev setups; for unit tests we just
    # need to verify shapes/keys, so allow Dynamo to fall back to eager.
    import torch._dynamo  # noqa: PLC0415

    torch._dynamo.config.suppress_errors = True

    env_cfg = cogsguard.make_env(num_agents=8, max_steps=10)
    env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)

    cfg = PufferDefaultConfig(hidden_size=64)
    policy = cfg.make_policy(env_info)
    policy.initialize_to_environment(env_info, torch.device("cpu"))

    B = 4
    TT = 1
    device = torch.device("cpu")
    batch, bptt = _make_metadata(B=B, TT=TT, device=device)
    obs = torch.randint(0, 256, (B, *env_info.observation_shape), dtype=torch.uint8, device=device)
    td = TensorDict(
        {
            "env_obs": obs,
            "dones": torch.zeros((B,), dtype=torch.float32, device=device),
            "truncateds": torch.zeros((B,), dtype=torch.float32, device=device),
            "agent_slot_ids": torch.arange(B, dtype=torch.long, device=device).view(B, 1),
            "row_id": torch.arange(B, dtype=torch.long, device=device),
            "t_in_row": torch.zeros((B,), dtype=torch.long, device=device),
            "batch": batch,
            "bptt": bptt,
        },
        batch_size=[B],
        device=device,
    )

    out = policy(td)
    assert out["logits"].shape == (B, int(env_info.action_space.n))
    assert out["values"].shape == (B,)
    assert out["h_values"].shape == (B,)
    assert out["actions"].shape == (B,)
    assert out["act_log_prob"].shape == (B,)

    # Training path (TT>1) should accept flattened actions and produce entropy/log-prob tensors.
    B = 2
    TT = 4
    total = B * TT
    batch, bptt = _make_metadata(B=B, TT=TT, device=device)
    obs = torch.randint(0, 256, (total, *env_info.observation_shape), dtype=torch.uint8, device=device)
    td_train = TensorDict(
        {
            "env_obs": obs,
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
    out_train = policy(td_train, action=actions)
    assert out_train["logits"].shape == (total, int(env_info.action_space.n))
    assert out_train["values"].shape == (total,)
    assert out_train["h_values"].shape == (total,)
    assert out_train["act_log_prob"].shape == (total,)
    assert out_train["entropy"].shape == (total,)
