"""Test that a metta-trained checkpoint can be bundled for cogames submission."""

import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pytest

from cogames.cli.policy import PolicySpec
from cogames.cli.submit import create_submission_zip
from metta.agent.mocks import MockAgent, MockArchitecture
from metta.rl.checkpoint_manager import write_checkpoint_bundle
from mettagrid.config.mettagrid_config import MettaGridConfig
from mettagrid.policy.submission import POLICY_SPEC_FILENAME, SubmissionPolicySpec
from mettagrid.runner.episode_runner import run_episode_isolated
from mettagrid.runner.types import EpisodeSpec

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SCRIPT = Path("packages/cogames-agents/trained_setup_script.py")
AGENT_DIR = Path("agent")


@pytest.fixture
def checkpoint_dir(tmp_path: Path) -> Path:
    checkpoint = tmp_path / "test_run:v1"
    architecture = MockArchitecture()
    policy = MockAgent()
    write_checkpoint_bundle(
        checkpoint,
        architecture_spec=architecture.to_spec(),
        state_dict=policy.state_dict(),
    )
    return checkpoint


def _create_bundle_workdir(tmp_path: Path, checkpoint_dir: Path) -> Path:
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    shutil.copytree(checkpoint_dir, workdir / "checkpoint")
    shutil.copytree(REPO_ROOT / AGENT_DIR, workdir / AGENT_DIR, symlinks=True)
    setup_dest = workdir / SETUP_SCRIPT
    setup_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / SETUP_SCRIPT, setup_dest)
    return workdir


def _create_bundle_zip(workdir: Path, checkpoint_dir: Path) -> Path:
    spec_path = checkpoint_dir / POLICY_SPEC_FILENAME
    submission_spec = SubmissionPolicySpec.model_validate_json(spec_path.read_text())
    assert submission_spec.data_path is not None

    policy_spec = PolicySpec(
        class_path=submission_spec.class_path,
        data_path=str(Path("checkpoint") / submission_spec.data_path),
        init_kwargs=submission_spec.init_kwargs,
    )

    include_paths = [
        Path("checkpoint") / submission_spec.data_path,
        SETUP_SCRIPT,
        AGENT_DIR,
    ]
    validated = [p for p in include_paths if (workdir / p).exists()]

    old_cwd = os.getcwd()
    os.chdir(workdir)
    try:
        return create_submission_zip(validated, policy_spec, setup_script=str(SETUP_SCRIPT))
    finally:
        os.chdir(old_cwd)


def test_trained_agent_bundle_structure(tmp_path: Path, checkpoint_dir: Path):
    """Bundle zip contains agent/, setup script, weights, and correct policy_spec."""
    workdir = _create_bundle_workdir(tmp_path, checkpoint_dir)
    zip_path = _create_bundle_zip(workdir, checkpoint_dir)

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

        assert POLICY_SPEC_FILENAME in names
        spec_data = json.loads(zf.read(POLICY_SPEC_FILENAME))
        assert spec_data["class_path"] == "metta.agent.policy.CheckpointPolicy"
        assert spec_data["setup_script"] == str(SETUP_SCRIPT)

        agent_files = [n for n in names if n.startswith("agent/")]
        assert len(agent_files) > 0, "agent/ directory missing from bundle"
        assert any("pyproject.toml" in f for f in agent_files), "agent/pyproject.toml missing"
        assert any("policy.py" in f for f in agent_files), "agent policy.py missing"
        assert any("utils.py" in f for f in agent_files), "agent utils.py missing"

        setup_files = [n for n in names if "trained_setup_script.py" in n]
        assert len(setup_files) > 0, "setup script missing from bundle"

        weight_files = [n for n in names if n.endswith("weights.safetensors")]
        assert len(weight_files) > 0, "weights file missing from bundle"

    zip_path.unlink()


def test_trained_agent_bundle_validates(tmp_path: Path, checkpoint_dir: Path):
    """Bundle loads and runs in an isolated policy server."""
    workdir = _create_bundle_workdir(tmp_path, checkpoint_dir)
    zip_path = _create_bundle_zip(workdir, checkpoint_dir)

    env_cfg = MettaGridConfig()
    env_cfg.game.max_steps = 10
    spec = EpisodeSpec(
        policy_uris=[zip_path.as_uri()],
        assignments=[0] * env_cfg.game.num_agents,
        env=env_cfg,
        seed=42,
        max_action_time_ms=10000,
    )

    with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as results_file:
        result = run_episode_isolated(spec, Path(results_file.name))
        assert result.steps > 0

    zip_path.unlink()
