import json
import os
import subprocess
import sys
import tempfile
import uuid

from metta_alo.rollout import PureSingleEpisodeJob

from cogames.cogs_vs_clips.missions import make_cogsguard_mission
from metta.app_backend.clients.base_client import get_machine_token
from metta.app_backend.clients.stats_client import StatsClient
from metta.common.tool import Tool
from metta.tools.utils.auto_config import auto_stats_server_uri


class PureSingleEpisodeTool(Tool):
    job: PureSingleEpisodeJob

    def invoke(self, args: dict[str, str]) -> int:
        with tempfile.NamedTemporaryFile(delete=True) as temp_file:
            temp_file.write(
                json.dumps({"job": self.job.model_dump(), "device": "cpu", "allow_network": True}).encode("utf-8")
            )
            temp_file.flush()
            subprocess.run([sys.executable, "-m", "metta_alo.rollout", temp_file.name], check=True)
        return 0


def run_example(
    policy_uris: list[str] | str,
    results_uri: str,
    replay_uri: str,
    assignments: list[int] | None = None,
    debug_dir: str | None = None,
) -> PureSingleEpisodeTool:
    """
    ./tools/run.py recipes.experiment.pure_single_episode.run_example \
        policy_uris=metta://policy/dinky:v15 \
        results_uri=file://./results.json \
        replay_uri=file://./replay.json.z \
        debug_dir=./trace_output

    # Multiple policies with round-robin assignment:
    ./tools/run.py recipes.experiment.pure_single_episode.run_example \
        policy_uris='["metta://policy/dinky:v15", "metta://policy/other:v1"]' \
        results_uri=file://./results.json \
        replay_uri=file://./replay.json.z

    # Explicit assignments (agent 0,1 use policy 0; agent 2,3 use policy 1):
    ./tools/run.py recipes.experiment.pure_single_episode.run_example \
        policy_uris='["metta://policy/a:v1", "metta://policy/b:v1"]' \
        assignments='[0, 0, 1, 1]' \
        results_uri=file://./results.json \
        replay_uri=file://./replay.json.z
    """
    # Normalize single policy to list
    if isinstance(policy_uris, str):
        policy_uris = [policy_uris]

    # Determine num_agents: from assignments if provided, else one per policy
    if assignments is not None:
        num_agents = len(assignments)
    else:
        num_agents = len(policy_uris)
        assignments = list(range(num_agents))  # agent i uses policy i

    mission = make_cogsguard_mission(num_agents=num_agents)
    env = mission.make_env()

    return PureSingleEpisodeTool(
        job=PureSingleEpisodeJob(
            policy_uris=policy_uris,
            assignments=assignments,
            env=env,
            results_uri=results_uri,
            replay_uri=replay_uri,
            debug_dir=debug_dir,
        )
    )


class SingleEpisodeTool(Tool):
    stats_server_uri: str | None = auto_stats_server_uri()
    job_id: uuid.UUID

    def invoke(self, args: dict[str, str]) -> int:
        if not self.stats_server_uri:
            raise ValueError("Stats server URI is not set")
        machine_token = get_machine_token(self.stats_server_uri)
        StatsClient(backend_url=self.stats_server_uri, machine_token=machine_token or "")._validate_authenticated()

        env = os.environ.copy()
        env["BACKEND_URL"] = self.stats_server_uri
        env["MACHINE_TOKEN"] = machine_token or ""
        subprocess.run([sys.executable, "-m", "metta.sim.single_episode_runner", str(self.job_id)], check=True, env=env)
        return 0


def run_single_episode_example(job_id: str) -> SingleEpisodeTool:
    """
    ./tools/run.py recipes.experiment.pure_single_episode.run_single_episode_example job_id=my-uuid
    """
    return SingleEpisodeTool(job_id=uuid.UUID(job_id))
