from metta.common.util.fs import get_repo_root


def test_sandbox_train_skill_keeps_key_operational_caveats() -> None:
    skill = (get_repo_root() / "skills/tr.sandbox-train/SKILL.md").read_text()

    assert "bash -lc 'a && b && c'" in skill
    assert "pufferlib-core" in skill
    assert "evaluator.evaluate_local=false" in skill
    assert "separate local smoke or explicit eval command" in skill
