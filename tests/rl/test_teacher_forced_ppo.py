from types import SimpleNamespace

import pytest
import torch
from tensordict import TensorDict

from metta.rl.advantage import td_lambda_reverse_scan
from metta.rl.loss.kickstarter import Kickstarter, KickstarterConfig
from metta.rl.loss.logit_kickstarter import LogitKickstarter, LogitKickstarterConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from metta.rl.training.teacher import (
    TeacherConfig,
    _setup_trajectory_isolation,
    _wire_teacher_loss_into_mixed_slice,
)
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationSliceConfig,
    _pad_tensor_like,
    default_trajectory_isolation_config,
)

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


def _importance_sampled_delta_lambda(
    *,
    values: torch.Tensor,
    rewards: torch.Tensor,
    dones: torch.Tensor,
    rho: torch.Tensor,
    gamma: float,
    gae_lambda: float,
    rho_clip: float,
) -> torch.Tensor:
    _, tt = values.shape
    delta_lambda = torch.zeros_like(values)
    if tt <= 1:
        return delta_lambda
    terminal_next = dones[:, 1:]
    mask_next = 1.0 - terminal_next
    delta = rewards[:, 1:] + gamma * mask_next * values[:, 1:] - values[:, :-1]
    rho = rho[:, :-1].clamp(max=rho_clip)
    delta_lambda[:, :-1] = td_lambda_reverse_scan(rho * delta, rho * mask_next, float(gamma * gae_lambda))
    return delta_lambda


def _actor_losses(
    *,
    registry: _PolicyRegistry,
    env: SimpleNamespace,
) -> dict[str, object]:
    primary = PPOActorConfig().create(registry, SimpleNamespace(), env, torch.device("cpu"), "ppo_actor")
    vibe = PPOActorConfig(
        actor_name="vibe",
        log_prob_key="vibe_act_log_prob",
        entropy_key="vibe_entropy",
        importance_sampling_ratio_key=None,
        allow_global_ratio_fallback=False,
        replay_ratio_key="vibe_ratio",
    ).create(registry, SimpleNamespace(), env, torch.device("cpu"), "ppo_vibe_actor")
    return {"ppo_actor": primary, "ppo_vibe_actor": vibe}


def test_sliced_supervisor_runs_ppo_losses_on_teacher_slices() -> None:
    trajectory_isolation = default_trajectory_isolation_config()
    teacher_cfg = TeacherConfig(
        policy_uri="metta://policy/nlanky",
        mode="scripted.supervisor.sliced",
        teacher_led_proportion=0.2,
    )

    _setup_trajectory_isolation(
        trajectory_isolation=trajectory_isolation,
        family="supervisor",
        teacher_cfg=teacher_cfg,
        primary_policy_name="learner0",
        teacher_policy_name="teacher",
        ppo_loss_names=["ppo_critic", "ppo_actor"],
    )

    teacher_slice = next(slice_cfg for slice_cfg in trajectory_isolation.slices if slice_cfg.name == "teacher_led")
    assert "ppo_actor" in teacher_slice.losses
    assert "ppo_critic" in teacher_slice.losses


def test_mixed_supervisor_wires_supervisor_loss_into_default_slice() -> None:
    trajectory_isolation = default_trajectory_isolation_config()
    _wire_teacher_loss_into_mixed_slice(
        trajectory_isolation=trajectory_isolation,
        teacher_loss_names=["supervisor"],
        primary_policy_name="learner0",
        teacher_policy_name="teacher",
        include_teacher_policy=False,
    )
    assert "supervisor" in trajectory_isolation.slices[0].losses


def test_sliced_kickstarter_runs_ppo_losses_on_teacher_slices() -> None:
    trajectory_isolation = default_trajectory_isolation_config()
    teacher_cfg = TeacherConfig(
        policy_uri="file://./train_dir/some_run/checkpoints/some_run:v2",
        mode="learned.kickstarter.sliced",
        teacher_led_proportion=0.2,
    )

    _setup_trajectory_isolation(
        trajectory_isolation=trajectory_isolation,
        family="kickstarter",
        teacher_cfg=teacher_cfg,
        primary_policy_name="learner0",
        teacher_policy_name="teacher",
        ppo_loss_names=["ppo_critic", "ppo_actor"],
    )

    teacher_slice = next(slice_cfg for slice_cfg in trajectory_isolation.slices if slice_cfg.name == "teacher_led")
    assert "ppo_actor" in teacher_slice.losses
    assert "ppo_critic" in teacher_slice.losses
    assert teacher_slice.policies == ["learner0", "teacher"]


