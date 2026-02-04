"""Export PolicyEnvInterface to JSON for use with the policy server.

Usage:
    ./tools/run.py recipes.experiment.export_env_interface.export output_path=./env_interface.json
"""

from pathlib import Path

from cogames.cogs_vs_clips.missions import make_cogsguard_mission
from metta.common.tool import Tool
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class ExportEnvInterfaceTool(Tool):
    output_path: Path

    def invoke(self, args: dict[str, str]) -> int:
        env_cfg = make_cogsguard_mission().make_env()
        env_interface = PolicyEnvInterface.from_mg_cfg(env_cfg)
        self.output_path.write_text(env_interface.model_dump_json(indent=2))
        print(f"Wrote PolicyEnvInterface to {self.output_path}")
        return 0


def export(output_path: str) -> ExportEnvInterfaceTool:
    """Export CogsGuard PolicyEnvInterface to JSON."""
    return ExportEnvInterfaceTool(output_path=Path(output_path))
