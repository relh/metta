# Generate a replay file that can be used in MettaScope to visualize a single run.

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

from pydantic import Field

from metta.common.tool import Tool
from metta.common.wandb.context import WandbConfig
from metta.sim.runner import apply_lineup_overrides, run_simulations
from metta.sim.simulation_config import SimulationConfig
from metta.tools.utils.auto_config import auto_replay_dir, auto_wandb_config

logger = logging.getLogger(__name__)


class ReplayTool(Tool):
    """Tool for generating and viewing replay files in MettaScope.
    Creates a simulation specifically to generate replay files and automatically
    opens them in the Nim MettaScope application for visualization. This tool focuses
    on replay viewing, unlike EvaluateTool which focuses on policy evaluation."""

    wandb: WandbConfig = auto_wandb_config()
    sim: SimulationConfig
    # Empty/None means "null agent" (MockAgent), matching the old `policy_uri=None` semantics.
    # If you want random actions, pass `policy_uris=["metta://policy/random"]`.
    # Back-compat: single-policy override for CLI usage (`policy_uri=...`). Prefer `policy_uris` going forward.
    policy_uri: str | None = None
    policy_uris: list[str] | None = None
    assignments: list[int] | None = None
    proportions: list[float] | None = None
    shuffle_assignments: bool = True
    replay_dir: str = Field(default_factory=auto_replay_dir)
    open_browser_on_start: bool = True
    launch_viewer: bool = True

    def invoke(self, args: dict[str, str]) -> Optional[int]:
        if self.policy_uri and self.policy_uris:
            raise ValueError("Specify only one of policy_uri or policy_uris")
        policy_uris = list(self.policy_uris) if self.policy_uris else ([self.policy_uri] if self.policy_uri else [])
        if not policy_uris:
            # Must resolve inside the isolated episode-runner policy-server venv, which only
            # guarantees `mettagrid` is installed (not `metta`). Use a registered mettagrid
            # mock policy for "null agent" semantics.
            policy_uris = ["mock://noop"]

        simulation_run = self.sim.to_simulation_run_config()
        apply_lineup_overrides(
            simulation_run,
            assignments=self.assignments,
            proportions=self.proportions,
            shuffle_assignments=self.shuffle_assignments,
        )

        simulation_results = run_simulations(
            policy_uris=policy_uris,
            simulations=[simulation_run],
            replay_dir=self.replay_dir,
            seed=self.system.seed,
        )

        result = simulation_results[0]
        replay_url = result.results.episodes[0].replay_path
        if not replay_url:
            logger.error("No replay path found in simulation results", exc_info=True)
            return 1

        if self.launch_viewer:
            launch_mettascope(replay_url)
        else:
            # For CI/non-visualization, just confirm replays were generated
            logger.info("Replay generation completed (viewer launch skipped)")

        return 0


def launch_mettascope(replay_url: str) -> None:
    """Launch the Nim MettaScope application with the given replay file."""
    if replay_url.startswith("http"):
        logger.error("HTTP replay URLs are not supported with the Nim MettaScope. Use file:// URLs instead.")
        return

    # Get the clean file path
    replay_path = replay_url.removeprefix("file://")
    if replay_path.startswith("./"):
        replay_path = replay_path.removeprefix("./")
    else:
        # If the path url is fully qualified, we want to remove the cwd prefix
        replay_path = replay_path.removeprefix(os.getcwd())

    # Find the mettascope source directory
    project_root = Path(__file__).resolve().parent.parent.parent
    mettascope_src = project_root / "packages" / "mettagrid" / "nim" / "mettascope" / "src" / "mettascope.nim"

    if not mettascope_src.exists():
        logger.error(f"MettaScope source not found at {mettascope_src}")
        return

    # Launch mettascope with the replay file
    try:
        logger.info(f"Launching MettaScope with replay: {replay_path}")
        cmd = ["nim", "r", "-d:fidgetUseFigma", str(mettascope_src), "--replay=./" + replay_path]
        subprocess.run(cmd, cwd=project_root, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to launch MettaScope: {e}")
    except FileNotFoundError:
        logger.error("Nim compiler not found. Please ensure Nim is installed and in PATH.")
