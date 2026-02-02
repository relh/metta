from metta.rl.training.teacher import TeacherConfig
from recipes.experiment import cogsguard


def test_cogsguard_default_teacher_accepts_cli_overrides() -> None:
    teacher_override = TeacherConfig.model_validate({"policy_uri": "metta://policy/buggy"})
    tool = cogsguard.train(use_default_teacher=True, teacher=teacher_override)

    assert tool.training_env.supervisor_policy_uri == "metta://policy/buggy"
    assert tool.scheduler is not None
    assert any(gate.loss_instance_name == "supervisor" for gate in tool.scheduler.run_gates)
    assert tool.trainer.losses.supervisor.enabled is True
    assert tool.trainer.losses.supervisor.teacher_led_proportion == 0.0