@pytest.mark.parametrize(
    ("instance_name", "loss_cls", "cfg_cls"),
    [
        ("kickstarter", Kickstarter, KickstarterConfig),
        ("logit_kickstarter", LogitKickstarter, LogitKickstarterConfig),
    ],
)
def test_teacher_forced_actions_record_behavior_logprob(
    instance_name: str,
    loss_cls: type[Kickstarter] | type[LogitKickstarter],
    cfg_cls: type[KickstarterConfig] | type[LogitKickstarterConfig],
) -> None:
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(5))
    registry = _PolicyRegistry(_ToyPolicy())
    loss = loss_cls(
        registry,
        SimpleNamespace(),
        env,
        torch.device("cpu"),
        instance_name,
        cfg_cls(teacher="teacher", teacher_led_proportion=1.0),
    )

    num_agents = 3
    teacher_actions = torch.tensor([2, 1, 4], dtype=torch.int32)
    teacher_act_log_prob = torch.tensor([-0.2, -1.2, -0.7], dtype=torch.float32)

    teacher_td = TensorDict(
        {
            "actions": teacher_actions,
            "act_log_prob": teacher_act_log_prob,
            "logits": torch.zeros((num_agents, 5), dtype=torch.float32),
            "values": torch.zeros((num_agents,), dtype=torch.float32),
        },
        batch_size=[num_agents],
    )
    student_td = TensorDict(
        {
            "actions": torch.zeros((num_agents,), dtype=torch.int32),
            "act_log_prob": torch.zeros((num_agents,), dtype=torch.float32),
        },
        batch_size=[num_agents],
    )
    td = TensorDict({"teacher": teacher_td, "learner0": student_td}, batch_size=[num_agents])
    context = SimpleNamespace(
        current_slice_cfg=TrajectoryIsolationSliceConfig(
            name="teacher_led",
            env_ratio=1.0,
            policies=["learner0", "teacher"],
            primary_policy="learner0",
        ),
        policy_assets=registry,
    )

    loss.rollout_postprocess(td, context)

    assert td["learner0"]["teacher_mask"].all()
    assert torch.equal(td["learner0"]["actions"], teacher_actions)
    torch.testing.assert_close(td["learner0"]["act_log_prob"], teacher_act_log_prob)


def test_ppo_critic_teacher_rho_uses_behavior_logprob() -> None:
    policy = _ToyPolicy()
    registry = _PolicyRegistry(policy)
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(4))
    cfg = PPOCriticConfig(critic_update="gtd_lambda", rho_clip=1.5)
    loss = cfg.create(registry, SimpleNamespace(), env, torch.device("cpu"), "ppo_critic")
    losses_for_context = _actor_losses(registry=registry, env=env)
    losses_for_context["ppo_critic"] = loss

    class _Replay:
        def update(self, *_args, **_kwargs) -> None:
            return None

    loss.attach_replay_buffer(_Replay())  # type: ignore[arg-type]

    b, t = 2, 4
    minibatch = TensorDict(
        {
            "values": torch.zeros((b, t), dtype=torch.float32),
            "rewards": torch.zeros((b, t), dtype=torch.float32),
            "reward_baseline": torch.zeros((b, t), dtype=torch.float32),
            "dones": torch.zeros((b, t), dtype=torch.float32),
            "truncateds": torch.zeros((b, t), dtype=torch.float32),
            "actions": torch.zeros((b, t), dtype=torch.int32),
            "act_log_prob": torch.tensor([[-0.26236426, -0.26236426, -0.26236426, -0.26236426], [0, 0, 0, 0]]),
            "vibe_act_log_prob": torch.tensor(
                [[-0.26236426, -0.26236426, -0.26236426, -0.26236426], [0, 0, 0, 0]], dtype=torch.float32
            ),
            "teacher_mask": torch.tensor([[1, 1, 1, 1], [0, 0, 0, 0]], dtype=torch.bool),
        },
        batch_size=[b, t],
    )
    policy_td = TensorDict(
        {
            "values": torch.zeros((b, t), dtype=torch.float32, requires_grad=True),
            "h_values": torch.zeros((b, t), dtype=torch.float32, requires_grad=True),
            "act_log_prob": torch.zeros((b, t), dtype=torch.float32),
            "vibe_act_log_prob": torch.zeros((b, t), dtype=torch.float32),
        },
        batch_size=[b, t],
    )

    context = SimpleNamespace(
        current_slice_cfg=TrajectoryIsolationSliceConfig(
            name="teacher_led",
            env_ratio=1.0,
            policies=["learner0"],
            primary_policy="learner0",
            losses=["ppo_actor", "ppo_vibe_actor", "ppo_critic"],
        ),
        policy_assets=registry,
        losses=losses_for_context,
    )
    shared = TensorDict(
        {
            "sampled_mb": minibatch,
            "policy_td": policy_td,
            "advantages_pg": torch.zeros((b, t), dtype=torch.float32),
            "indices": torch.zeros((b, 2), dtype=torch.long),
            "importance_sampling_ratio": (
                (policy_td["act_log_prob"] - minibatch["act_log_prob"])
                + (policy_td["vibe_act_log_prob"] - minibatch["vibe_act_log_prob"])
            ).exp(),
        },
        batch_size=[],
    )

    loss.train(shared, context, mb_idx=0)

    # Each actor head has rho ~= 1.3 (<1.5); combined rho ~= 1.69 (>1.5), so clipfrac confirms combination.
    assert loss.loss_tracker["teacher_td_lambda_rho_clipfrac"][-1] == 1.0


