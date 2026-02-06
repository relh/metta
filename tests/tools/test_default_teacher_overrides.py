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
