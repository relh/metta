from __future__ import annotations

import pytest
from cortex.config import RoutedAdapterConfig

from metta.agent.policies.cnn_shared_critic import CnnSharedCriticConfig
from metta.agent.policies.default import DefaultPolicyConfig
from metta.rl.training.teacher import TeacherConfig
from recipes.experiment import cogsguard_marlbro as marlbro


def test_marlbro_route_slot_ids_support_shared_policy() -> None:
    shared_architecture = DefaultPolicyConfig(cortex_routed_adapter=RoutedAdapterConfig(num_slots=8, rank=2))
    tool = marlbro.build_two_policy_role_train_tool(
        policy_architecture=shared_architecture,
        slice_configs=(
            marlbro.MarlbroSliceConfig(
                name="miner_slice",
                agent_range=(0, 4),
                policy_name="shared_policy",
                loss_suffix="miner",
                route_slot_ids=(0, 1, 2, 3),
            ),
            marlbro.MarlbroSliceConfig(
                name="aligner_slice",
                agent_range=(4, 8),
                policy_name="shared_policy",
                loss_suffix="aligner",
                route_slot_ids=(4, 5, 6, 7),
            ),
        ),
    )

    assert set(tool.policy_assets) == {"shared_policy"}
    slices = {slice_cfg.name: slice_cfg for slice_cfg in tool.trajectory_isolation.slices}
    assert slices["miner_slice"].route_slot_ids == (0, 1, 2, 3)
    assert slices["aligner_slice"].route_slot_ids == (4, 5, 6, 7)


def test_marlbro_routed_adapter_param_enables_default_architecture() -> None:
    tool = marlbro.build_two_policy_role_train_tool(
        routed_adapter={"enabled": True},
        slice_configs=(
            marlbro.MarlbroSliceConfig(
                name="miner_slice",
                agent_range=(0, 4),
                policy_name="miner_policy",
                loss_suffix="miner",
                route_slot_ids=(0, 1, 2, 3),
            ),
            marlbro.MarlbroSliceConfig(
                name="aligner_slice",
                agent_range=(4, 8),
                policy_name="aligner_policy",
                loss_suffix="aligner",
                route_slot_ids=(4, 5, 6, 7),
            ),
        ),
    )

    miner_architecture = tool.policy_assets["miner_policy"].architecture
    aligner_architecture = tool.policy_assets["aligner_policy"].architecture
    assert isinstance(miner_architecture, CnnSharedCriticConfig)
    assert isinstance(aligner_architecture, CnnSharedCriticConfig)
    assert miner_architecture.cortex_routed_adapter is not None
    assert aligner_architecture.cortex_routed_adapter is not None
    assert miner_architecture.cortex_routed_adapter.enabled
    assert aligner_architecture.cortex_routed_adapter.enabled
    assert miner_architecture.cortex_routed_adapter.num_slots == 8
    assert aligner_architecture.cortex_routed_adapter.num_slots == 8


def test_marlbro_train_uses_shared_policy_with_routed_adapter() -> None:
    tool = marlbro.train(routed_adapter={"enabled": True})
    assert set(tool.policy_assets) == {"shared_policy"}
    shared_architecture = tool.policy_assets["shared_policy"].architecture
    assert isinstance(shared_architecture, CnnSharedCriticConfig)
    assert shared_architecture.cortex_routed_adapter is not None
    assert shared_architecture.cortex_routed_adapter.enabled
    assert shared_architecture.cortex_routed_adapter.num_slots == 8
    slices = {slice_cfg.name: slice_cfg for slice_cfg in tool.trajectory_isolation.slices}
    assert slices["miner_slice"].policies == ["shared_policy"]
    assert slices["aligner_slice"].policies == ["shared_policy"]
    assert slices["miner_slice"].route_slot_ids == (0, 1, 2, 3)
    assert slices["aligner_slice"].route_slot_ids == (4, 5, 6, 7)


def test_marlbro_train_keeps_separate_policies_without_routed_adapter() -> None:
    tool = marlbro.train()
    assert set(tool.policy_assets) == {"miner_policy", "aligner_policy"}
    assert tool.scheduler is None
    assert tool.training_env.supervisor_policy_uri is None
    slices = {slice_cfg.name: slice_cfg for slice_cfg in tool.trajectory_isolation.slices}
    assert slices["miner_slice"].policies == ["miner_policy"]
    assert slices["aligner_slice"].policies == ["aligner_policy"]
    assert slices["miner_slice"].route_slot_ids is None
    assert slices["aligner_slice"].route_slot_ids is None
    assert slices["miner_slice"].losses == ["ppo_actor_miner", "ppo_critic_miner"]
    assert slices["aligner_slice"].losses == ["ppo_actor_aligner", "ppo_critic_aligner"]
    assert isinstance(tool.policy_assets["miner_policy"].architecture, CnnSharedCriticConfig)
    assert isinstance(tool.policy_assets["aligner_policy"].architecture, CnnSharedCriticConfig)
    assert tool.policy_assets["miner_policy"].architecture.cortex_routed_adapter is None
    assert tool.policy_assets["aligner_policy"].architecture.cortex_routed_adapter is None


def test_marlbro_route_slot_ids_require_routed_adapter() -> None:
    with pytest.raises(ValueError, match="cortex_routed_adapter"):
        marlbro.build_two_policy_role_train_tool(
            slice_configs=(
                marlbro.MarlbroSliceConfig(
                    name="miner_slice",
                    agent_range=(0, 4),
                    policy_name="miner_policy",
                    loss_suffix="miner",
                    route_slot_ids=(0, 1, 2, 3),
                ),
                marlbro.MarlbroSliceConfig(
                    name="aligner_slice",
                    agent_range=(4, 8),
                    policy_name="aligner_policy",
                    loss_suffix="aligner",
                    route_slot_ids=(4, 5, 6, 7),
                ),
            )
        )


