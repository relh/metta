import subprocess

from metta.common.tool import Tool


class EpisodeRunnerTool(Tool):
    source: str
    output_dir: str = "."
    mode: str = "local"

    def invoke(self, args: dict[str, str]) -> int:
        cmd = ["metta", "observatory", "run-episode", self.source, "-m", self.mode, "-o", self.output_dir]
        return subprocess.run(cmd, check=True).returncode


def repro(source: str, output_dir: str = ".", mode: str = "local") -> Tool:
    """
    ./tools/run.py recipes.experiment.episode_runner.repro source=<uuid-or-path-to-job.json>

    Modes: local (default), local-image, prod-image
    """
    return EpisodeRunnerTool(source=source, output_dir=output_dir, mode=mode)
