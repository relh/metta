from types import SimpleNamespace

import pytest
import torch
from tensordict import TensorDict

from metta.rl.loss.diff_horde import DiffHordeLossConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from metta.rl.training.trajectory_isolation import TrajectoryIsolationSliceConfig

try:
    from gymnasium import spaces as gym_spaces
except ImportError:  # pragma: no cover
    from gym import spaces as gym_spaces  # type: ignore[no-redef]


class _PolicyRegistry:
    def __init__(self, policy: torch.nn.Module) -> None:
        self._policy = policy

    def get(self, name: str) -> torch.nn.Module:
        _ = name
        return self._policy


class _ToyPolicy(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.gtd_aux = torch.nn.Linear(3, 3)


def _make_context(registry: _PolicyRegistry) -> SimpleNamespace:
    return SimpleNamespace(
        current_slice_cfg=TrajectoryIsolationSliceConfig(
            name="default",
            env_ratio=1.0,
            policies=["learner0"],
            primary_policy="learner0",
        ),
        experience=SimpleNamespace(total_agents=8),
        state=SimpleNamespace(avg_reward=torch.full((8,), torch.nan, dtype=torch.float32)),
        policy_assets=registry,
    )


def test_diff_horde_loss_rollout_and_train() -> None:
    policy = _ToyPolicy()
    registry = _PolicyRegistry(policy)
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(4))
    cfg = DiffHordeLossConfig(
        cumulants=[{"kind": "td_key", "name": "core3", "key": "core", "slice": "0:3"}],
        beta=0.0,
        psi_all_actions_key=None,
        h_all_actions_key=None,
    )
    loss = cfg.create(registry, SimpleNamespace(), env, torch.device("cpu"), "diff_horde")
    context = _make_context(registry)

    rollout_td = TensorDict(
        {
            "learner0": TensorDict(
                {
                    "agent_slot_ids": torch.tensor([[1], [3]], dtype=torch.long),
                    "actions": torch.tensor([0, 2], dtype=torch.int32),
                    "core": torch.tensor([[0.5, 1.0, -0.5], [0.3, -0.2, 0.7]], dtype=torch.float32),
                },
                batch_size=[2],
            )
        },
        batch_size=[2],
    )
    loss.rollout_postprocess(rollout_td, context)
    learner_td = rollout_td["learner0"]
    assert learner_td["cumulants"].shape == (2, 3)
    assert learner_td["cumulants_phi_bar"].shape == (2, 3)
    torch.testing.assert_close(learner_td["cumulants_phi_bar"], learner_td["cumulants"])
    assert loss.phi_bar_agentF.shape == (8, 3)

    b, t, f = 2, 4, 3
    minibatch = TensorDict(
        {
            "actions": torch.tensor([[0, 1, 2, 1], [1, 2, 0, 3]], dtype=torch.int32),
            "dones": torch.zeros((b, t), dtype=torch.float32),
            "truncateds": torch.zeros((b, t), dtype=torch.float32),
            "act_log_prob": torch.zeros((b, t), dtype=torch.float32),
            "cumulants": torch.randn((b, t, f), dtype=torch.float32),
            "cumulants_phi_bar": torch.zeros((b, t, f), dtype=torch.float32),
        },
        batch_size=[b, t],
    )
    policy_td = TensorDict(
        {
            "horde_psi": torch.randn((b, t, f), dtype=torch.float32, requires_grad=True),
            "horde_h": torch.randn((b, t, f), dtype=torch.float32, requires_grad=True),
            "act_log_prob": torch.zeros((b, t), dtype=torch.float32),
        },
        batch_size=[b, t],
    )
    shared = TensorDict({"sampled_mb": minibatch, "policy_td": policy_td}, batch_size=[])
    train_loss, _, _ = loss.train(shared, context, mb_idx=0)
    assert torch.isfinite(train_loss)


