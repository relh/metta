from metta.rl.training.teacher import TeacherConfig
from recipes.experiment import cogsguard


def test_cogsguard_default_teacher_accepts_cli_overrides() -> None:
    teacher_override = TeacherConfig.model_validate({"policy_uri": "metta://policy/buggy"})
    tool = cogsguard.train(teacher=teacher_override)

    assert tool.training_env.supervisor_policy_uri == "metta://policy/buggy"
    assert tool.scheduler is not None
    assert any(gate.loss_instance_name == "supervisor" for gate in tool.scheduler.run_gates)
    assert tool.trainer.losses.supervisor.teacher_led_proportion == 0.0


def test_teacher_ppo_begin_step_adds_ppo_train_run_gates() -> None:
    teacher_override = TeacherConfig.model_validate({"policy_uri": "metta://policy/buggy", "ppo_begin_step": 123})
    tool = cogsguard.train(teacher=teacher_override)

    assert tool.scheduler is not None
    ppo_gates = [
        gate
        for gate in tool.scheduler.run_gates
        if gate.loss_instance_name in {"ppo_actor", "ppo_critic"} and gate.phase == "train"
    ]
    assert {gate.loss_instance_name for gate in ppo_gates} == {"ppo_actor", "ppo_critic"}
    assert all(gate.begin_at_step == 123 for gate in ppo_gates)


def test_cogsguard_diff_horde_wires_loss_architecture_and_slice() -> None:
    tool = cogsguard.train(
        diff_horde_cumulants={
            "junction_held": {"kind": "info_scalar", "key": "env_collective/cogs/aligned.junction.held"},
            "core2": {"kind": "td_key", "key": "core", "slice": "0:2"},
        }
    )

    learner_arch = tool.policy_assets["learner0"].architecture
    assert learner_arch is not None
    assert hasattr(learner_arch, "horde_num_cumulants")
    assert learner_arch.horde_num_cumulants == 3

    diff_horde_cfg = tool.trainer.losses["diff_horde"]
    assert diff_horde_cfg.cumulants.num_cumulants == 3
    assert "diff_horde" in tool.trajectory_isolation.slices[0].losses


def test_cogsguard_diff_horde_td_key_auto_sizes_from_policy_output() -> None:
    tool = cogsguard.train(diff_horde_cumulants={"hidden_all": {"kind": "td_key", "key": "actor_hidden"}})

    learner_arch = tool.policy_assets["learner0"].architecture
    assert learner_arch is not None
    assert hasattr(learner_arch, "horde_num_cumulants")
    assert hasattr(learner_arch, "actor_hidden")
    assert learner_arch.horde_num_cumulants == learner_arch.actor_hidden

    diff_horde_cfg = tool.trainer.losses["diff_horde"]
    assert diff_horde_cfg.cumulants.num_cumulants == learner_arch.actor_hidden


def test_cogsguard_diff_horde_defaults_to_ppo_slice_for_sliced_teacher() -> None:
    teacher_override = TeacherConfig.model_validate(
        {"policy_uri": "metta://policy/buggy", "mode": "scripted.supervisor.sliced"}
    )
    tool = cogsguard.train(
        teacher=teacher_override,
        diff_horde_cumulants={"core2": {"kind": "td_key", "key": "core", "slice": "0:2"}},
    )

    slice_names = [slice_cfg.name for slice_cfg in tool.trajectory_isolation.slices]
    assert "ppo" in slice_names
    ppo_slice = next(slice_cfg for slice_cfg in tool.trajectory_isolation.slices if slice_cfg.name == "ppo")
    assert "diff_horde" in ppo_slice.losses


def test_cogsguard_diff_horde_added_to_sliced_teacher_led_and_student_slices() -> None:
    teacher_override = TeacherConfig.model_validate(
        {
            "policy_uri": "metta://policy/buggy",
            "mode": "scripted.supervisor.sliced",
            "teacher_led_proportion": 0.2,
            "student_led_proportion": 0.2,
        }
    )
    tool = cogsguard.train(
        teacher=teacher_override,
        diff_horde_cumulants={"core2": {"kind": "td_key", "key": "core", "slice": "0:2"}},
    )

    ppo_slice = next(slice_cfg for slice_cfg in tool.trajectory_isolation.slices if slice_cfg.name == "ppo")
    teacher_slice = next(slice_cfg for slice_cfg in tool.trajectory_isolation.slices if slice_cfg.name == "teacher_led")
    student_slice = next(slice_cfg for slice_cfg in tool.trajectory_isolation.slices if slice_cfg.name == "student_led")
    assert "diff_horde" in ppo_slice.losses
    assert "diff_horde" in teacher_slice.losses
    assert "diff_horde" in student_slice.losses
