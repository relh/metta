from metta.common.util.fs import get_repo_root


def test_checks_workflow_treats_training_compat_version_as_relevant_change() -> None:
    workflow = (get_repo_root() / ".github/workflows/checks.yml").read_text()
    assert "'TRAINING_COMPAT_VERSION'" in workflow


def test_training_compat_reminder_workflow_anchors_cross_compat_guidance() -> None:
    workflow = (get_repo_root() / ".github/workflows/training-compat-version-reminder.yml").read_text()

    assert "TRAINING_COMPAT_VERSION" in workflow
    assert "common/src/metta/common/training_compat.py" in workflow
    assert "devops/stable/stable_tool_check_registry.py" in workflow
    assert "COMPAT_VERSION" in workflow
    assert "metta/rl/**" in workflow
    assert "packages/cogames/src/**" in workflow
    assert "packages/mettagrid/python/src/**" in workflow
    assert "packages/mettagrid/cpp/**" in workflow
