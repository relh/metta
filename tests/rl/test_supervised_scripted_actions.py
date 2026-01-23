from __future__ import annotations

from types import SimpleNamespace

import torch
from tensordict import TensorDict
from torchrl.data import Composite, UnboundedDiscrete

from cogames.cli.mission import get_mission
from metta.agent.policy import Policy
from metta.rl.loss.action_supervised import ActionSupervised, ActionSupervisedConfig
from metta.rl.training.experience import Experience
from mettagrid.envs.mettagrid_puffer_env import MettaGridPufferEnv
from mettagrid.policy.loader import discover_and_register_policies
from mettagrid.policy.policy import PolicySpec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Simulator

discover_and_register_policies("cogames.policy")


class ConstantActionPolicy(Policy):
    def __init__(self, policy_env_info: PolicyEnvInterface) -> None:
        super().__init__(policy_env_info)
        self._device = torch.device("cpu")
        self.action_value = min(1, int(policy_env_info.action_space.n) - 1)
        self._obs_shape = torch.Size(policy_env_info.observation_space.shape)

    def forward(self, td: TensorDict, action: torch.Tensor | None = None) -> TensorDict:  # noqa: D401
        env_obs = td["env_obs"]
        num_agents = env_obs.shape[0]
        td["actions"] = torch.full(
            (num_agents,),
            self.action_value,
            dtype=torch.int32,
            device=env_obs.device,
        )
        return td

    def get_agent_experience_spec(self) -> Composite:  # noqa: D401
        return Composite(
            env_obs=UnboundedDiscrete(shape=self._obs_shape, dtype=torch.uint8),
            dones=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.float32),
            truncateds=UnboundedDiscrete(shape=torch.Size([]), dtype=torch.float32),
        )

    @property
    def device(self) -> torch.device:
        return self._device

    def reset_memory(self) -> None:
        return None


def test_supervised_loss_uses_scripted_teacher_actions() -> None:
    _, env_cfg, _ = get_mission("evals.diagnostic_chest_navigation1", variants_arg=None, cogs=2)
    env_cfg.game.max_steps = 2

    simulator = Simulator()
    env = MettaGridPufferEnv(
        simulator,
        env_cfg,
        supervisor_policy_spec=PolicySpec(class_path="noop"),
    )
    try:
        observations, _ = env.reset(seed=123)
        teacher_actions = torch.as_tensor(env.teacher_actions.copy(), dtype=torch.long)

        policy_env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)
        policy = ConstantActionPolicy(policy_env_info)

        loss_cfg = ActionSupervisedConfig(enabled=True, teacher_led_proportion=1.0)
        loss = ActionSupervised(
            policy,
            SimpleNamespace(),
            SimpleNamespace(),
            torch.device("cpu"),
            "supervisor",
            loss_cfg,
        )

        num_agents = env_cfg.game.num_agents
        experience = Experience.from_losses(
            total_agents=num_agents,
            batch_size=num_agents,
            bptt_horizon=1,
            minibatch_size=1,
            max_minibatch_size=1,
            policy_experience_spec=policy.get_agent_experience_spec(),
            losses={"supervisor": loss},
            device="cpu",
            sampling_config=SimpleNamespace(method="sequential", prio_alpha=0.0, prio_beta0=0.0),
        )

        td = TensorDict(
            {
                "env_obs": torch.as_tensor(observations, dtype=torch.uint8),
                "rewards": torch.zeros(num_agents, dtype=torch.float32),
                "dones": torch.zeros(num_agents, dtype=torch.float32),
                "truncateds": torch.zeros(num_agents, dtype=torch.float32),
                "teacher_actions": teacher_actions,
                "reward_baseline": torch.zeros(num_agents, dtype=torch.float32),
            },
            batch_size=[num_agents],
        )

        context = SimpleNamespace(training_env_id=slice(0, num_agents))
        loss.run_rollout(td, context)

        assert td["teacher_mask"].all()
        assert torch.equal(td["actions"], teacher_actions.to(dtype=td["actions"].dtype))

        stored = experience.buffer["teacher_actions"][:num_agents, 0]
        assert torch.equal(stored, teacher_actions)

        if not torch.all(teacher_actions == policy.action_value):
            assert not torch.all(td["actions"] == policy.action_value)
    finally:
        env.close()
