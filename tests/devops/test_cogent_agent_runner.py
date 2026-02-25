from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_agent_runner() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "devops" / "cogent" / "agent-runner.py"
    spec = importlib.util.spec_from_file_location("cogent_agent_runner", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_read_content_uses_cogents_prompt_directory(tmp_path: Path, monkeypatch) -> None:
    module = _load_agent_runner()
    cogents_dir = tmp_path / "cogents"
    prompt_path = cogents_dir / "prompts" / "launch-neophyte.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("launch bot", encoding="utf-8")

    monkeypatch.setattr(module, "COGENTS_DIR", cogents_dir)
    monkeypatch.setattr(module, "PROMPT_DIR", cogents_dir / "prompts")

    content, label = module.read_content(skill=None, prompt="launch-neophyte.md")

    assert content == "launch bot"
    assert label == "prompt-launch-neophyte"


def test_build_competitor_command_has_neophyte_profile() -> None:
    module = _load_agent_runner()

    command = module.build_competitor_command(
        policy="metta://policy/role_py",
        policy_name="neophyte-test",
        season="beta-cvc",
        output_root="./artifacts/ai_researcher",
        cogames_bin="cogames",
        researcher_profile="neophyte",
    )

    assert command[:3] == [
        "uv",
        "run",
        "./packages/cogames-rl-researcher/scripts/run_ai_researcher_startup.py",
    ]
    assert "--policy-name" in command
    assert "neophyte-test" in command
    assert "--researcher-profile" in command
    assert command[command.index("--researcher-profile") + 1] == "neophyte"


def test_build_competitor_command_has_experienced_profile() -> None:
    module = _load_agent_runner()

    command = module.build_competitor_command(
        policy="metta://policy/role_py",
        policy_name="experienced-test",
        season="beta-cvc",
        output_root="./artifacts/ai_researcher",
        cogames_bin="cogames",
        researcher_profile="experienced",
    )

    assert "--policy-name" in command
    assert "experienced-test" in command
    assert "--researcher-profile" in command
    assert command[command.index("--researcher-profile") + 1] == "experienced"