def test_ppo_critic_td_lambda_offpolicy_applies_to_student_slices() -> None:
    policy = _ToyPolicy()
    registry = _PolicyRegistry(policy)
    env = SimpleNamespace(single_action_space=gym_spaces.Discrete(4))
    cfg = PPOCriticConfig(critic_update="gtd_lambda", rho_clip=1.0)
    loss = cfg.create(registry, SimpleNamespace(), env, torch.device("cpu"), "ppo_critic")
    losses_for_context = _actor_losses(registry=registry, env=env)
    losses_for_context["ppo_critic"] = loss

    class _Replay:
        def update(self, *_args, **_kwargs) -> None:
            return None

    loss.attach_replay_buffer(_Replay())  # type: ignore[arg-type]

    b, t = 1, 4
    minibatch = TensorDict(
        {
            "values": torch.zeros((b, t), dtype=torch.float32),
            "rewards": torch.ones((b, t), dtype=torch.float32),
            "reward_baseline": torch.zeros((b, t), dtype=torch.float32),
            "dones": torch.zeros((b, t), dtype=torch.float32),
            "truncateds": torch.zeros((b, t), dtype=torch.float32),
            "actions": torch.zeros((b, t), dtype=torch.int32),
            "act_log_prob": torch.zeros((b, t), dtype=torch.float32),
            "vibe_act_log_prob": torch.zeros((b, t), dtype=torch.float32),
            "teacher_mask": torch.zeros((b, t), dtype=torch.bool),
        },
        batch_size=[b, t],
    )
    policy_td = TensorDict(
        {
            "values": torch.zeros((b, t), dtype=torch.float32, requires_grad=True),
            "h_values": torch.zeros((b, t), dtype=torch.float32, requires_grad=True),
            "act_log_prob": torch.full((b, t), -0.69314718056, dtype=torch.float32),
            "vibe_act_log_prob": torch.full((b, t), -0.69314718056, dtype=torch.float32),
        },
        batch_size=[b, t],
    )

    context = SimpleNamespace(
        current_slice_cfg=TrajectoryIsolationSliceConfig(
            name="student",
            env_ratio=1.0,
            policies=["learner0"],
            primary_policy="learner0",
            losses=["ppo_actor", "ppo_vibe_actor", "ppo_critic"],
        ),
        policy_assets=registry,
        losses=losses_for_context,
    )
    combined_logratio = (policy_td["act_log_prob"] - minibatch["act_log_prob"]) + (
        policy_td["vibe_act_log_prob"] - minibatch["vibe_act_log_prob"]
    )
    shared = TensorDict(
        {
            "sampled_mb": minibatch,
            "policy_td": policy_td,
            "advantages_pg": torch.zeros((b, t), dtype=torch.float32),
            "indices": torch.zeros((b, 2), dtype=torch.long),
            "importance_sampling_ratio": combined_logratio.exp(),
        },
        batch_size=[],
    )
    expected = _importance_sampled_delta_lambda(
        values=policy_td["values"].reshape((b, t)),
        rewards=minibatch["rewards"],
        dones=minibatch["dones"],
        rho=combined_logratio.exp(),
        gamma=float(context.current_slice_cfg.advantage.gamma),
        gae_lambda=float(context.current_slice_cfg.advantage.gae_lambda),
        rho_clip=float(cfg.rho_clip),
    )

    loss.train(shared, context, mb_idx=0)

    torch.testing.assert_close(shared["advantages_pg"], expected)


def test_pad_tensor_like_casts_dtype_to_rollout() -> None:
    slice_value = torch.zeros((2, 3), dtype=torch.int32)
    rollout_value = torch.zeros((2, 3), dtype=torch.long)
    padded = _pad_tensor_like(slice_value, rollout_value)
    assert padded.dtype == rollout_value.dtype
