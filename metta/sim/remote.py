from typing import Sequence

from pydantic import BaseModel, ConfigDict

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.queries.eval_task_queries import EvalTaskRow
from metta.app_backend.routes.eval_task_routes import TaskCreateRequest
from metta.sim.runner import SimulationRunConfig


class RemoteEvalTaskData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulations: Sequence[SimulationRunConfig]
    policy_uris: list[str]


def evaluate_remotely(
    simulations: Sequence[SimulationRunConfig],
    policy_uris: Sequence[str],
    stats_client: StatsClient,
    git_hash: str | None = None,
    push_metrics_to_wandb: bool = True,
) -> EvalTaskRow:
    if not policy_uris:
        raise ValueError("policy_uris is required")

    command_parts = [
        "uv run tools/run.py recipes.experiment.remote_eval.eval",
        f"push_metrics_to_wandb={str(push_metrics_to_wandb).lower()}",
    ]
    command = " ".join(command_parts)
    request = TaskCreateRequest(
        command=command,
        data_file=RemoteEvalTaskData(simulations=simulations, policy_uris=list(policy_uris)).model_dump(mode="json"),
        git_hash=git_hash,
        attributes={"parallelism": len(simulations)},
    )
    return stats_client.create_eval_task(request)