def test_diff_horde_requires_policy_log_probs_for_rho_correction() -> None:
    policy = _ToyPolicy()
    registry = _PolicyRegistry(policy)
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(4))
    cfg = DiffHordeLossConfig(
        cumulants=[{"kind": "td_key", "name": "core3", "key": "core", "slice": "0:3"}],
        beta=0.0,
        psi_all_actions_key=None,
        h_all_actions_key=None,
    )
    loss = cfg.create(registry, SimpleNamespace(), env, torch.device("cpu"), "diff_horde")
    context = _make_context(registry)

    b, t, f = 2, 4, 3
    minibatch = TensorDict(
        {
            "actions": torch.tensor([[0, 1, 2, 1], [1, 2, 0, 3]], dtype=torch.int32),
            "dones": torch.zeros((b, t), dtype=torch.float32),
            "truncateds": torch.zeros((b, t), dtype=torch.float32),
            "act_log_prob": torch.zeros((b, t), dtype=torch.float32),
            "cumulants": torch.randn((b, t, f), dtype=torch.float32),
            "cumulants_phi_bar": torch.zeros((b, t, f), dtype=torch.float32),
        },
        batch_size=[b, t],
    )
    policy_td = TensorDict(
        {
            "horde_psi": torch.randn((b, t, f), dtype=torch.float32, requires_grad=True),
            "horde_h": torch.randn((b, t, f), dtype=torch.float32, requires_grad=True),
        },
        batch_size=[b, t],
    )
    shared = TensorDict({"sampled_mb": minibatch, "policy_td": policy_td}, batch_size=[])

    with pytest.raises(RuntimeError, match="policy_td\\['act_log_prob'\\]"):
        loss.train(shared, context, mb_idx=0)


def test_ppo_critic_rollout_updates_internal_reward_baseline() -> None:
    policy = _ToyPolicy()
    registry = _PolicyRegistry(policy)
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(4))
    cfg = PPOCriticConfig(critic_update="gtd_lambda")
    loss = cfg.create(registry, SimpleNamespace(), env, torch.device("cpu"), "ppo_critic")
    context = _make_context(registry)

    rollout_td = TensorDict(
        {
            "learner0": TensorDict(
                {
                    "agent_slot_ids": torch.tensor([[0], [2]], dtype=torch.long),
                    "rewards": torch.tensor([2.0, -1.0], dtype=torch.float32),
                    "reward_baseline": torch.tensor([99.0, 99.0], dtype=torch.float32),
                },
                batch_size=[2],
            )
        },
        batch_size=[2],
    )
    loss.rollout_postprocess(rollout_td, context)

    baseline = rollout_td["learner0"]["reward_baseline"]
    assert torch.allclose(baseline, torch.tensor([2.0, -1.0], dtype=torch.float32))
    assert loss.reward_phi_bar_agentF.shape == (8, 1)
    assert float(loss.reward_phi_bar_agentF[0, 0].item()) > 0.0
    assert bool(torch.isnan(context.state.avg_reward).all())


def test_ppo_critic_rollout_resyncs_baseline_from_context_state() -> None:
    policy = _ToyPolicy()
    registry = _PolicyRegistry(policy)
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(4))
    cfg = PPOCriticConfig(critic_update="gtd_lambda")
    loss = cfg.create(registry, SimpleNamespace(), env, torch.device("cpu"), "ppo_critic")
    context = _make_context(registry)

    first_td = TensorDict(
        {
            "learner0": TensorDict(
                {
                    "agent_slot_ids": torch.tensor([[0]], dtype=torch.long),
                    "rewards": torch.tensor([2.0], dtype=torch.float32),
                    "reward_baseline": torch.tensor([99.0], dtype=torch.float32),
                },
                batch_size=[1],
            )
        },
        batch_size=[1],
    )
    loss.rollout_postprocess(first_td, context)
    assert float(loss.reward_phi_bar_agentF[0, 0].item()) > 0.0

    # Simulate rollout gating elsewhere that updates canonical trainer state but skips PPOCritic.
    context.state.avg_reward[0] = 5.0

    second_td = TensorDict(
        {
            "learner0": TensorDict(
                {
                    "agent_slot_ids": torch.tensor([[0]], dtype=torch.long),
                    "rewards": torch.tensor([1.0], dtype=torch.float32),
                    "reward_baseline": torch.tensor([0.0], dtype=torch.float32),
                },
                batch_size=[1],
            )
        },
        batch_size=[1],
    )
    loss.rollout_postprocess(second_td, context)

    torch.testing.assert_close(
        second_td["learner0"]["reward_baseline"],
        torch.tensor([5.0], dtype=torch.float32),
    )
