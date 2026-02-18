import contextlib
import logging
import math
import multiprocessing
from typing import Sequence
from urllib.parse import parse_qs, urlparse

from pydantic import Field

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.metta_scheme_resolver import MettaSchemeResolver
from metta.app_backend.routes.stats_routes import PolicyVersionRow
from metta.common.tool import Tool
from metta.common.tool.tool import ToolResult, ToolWithResult
from metta.common.wandb.context import WandbRunAppendContext
from metta.sim.handle_results import render_eval_summary
from metta.sim.runner import SimulationRunConfig, SimulationRunResult, apply_lineup_overrides
from metta.sim.simulate_and_record import (
    ObservatoryWriter,
    WandbWriter,
    simulate_and_record,
)
from metta.sim.simulation_config import SimulationConfig
from metta.tools.utils.auto_config import auto_replay_dir, auto_stats_server_uri, auto_wandb_config

logger = logging.getLogger(__name__)


def _policy_display_name_from_uri(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.query:
        qs = parse_qs(parsed.query)
        # Lightweight naming without changing the `policy_uris` list contract.
        for key in ("display_name", "name", "label"):
            vals = qs.get(key)
            if vals and vals[-1]:
                return vals[-1]

    base = uri.split("?", 1)[0]
    if "://" in base:
        path = urlparse(base).path.rstrip("/")
        if path:
            return path.rsplit("/", 1)[-1]
    return base


class EvaluateTool(Tool):
    simulations: Sequence[SimulationConfig] | Sequence[SimulationRunConfig]
    # Convenience for single-policy use (`policy_uri=...`). Use `policy_uris=[...]` for multi-policy.
    policy_uri: str | None = None
    policy_uris: list[str] = Field(
        default_factory=list,
        description="Policy URIs to evaluate. The first URI is the primary policy.",
    )
    assignments: list[int] | None = Field(
        default=None,
        description="Optional explicit policy index per agent for all simulations.",
    )
    proportions: list[float] | None = Field(
        default=None,
        description="Optional policy proportions for all simulations when assignments are omitted.",
    )
    shuffle_assignments: bool = Field(
        default=True,
        description="Shuffle policy assignments each episode when generated from proportions.",
    )

    replay_dir: str = Field(default_factory=auto_replay_dir)

    stats_server_uri: str | None = Field(default_factory=auto_stats_server_uri)
    verbose: bool = False
    push_metrics_to_wandb: bool = False
    max_workers: int | None = None

    def invoke(self, args: dict[str, str]) -> int:
        """CLI entrypoint via run_tool. Runs eval and returns success exit code."""
        self.run_eval()
        return 0

    def run_eval(self) -> list[SimulationRunResult]:
        if self.policy_uri and self.policy_uris:
            raise ValueError("Specify only one of policy_uri or policy_uris")
        policy_uris = list(self.policy_uris) if self.policy_uris else ([self.policy_uri] if self.policy_uri else [])
        if not policy_uris:
            raise ValueError("policy_uris is required (or set policy_uri for a single policy)")
        if self.assignments is not None and self.proportions is not None:
            raise ValueError("Specify only one of assignments or proportions")

        policy_names = [_policy_display_name_from_uri(uri) for uri in policy_uris]

        observatory_writer: ObservatoryWriter | None = None
        wandb_writer: WandbWriter | None = None
        wandb_context = contextlib.nullcontext(None)
        primary_policy_version: PolicyVersionRow | None = None

        stats_client: StatsClient | None = None
        if self.push_metrics_to_wandb or any(uri.startswith("metta://") for uri in policy_uris):
            if not self.stats_server_uri:
                raise ValueError("stats_server_uri is required when using metta:// policies or pushing metrics")
            stats_client = StatsClient.create(self.stats_server_uri)

        if stats_client:
            resolver = MettaSchemeResolver(self.stats_server_uri)
            policy_versions: list[PolicyVersionRow | None] = []
            for uri in policy_uris:
                if uri.startswith("metta://"):
                    try:
                        policy_versions.append(resolver.get_policy_version(uri))
                    except Exception:
                        policy_versions.append(None)
                else:
                    policy_versions.append(None)
        else:
            policy_versions = [None for _ in policy_uris]
        primary_policy_version = policy_versions[0]

        if primary_policy_version and stats_client:
            policy_version_ids = [str(pv.id) for pv in policy_versions if pv]
            if not all(policy_version_ids) or len(policy_version_ids) != len(policy_uris):
                raise ValueError("All policy URIs must specify a policy registered in the stats server")
            observatory_writer = ObservatoryWriter(
                stats_client=stats_client,
                policy_version_ids=policy_version_ids,
                primary_policy_version_id=str(primary_policy_version.id),
            )

        if self.push_metrics_to_wandb:
            if not primary_policy_version:
                raise ValueError(
                    "The first entry in policy_uris must specify a policy registered in the stats server in order for "
                    "metrics to be pushed to WandB; it's needed to find the wandb run to push stats to."
                )
            wandb_config = auto_wandb_config(primary_policy_version.name)
            wandb_context = WandbRunAppendContext(wandb_config)
            epoch = primary_policy_version.attributes.get("epoch")
            agent_step = primary_policy_version.attributes.get("agent_step")
            if epoch is None or agent_step is None:
                raise ValueError(
                    f"Cannot find the agent step or epoch associated with {primary_policy_version.name}. This is "
                    "needed to push metrics to WandB."
                )

        with wandb_context as wandb_run:
            if self.push_metrics_to_wandb:
                assert wandb_run is not None and epoch is not None and agent_step is not None
                wandb_writer = WandbWriter(
                    wandb_run=wandb_run,
                    epoch=epoch,
                    agent_step=agent_step,
                )

            if self.max_workers is not None:
                num_workers = self.max_workers
            else:
                cpu_count = multiprocessing.cpu_count()
                remainder = len(self.simulations) % cpu_count
                if remainder == 0 or len(self.simulations) < cpu_count:
                    num_workers = cpu_count
                else:
                    full_rounds = math.floor(len(self.simulations) / cpu_count)
                    num_workers = math.ceil(len(self.simulations) / full_rounds)
            logger.info("Using %d workers for evaluation", num_workers)
            sim_run_configs = [
                sim.to_simulation_run_config() if isinstance(sim, SimulationConfig) else sim for sim in self.simulations
            ]
            for sim_run in sim_run_configs:
                apply_lineup_overrides(
                    sim_run,
                    assignments=self.assignments,
                    proportions=self.proportions,
                    shuffle_assignments=self.shuffle_assignments,
                )
            rollout_results = simulate_and_record(
                policy_uris=policy_uris,
                simulations=sim_run_configs,
                replay_dir=self.replay_dir,
                seed=self.system.seed,
                observatory_writer=observatory_writer,
                wandb_writer=wandb_writer,
                max_workers=num_workers,
                on_progress=logger.info if self.verbose else lambda x: None,
            )

        render_eval_summary(
            rollout_results,
            policy_names=policy_names,
            verbose=self.verbose,
        )

        return rollout_results


class EvalWithResultTool(ToolWithResult, EvaluateTool):
    def run_job(self) -> ToolResult:
        try:
            self.run_eval()
            return ToolResult(result="success")
        except Exception as e:
            return ToolResult(result="failure", error=str(e))
