"""Interactive play tool for Metta simulations."""

import logging
from typing import Optional

import torch
from metta_alo.scoring import allocate_counts, validate_proportions
from pydantic import PrivateAttr
from rich.console import Console

from cogames.seed import seed_rollout_rng
from metta.common.tool import Tool
from metta.common.wandb.context import WandbConfig
from metta.sim.simulation_config import SimulationConfig
from metta.tools.utils.auto_config import auto_wandb_config
from mettagrid.map_builder.map_builder import HasSeed
from mettagrid.renderer.renderer import RenderMode
from mettagrid.runner.rollout import run_episode_local
from mettagrid.runner.types import SingleEpisodeJob
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

    # Back-compat: single-policy override for CLI usage (`policy_uri=...`). Prefer `policy_uris` going forward.
    policy_uri: str | None = None
    policy_uris: list[str] = []
    assignments: list[int] | None = None
    proportions: list[float] | None = None

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

    def _resolve_assignments(self, *, num_agents: int, num_policies: int) -> list[int]:
        if self.assignments is not None and self.proportions is not None:
            raise ValueError("Specify only one of assignments or proportions")

        if self.assignments is not None:
            if len(self.assignments) != num_agents:
                raise ValueError(f"assignments length ({len(self.assignments)}) must equal num_agents ({num_agents})")
            assignments = list(self.assignments)
            if any(policy_idx < 0 or policy_idx >= num_policies for policy_idx in assignments):
                raise ValueError(
                    "assignments contains an out-of-range policy index "
                    f"(num_policies={num_policies}, assignments={assignments})"
                )
            return assignments

        proportions = list(self.proportions) if self.proportions is not None else [1.0] * num_policies
        validate_proportions(proportions, num_policies)
        counts = allocate_counts(num_agents, proportions)
        return [i for i, c in enumerate(counts) for _ in range(c)]

    def invoke(self, args: dict[str, str]) -> int | None:
        """Run an interactive play session with the configured simulation."""

        console = Console()
        device = torch.device("cpu")

        # Get environment config
        env_cfg = self.sim.env
        # Set max_steps in config if specified
        if self.max_steps is not None:
            env_cfg.game.max_steps = self.max_steps

        if self.policy_uri and self.policy_uris:
            raise ValueError("Specify only one of policy_uri or policy_uris")
        policy_uris = list(self.policy_uris) if self.policy_uris else ([self.policy_uri] if self.policy_uri else [])
        if not policy_uris:
            # Fall back to random policies only when no policy was configured explicitly.
            policy_uris = ["metta://policy/random"]
        policy_specs = [policy_spec_from_uri(uri, device=str(device)) for uri in policy_uris]
        assignments = self._resolve_assignments(num_agents=env_cfg.game.num_agents, num_policies=len(policy_specs))

        seed = int(self.seed if self.seed is not None else self.system.seed)
        seed_rollout_rng(seed)

        job = SingleEpisodeJob(
            policy_uris=list(policy_uris),
            assignments=list(assignments),
            env=env_cfg,
            seed=seed,
            max_action_time_ms=10000,
        )
        episode_results, _replay = run_episode_local(
            policy_specs=policy_specs,
            assignments=job.assignments,
            env=job.env,
            seed=job.seed,
            max_action_time_ms=job.max_action_time_ms,
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
