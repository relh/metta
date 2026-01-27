"""Interactive play tool for Metta simulations."""

import logging
import uuid
from typing import Optional

import torch
from metta_alo.rollout import run_single_episode
from pydantic import PrivateAttr, model_validator
from rich.console import Console

from metta.app_backend.clients.stats_client import StatsClient
from metta.common.tool import Tool
from metta.common.wandb.context import WandbConfig
from metta.sim.simulation_config import SimulationConfig
from metta.tools.utils.auto_config import auto_stats_server_uri, auto_wandb_config
from mettagrid.map_builder.map_builder import HasSeed
from mettagrid.renderer.renderer import RenderMode
from mettagrid.util.uri_resolvers.schemes import policy_spec_from_uri

logger = logging.getLogger(__name__)


class PlayTool(Tool):
    """Interactive play tool for Metta simulations using Rollout.

    This tool creates an interactive play session where agents act using either
    a specified policy or random actions. The simulation is rendered according
    to the specified render mode (gui, unicode, log, or none).
    """

    wandb: WandbConfig = auto_wandb_config()
    sim: SimulationConfig

    policy_uri: str | None = None  # Deprecated, use policy_version_id or s3_path instead
    s3_path: str | None = None
    policy_version_id: str | None = None

    open_browser_on_start: bool = True
    max_steps: Optional[int] = None
    # Single source of truth for determinism in `play`:
    # - If the user passes `seed=<N>`, we also set `system.seed=<N>` so Python/NumPy/Torch
    #   are seeded consistently.
    # - If the user passes only `system.seed=<N>`, we default `seed` to that value so the
    #   simulator rollout is deterministic as well.
    seed: int | None = None
    render: RenderMode = "gui"
    autostart: bool = False
    stats_server_uri: str | None = auto_stats_server_uri()

    _explicit_seed_overrides: set[str] = PrivateAttr(default_factory=set)

    def override(self, key: str, value: object):  # type: ignore[override]
        """Keep `seed` a single determinism knob unless the user explicitly overrides individual seeds."""
        tool = super().override(key, value)
        assert isinstance(tool, PlayTool)

        if key in {"seed", "system.seed", "sim.env.game.map_builder.seed"}:
            tool._explicit_seed_overrides.add(key)

        if key == "seed" and tool.seed is not None:
            if "system.seed" not in tool._explicit_seed_overrides:
                tool.system.seed = int(tool.seed)
            map_builder = tool.sim.env.game.map_builder
            if isinstance(map_builder, HasSeed):
                if "sim.env.game.map_builder.seed" not in tool._explicit_seed_overrides:
                    map_builder.seed = int(tool.seed)

        if key == "system.seed":
            if "seed" not in tool._explicit_seed_overrides and tool.seed is None:
                tool.seed = int(tool.system.seed)
            map_builder = tool.sim.env.game.map_builder
            if isinstance(map_builder, HasSeed):
                if "sim.env.game.map_builder.seed" not in tool._explicit_seed_overrides:
                    seed = tool.seed
                    if seed is None:
                        raise RuntimeError("PlayTool.seed should be set when syncing map_builder seed")
                    map_builder.seed = int(seed)

        return tool

    @model_validator(mode="after")
    def validate(self) -> "PlayTool":
        if len([x for x in [self.policy_uri, self.policy_version_id, self.s3_path] if x is not None]) > 1:
            raise ValueError("Only one of policy_uri, policy_version_id, or s3_path can be specified")
        return self

    def invoke(self, args: dict[str, str]) -> int | None:
        """Run an interactive play session with the configured simulation."""

        console = Console()
        device = torch.device("cpu")

        # Get environment config
        env_cfg = self.sim.env
        # Set max_steps in config if specified
        if self.max_steps is not None:
            env_cfg.game.max_steps = self.max_steps

        s3_path: str | None = self.s3_path
        if self.policy_version_id:
            if not self.stats_server_uri:
                raise ValueError("stats_server_uri is required")
            if s3_path:
                raise ValueError("s3_path and policy_version_id cannot be specified together")
            stats_client = StatsClient.create(self.stats_server_uri)
            policy_version = stats_client.get_policy_version(uuid.UUID(self.policy_version_id))
            s3_path = policy_version.s3_path
            if not s3_path:
                raise ValueError(f"Policy version {self.policy_version_id} has no s3 path")

        if s3_path:
            policy_specs = [policy_spec_from_uri(s3_path, device=str(device))]
            logger.info("Using policy from s3 path")
        elif self.policy_uri:
            logger.info(f"Loading policy from URI: {self.policy_uri}")
            policy_specs = [policy_spec_from_uri(self.policy_uri, device=str(device))]
            logger.info("Using policy from deprecated-format policy uri")
        else:
            # Fall back to random policies only when no policy was configured explicitly.
            policy_specs = [policy_spec_from_uri("metta://policy/random", device=str(device))]

        seed = self.seed
        if seed is None:
            seed = self.system.seed

        episode_results, _replay = run_single_episode(
            policy_specs=policy_specs,
            assignments=[0] * env_cfg.game.num_agents,
            env=env_cfg,
            results_uri=None,
            replay_uri=None,
            seed=seed,
            max_action_time_ms=10000,
            autostart=self.autostart,
            device=str(device),
            render_mode=self.render,
        )

        logger.info("Starting interactive play session")
        console.print(f"[cyan]Running simulation with {env_cfg.game.num_agents} agents[/cyan]")
        console.print(f"[cyan]Render mode: {self.render}[/cyan]")
        console.print(f"[cyan]Max steps: {env_cfg.game.max_steps}[/cyan]")

        console.print("\n[bold green]Episode Complete![/bold green]")
        console.print(f"Steps: {episode_results.steps}")
        console.print(f"Total Rewards: {episode_results.rewards}")
        console.print(f"Final Reward Sum: {float(sum(episode_results.rewards)):.2f}")

        return None
