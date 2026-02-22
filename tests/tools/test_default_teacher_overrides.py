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
        if gate.loss_instance_name in {"ppo_actor", "ppo_vibe_actor", "ppo_critic"} and gate.phase == "train"
    ]
    assert {gate.loss_instance_name for gate in ppo_gates} == {"ppo_actor", "ppo_vibe_actor", "ppo_critic"}
    assert all(gate.begin_at_step == 123 for gate in ppo_gates)


def test_cogsguard_diff_horde_wires_loss_architecture_and_slice() -> None:
    tool = cogsguard.train(
        diff_horde_cumulants={
            "territory_now": {"kind": "info_scalar", "key": "env_team/cogs/aligned.junction"},
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


def test_cogsguard_horde_variants_wire_diff_horde() -> None:
    tool = cogsguard.train(horde_variants=["junctions", "vitals"])

    learner_arch = tool.policy_assets["learner0"].architecture
    assert learner_arch is not None
    assert hasattr(learner_arch, "horde_num_cumulants")
    assert learner_arch.horde_num_cumulants == 6

    diff_horde_cfg = tool.trainer.losses["diff_horde"]
    assert diff_horde_cfg.cumulants.num_cumulants == 6
    assert diff_horde_cfg.cumulants.required_info_keys() >= {
        "env_team/cogs/aligned.junction",
        "env_team/clips/aligned.junction",
        "agent/hp.amount",
        "agent/energy.amount",
    }


def test_cogsguard_horde_variants_support_cortex_core_td_key() -> None:
    tool = cogsguard.train(horde_variants=["cortex_core"])

    learner_arch = tool.policy_assets["learner0"].architecture
    assert learner_arch is not None
    assert hasattr(learner_arch, "horde_num_cumulants")

    cumulants = tool.trainer.losses["diff_horde"].cumulants
    specs_by_name = {spec.name: spec for spec in cumulants.specs}
    assert "cortex_core" in specs_by_name
    assert specs_by_name["cortex_core"].kind == "td_key"
    assert specs_by_name["cortex_core"].key == "core"
    assert specs_by_name["cortex_core"].size == cumulants.num_cumulants
    assert learner_arch.horde_num_cumulants == cumulants.num_cumulants


def test_cogsguard_horde_variants_merge_with_explicit_cumulants() -> None:
    tool = cogsguard.train(
        horde_variants=["junctions"],
        diff_horde_cumulants={
            "cogs_junction_now": {"kind": "info_scalar", "key": "env_team/cogs/aligned.junction.held"},
            "core2": {"kind": "td_key", "key": "core", "slice": "0:2"},
        },
    )

    cumulants = tool.trainer.losses["diff_horde"].cumulants
    specs_by_name = {spec.name: spec for spec in cumulants.specs}

    assert "clips_junction_now" in specs_by_name
    assert "core2" in specs_by_name
    assert specs_by_name["cogs_junction_now"].key == "env_team/cogs/aligned.junction.held"
    assert cumulants.num_cumulants == 4