def test_marlbro_supports_teacher_per_slice() -> None:
    tool = marlbro.build_two_policy_role_train_tool(
        slice_configs=(
            marlbro.MarlbroSliceConfig(
                name="miner_slice",
                agent_range=(0, 4),
                policy_name="miner_policy",
                loss_suffix="miner",
                teacher=TeacherConfig(policy_uri="metta://policy/miner_teacher", mode="learned.kickstarter.mixed"),
            ),
            marlbro.MarlbroSliceConfig(
                name="aligner_slice",
                agent_range=(4, 8),
                policy_name="aligner_policy",
                loss_suffix="aligner",
                teacher=TeacherConfig(policy_uri="metta://policy/aligner_teacher", mode="learned.kickstarter.mixed"),
            ),
        )
    )

    assert tool.scheduler is not None
    assert tool.trainer.losses.has_loss("miner_slice_kickstarter")
    assert tool.trainer.losses.has_loss("aligner_slice_kickstarter")
    assert "miner_slice_teacher" in tool.policy_assets
    assert "aligner_slice_teacher" in tool.policy_assets

    slices = {slice_cfg.name: slice_cfg for slice_cfg in tool.trajectory_isolation.slices}
    assert "miner_slice_kickstarter" in slices["miner_slice"].losses
    assert "aligner_slice_kickstarter" in slices["aligner_slice"].losses
    assert "miner_slice_teacher" in slices["miner_slice"].policies
    assert "aligner_slice_teacher" in slices["aligner_slice"].policies


def test_marlbro_supports_top_level_scripted_teacher() -> None:
    tool = marlbro.train(
        teacher={
            "policy_uri": "metta://policy/nlanky",
            "mode": "scripted.supervisor.mixed",
        }
    )

    assert tool.training_env.supervisor_policy_uri == "metta://policy/nlanky"
    assert tool.scheduler is not None
    assert tool.trainer.losses.has_loss("miner_slice_supervisor")
    assert tool.trainer.losses.has_loss("aligner_slice_supervisor")
    slices = {slice_cfg.name: slice_cfg for slice_cfg in tool.trajectory_isolation.slices}
    assert "miner_slice_supervisor" in slices["miner_slice"].losses
    assert "aligner_slice_supervisor" in slices["aligner_slice"].losses


def test_marlbro_routed_adapter_with_scripted_teacher_wires_both_slices() -> None:
    tool = marlbro.train(
        routed_adapter={"enabled": True},
        teacher={
            "policy_uri": "metta://policy/nlanky",
            "mode": "scripted.supervisor.mixed",
        },
    )
    assert set(tool.policy_assets) == {"shared_policy"}
    assert tool.training_env.supervisor_policy_uri == "metta://policy/nlanky"
    assert tool.scheduler is not None
    assert tool.trainer.losses.has_loss("miner_slice_supervisor")
    assert tool.trainer.losses.has_loss("aligner_slice_supervisor")
    slices = {slice_cfg.name: slice_cfg for slice_cfg in tool.trajectory_isolation.slices}
    assert slices["miner_slice"].policies == ["shared_policy"]
    assert slices["aligner_slice"].policies == ["shared_policy"]
    assert slices["miner_slice"].route_slot_ids == (0, 1, 2, 3)
    assert slices["aligner_slice"].route_slot_ids == (4, 5, 6, 7)
    assert "miner_slice_supervisor" in slices["miner_slice"].losses
    assert "aligner_slice_supervisor" in slices["aligner_slice"].losses


def test_marlbro_rejects_combined_top_level_and_slice_teachers() -> None:
    with pytest.raises(ValueError, match="Cannot combine top-level teacher with slice-level teachers"):
        marlbro.build_two_policy_role_train_tool(
            teacher=TeacherConfig(policy_uri="metta://policy/nlanky", mode="scripted.supervisor.mixed"),
            slice_configs=(
                marlbro.MarlbroSliceConfig(
                    name="miner_slice",
                    agent_range=(0, 4),
                    policy_name="miner_policy",
                    loss_suffix="miner",
                    teacher=TeacherConfig(policy_uri="metta://policy/miner_teacher", mode="learned.kickstarter.mixed"),
                ),
                marlbro.MarlbroSliceConfig(
                    name="aligner_slice",
                    agent_range=(4, 8),
                    policy_name="aligner_policy",
                    loss_suffix="aligner",
                ),
            ),
        )


def test_marlbro_teacher_ppo_begin_step_gates_slice_critic_losses() -> None:
    ppo_begin_step = 123
    tool = marlbro.train(
        teacher={
            "policy_uri": "metta://policy/nlanky",
            "mode": "scripted.supervisor.mixed",
            "ppo_begin_step": ppo_begin_step,
        }
    )

    assert tool.scheduler is not None
    ppo_begin_train_gates = [
        gate for gate in tool.scheduler.run_gates if gate.phase == "train" and gate.begin_at_step == ppo_begin_step
    ]
    gate_loss_names = {gate.loss_instance_name for gate in ppo_begin_train_gates}
    assert {"ppo_actor_miner", "ppo_actor_aligner", "ppo_critic_miner", "ppo_critic_aligner"} <= gate_loss_names


def test_marlbro_rejects_top_level_sliced_teacher_mode() -> None:
    with pytest.raises(ValueError, match="unsupported for marlbro; use mixed mode"):
        marlbro.train(
            teacher={
                "policy_uri": "metta://policy/nlanky",
                "mode": "scripted.supervisor.sliced",
            }
        )
