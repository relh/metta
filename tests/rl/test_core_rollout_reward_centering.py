from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import torch
from tensordict import TensorDict

from metta.rl.training.core import CoreTrainingLoop


class _FakeExperience:
    def __init__(self) -> None:
        self.total_agents = 2
        self.accumulate_minibatches = 1
        self._range_tensor = torch.arange(self.total_agents, dtype=torch.long)
        self.row_slot_ids = torch.arange(self.total_agents, dtype=torch.long)
        self.t_in_row = torch.zeros(self.total_agents, dtype=torch.long)
        self.buffer = TensorDict({}, batch_size=[self.total_agents, 1], device=torch.device("cpu"))
        self.store_keys: list[str] = []
        self.ready_for_training = False
        self.full_rows = 0
        self.stored_td: TensorDict | None = None

    def reset_for_rollout(self) -> None:
        self.ready_for_training = False
        self.stored_td = None

    def store(self, data_td: TensorDict, env_id: slice) -> None:
        _ = env_id
        self.stored_td = data_td.clone()
        self.ready_for_training = True


class _FakeTrajectoryIsolator:
    def __init__(self, *, reward_delta: float = 0.0) -> None:
        runtime_slice = SimpleNamespace(
            name="default",
            env_mask=torch.tensor([True, True], dtype=torch.bool),
            cfg=SimpleNamespace(
                advantage=SimpleNamespace(
                    reward_centering=SimpleNamespace(beta=0.5),
                )
            ),
        )
        self.slice_plan = [runtime_slice]
        self.training_phase_primary_policy_slices = {"learner0": [runtime_slice]}
        self._reward_delta = float(reward_delta)
        self._rollout_td: TensorDict | None = None

    def on_rollout_start(self) -> None:
        return

    def prepare_rollout_slices(self, rollout_td: TensorDict) -> None:
        self._rollout_td = rollout_td

    def build_rollout_policy_batches(self) -> list[Any]:
        return []

    def apply_rollout_policy_batch(self, batch: Any) -> None:
        _ = batch

    def finalize_rollout_slices(self) -> None:
        if self._reward_delta != 0.0 and self._rollout_td is not None:
            self._rollout_td["rewards"] = self._rollout_td["rewards"] + self._reward_delta

    def writeback_rollout_tds(self, rollout_td: TensorDict) -> None:
        rollout_td["actions"] = torch.zeros((rollout_td.batch_size[0],), dtype=torch.int64, device=rollout_td.device)


class _FakeEnv:
    def __init__(self) -> None:
        self.policy_env_info = SimpleNamespace(num_agents=2)
        self.sent_actions: list[Any] = []

    def get_observations(self):
        obs = torch.zeros((2, 1, 3), dtype=torch.uint8)
        rewards = torch.tensor([1.0, 3.0], dtype=torch.float32)
        dones = torch.zeros((2,), dtype=torch.bool)
        truncateds = torch.zeros((2,), dtype=torch.bool)
        teacher_actions = torch.zeros((2,), dtype=torch.int64)
        info: list[dict[str, Any]] = []
        training_env_id = slice(0, 2)
        extra = None
        num_steps = 2
        return obs, rewards, dones, truncateds, teacher_actions, info, training_env_id, extra, num_steps

    def send_actions(self, actions: Any) -> None:
        self.sent_actions.append(actions)


def test_rollout_phase_updates_avg_reward_without_ppo_critic_loss() -> None:
    experience = _FakeExperience()
    trajectory_isolator = _FakeTrajectoryIsolator()
    env = _FakeEnv()
    context = SimpleNamespace(
        state=SimpleNamespace(avg_reward=torch.tensor([10.0, 20.0], dtype=torch.float32)),
        stopwatch=lambda _name: nullcontext(),
        training_env_id=None,
        policy_assets=SimpleNamespace(policies={}, get=lambda _name: None),
    )

    loop = CoreTrainingLoop(
        experience=experience,
        losses={},
        device=torch.device("cpu"),
        context=context,
        trajectory_isolator=trajectory_isolator,
    )
    loop.rollout_phase(env, context)

    assert experience.stored_td is not None
    assert torch.allclose(
        experience.stored_td["reward_baseline"],
        torch.tensor([10.0, 20.0], dtype=torch.float32),
    )
    assert torch.allclose(
        context.state.avg_reward,
        torch.tensor([5.5, 11.5], dtype=torch.float32),
    )


def test_rollout_phase_initializes_reward_baseline_from_first_observation() -> None:
    experience = _FakeExperience()
    trajectory_isolator = _FakeTrajectoryIsolator()
    env = _FakeEnv()
    context = SimpleNamespace(
        state=SimpleNamespace(avg_reward=torch.full((2,), torch.nan, dtype=torch.float32)),
        stopwatch=lambda _name: nullcontext(),
        training_env_id=None,
        policy_assets=SimpleNamespace(policies={}, get=lambda _name: None),
    )

    loop = CoreTrainingLoop(
        experience=experience,
        losses={},
        device=torch.device("cpu"),
        context=context,
        trajectory_isolator=trajectory_isolator,
    )
    loop.rollout_phase(env, context)

    assert experience.stored_td is not None
    torch.testing.assert_close(
        experience.stored_td["reward_baseline"],
        torch.tensor([1.0, 3.0], dtype=torch.float32),
    )
    torch.testing.assert_close(
        context.state.avg_reward,
        torch.tensor([1.0, 3.0], dtype=torch.float32),
    )


def test_rollout_phase_uses_finalized_rewards_for_baseline_and_ema() -> None:
    experience = _FakeExperience()
    trajectory_isolator = _FakeTrajectoryIsolator(reward_delta=10.0)
    env = _FakeEnv()
    context = SimpleNamespace(
        state=SimpleNamespace(avg_reward=torch.full((2,), torch.nan, dtype=torch.float32)),
        stopwatch=lambda _name: nullcontext(),
        training_env_id=None,
        policy_assets=SimpleNamespace(policies={}, get=lambda _name: None),
    )

    loop = CoreTrainingLoop(
        experience=experience,
        losses={},
        device=torch.device("cpu"),
        context=context,
        trajectory_isolator=trajectory_isolator,
    )
    loop.rollout_phase(env, context)

    assert experience.stored_td is not None
    # Baseline init should match finalized (post-processed) rewards, not raw env rewards.
    torch.testing.assert_close(
        experience.stored_td["reward_baseline"],
        torch.tensor([11.0, 13.0], dtype=torch.float32),
    )
    torch.testing.assert_close(
        context.state.avg_reward,
        torch.tensor([11.0, 13.0], dtype=torch.float32),
    )
