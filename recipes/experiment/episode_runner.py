import subprocess

from metta.common.tool import Tool


class EpisodeRunnerTool(Tool):
    source: str
    output_dir: str | None = None
    mode: str = "local-image"

    def invoke(self, args: dict[str, str]) -> int:
        cmd = ["metta", "observatory", "run-episode", self.source, "-m", self.mode]
        if self.output_dir:
            cmd.extend(["-o", self.output_dir])
        return subprocess.run(cmd, check=True).returncode


def repro(source: str, output_dir: str | None = None, mode: str = "local-image") -> Tool:
    """
    ./tools/run.py recipes.experiment.episode_runner.repro source=<uuid-or-path-to-job.json>

    Modes: local-image (default), local, prod-image
    """
    return EpisodeRunnerTool(source=source, output_dir=output_dir, mode=mode)
