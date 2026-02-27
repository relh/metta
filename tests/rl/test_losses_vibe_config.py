from metta.rl.loss.losses import LossesConfig
from metta.rl.training.trajectory_isolation import default_trajectory_isolation_config
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


def _policy_env_info(vibe_action_names: list[str]) -> PolicyEnvInterface:
    return PolicyEnvInterface(
        obs_features=[],
        tags=[],
        action_names=["noop", "move_north"],
        vibe_action_names=vibe_action_names,
        num_agents=1,
        observation_shape=(1, 1),
        egocentric_shape=(1, 1),
    )


def test_losses_config_wires_vibe_actor_for_split_action_env() -> None:
    losses = LossesConfig()
    trajectory_isolation = default_trajectory_isolation_config()

    losses.configure_for_policy_env(
        policy_env_info=_policy_env_info(["change_vibe_default", "change_vibe_junction"]),
        trajectory_isolation=trajectory_isolation,
    )

    assert "ppo_vibe_actor" in losses.losses
    assert losses["ppo_actor"].loss_coef == 0.5
    assert "vibe_actions" in losses["ppo_actor"].extra_action_keys

    vibe_actor = losses["ppo_vibe_actor"]
    assert vibe_actor.actor_name == "vibe"
    assert vibe_actor.log_prob_key == "vibe_act_log_prob"
    assert vibe_actor.entropy_key == "vibe_entropy"
    assert vibe_actor.loss_coef == 0.5
    assert "vibe_actions" in vibe_actor.extra_action_keys

    default_slice = trajectory_isolation.slices[0]
    assert default_slice.losses == ["ppo_actor", "ppo_vibe_actor", "ppo_critic"]


def test_losses_config_prunes_vibe_actor_for_non_split_env_and_restores_primary_weight() -> None:
    losses = LossesConfig()
    trajectory_isolation = default_trajectory_isolation_config()

    losses.configure_for_policy_env(
        policy_env_info=_policy_env_info(["change_vibe_default"]),
        trajectory_isolation=trajectory_isolation,
    )
    losses.configure_for_policy_env(
        policy_env_info=_policy_env_info([]),
        trajectory_isolation=trajectory_isolation,
    )

    assert "ppo_vibe_actor" not in losses.losses
    assert losses["ppo_actor"].loss_coef == 1.0
    assert "vibe_actions" not in losses["ppo_actor"].extra_action_keys

    default_slice = trajectory_isolation.slices[0]
    assert default_slice.losses == ["ppo_actor", "ppo_critic"]


def test_losses_config_vibe_wiring_is_idempotent() -> None:
    losses = LossesConfig()
    trajectory_isolation = default_trajectory_isolation_config()
    policy_env_info = _policy_env_info(["change_vibe_default"])

    losses.configure_for_policy_env(policy_env_info=policy_env_info, trajectory_isolation=trajectory_isolation)
    losses.configure_for_policy_env(policy_env_info=policy_env_info, trajectory_isolation=trajectory_isolation)

    assert losses["ppo_actor"].loss_coef == 0.5
    assert list(name for name in losses.losses if name == "ppo_vibe_actor") == ["ppo_vibe_actor"]
    default_slice = trajectory_isolation.slices[0]
    assert default_slice.losses.count("ppo_vibe_actor") == 1
