import multiprocessing
import os
import random
import tempfile
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Sequence

from metta_alo.scoring import allocate_counts, validate_proportions
from pydantic import BaseModel, ConfigDict, Field, model_validator

from mettagrid import MettaGridConfig
from mettagrid.runner.episode_runner import run_episode_isolated
from mettagrid.runner.types import SingleEpisodeJob
from mettagrid.simulator.multi_episode.rollout import EpisodeRolloutResult, MultiEpisodeRolloutResult


def _run_single_simulation(
    simulation: Any,
    policy_uris: Sequence[str],
    replay_dir: str | None,
    seed: int,
) -> "SimulationRunResult":
    sim_cfg = SimulationRunConfig.model_validate(simulation)

    if sim_cfg.assignments is not None:
        assignments = list(sim_cfg.assignments)
    else:
        proportions = list(sim_cfg.proportions) if sim_cfg.proportions is not None else [1.0] * len(policy_uris)
        counts = allocate_counts(sim_cfg.env.game.num_agents, proportions)
        assignments = [i for i, c in enumerate(counts) for _ in range(c)]
    max_action_time_ms = int(sim_cfg.max_action_time_ms or 10000)

    rng = random.Random(seed)
    assignments_list = list(assignments)
    episodes: list[EpisodeRolloutResult] = []

    if replay_dir is not None:
        Path(replay_dir).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="metta_episode_results_") as tmpdir:
        tmp = Path(tmpdir)
        for episode_idx in range(sim_cfg.num_episodes):
            if sim_cfg.shuffle_assignments:
                rng.shuffle(assignments_list)

            replay_path: Path | None = None
            if replay_dir is not None:
                replay_path = Path(replay_dir) / f"{uuid.uuid4()}.json.z"

            results_path = tmp / f"results_{episode_idx}.json"
            job = SingleEpisodeJob(
                policy_uris=list(policy_uris),
                assignments=list(assignments_list),
                env=sim_cfg.env,
                seed=seed + episode_idx,
                max_action_time_ms=max_action_time_ms,
                episode_tags=dict(sim_cfg.episode_tags),
            )
            ep_results = run_episode_isolated(
                job.episode_spec(),
                results_path,
                replay_path=replay_path,
            )
            episodes.append(
                EpisodeRolloutResult(
                    assignments=list(assignments_list),
                    rewards=list(ep_results.rewards),
                    action_timeouts=list(ep_results.action_timeouts),
                    stats=ep_results.stats,
                    replay_path=str(replay_path) if replay_path else None,
                    steps=ep_results.steps,
                    max_steps=sim_cfg.env.game.max_steps,
                    time_averaged_game_stats=ep_results.time_averaged_game_stats,
                )
            )

    rollout_result = MultiEpisodeRolloutResult(episodes=episodes)

    return SimulationRunResult(run=sim_cfg, results=rollout_result)


class SimulationRunConfig(BaseModel):
    env: MettaGridConfig  # noqa: F821
    num_episodes: int = Field(default=1, description="Number of episodes to run", ge=1)
    proportions: Sequence[float] | None = None
    assignments: Sequence[int] | None = None
    shuffle_assignments: bool = True

    max_action_time_ms: int | None = Field(
        default=10000, description="Maximum time (in ms) a policy is given to take an action"
    )
    episode_tags: dict[str, str] = Field(default_factory=dict, description="Tags to add to each episode")

    @model_validator(mode="after")
    def validate_lineup(self) -> "SimulationRunConfig":
        if self.assignments is not None and self.proportions is not None:
            raise ValueError("Specify only one of assignments or proportions")
        if self.assignments is not None and len(self.assignments) != self.env.game.num_agents:
            raise ValueError(
                f"assignments length ({len(self.assignments)}) must equal num_agents ({self.env.game.num_agents})"
            )
        # Explicit assignments define a fixed policy-per-agent mapping.
        # Ignore shuffle in this mode to keep routed-adapter slot mapping stable.
        if self.assignments is not None:
            self.shuffle_assignments = False
        return self


class SimulationRunResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run: SimulationRunConfig
    results: MultiEpisodeRolloutResult


def apply_lineup_overrides(
    sim_run: SimulationRunConfig,
    *,
    assignments: Sequence[int] | None,
    proportions: Sequence[float] | None,
    shuffle_assignments: bool,
) -> None:
    if assignments is not None and proportions is not None:
        raise ValueError("Specify only one of assignments or proportions")

    if assignments is not None:
        sim_run.assignments = list(assignments)
        sim_run.proportions = None
        sim_run.shuffle_assignments = False
        return

    if proportions is not None:
        sim_run.proportions = list(proportions)
        sim_run.assignments = None
        sim_run.shuffle_assignments = shuffle_assignments
        return

    sim_run.shuffle_assignments = shuffle_assignments


def run_simulations(
    *,
    policy_uris: Sequence[str],
    simulations: Sequence[SimulationRunConfig],
    replay_dir: str | None,
    seed: int,
    max_workers: int | None = None,
    on_progress: Callable[[str], None] = lambda x: None,
) -> list[SimulationRunResult]:
    if not policy_uris:
        raise ValueError("At least one policy URI is required")
    for simulation in simulations:
        if simulation.assignments is not None:
            if any(policy_idx < 0 or policy_idx >= len(policy_uris) for policy_idx in simulation.assignments):
                raise ValueError(
                    "assignments contains an out-of-range policy index "
                    f"(num_policies={len(policy_uris)}, assignments={list(simulation.assignments)})"
                )
        else:
            validate_proportions(simulation.proportions, len(policy_uris))

    # Sequential path for max_workers unset or 1
    if not max_workers or max_workers <= 1 or len(simulations) <= 1:
        sequential_rollouts: list[SimulationRunResult] = []
        for i, simulation in enumerate(simulations):
            on_progress(f"Beginning rollout for simulation {i + 1} of {len(simulations)}")
            sequential_rollouts.append(_run_single_simulation(simulation, policy_uris, replay_dir, seed))
            on_progress(f"Finished rollout for simulation {i + 1} of {len(simulations)}")

        return sequential_rollouts

    # Parallel path
    simulation_rollouts: list[SimulationRunResult] = [None] * len(simulations)  # type: ignore[assignment]

    # Serialize configs to avoid pickling issues
    simulation_payloads = [sim.model_dump(mode="json") for sim in simulations]
    policy_payloads = list(policy_uris)

    on_progress(f"Launching {len(simulations)} eval rollouts with up to {max_workers} workers")

    # Use spawn in parallel mode; it's safer for CUDA and avoids subtle fork issues.
    mp_context = multiprocessing.get_context("spawn")

    with ProcessPoolExecutor(max_workers=max_workers, mp_context=mp_context) as executor:
        future_to_idx = {
            executor.submit(
                _run_single_simulation,
                payload,
                policy_payloads,
                os.path.join(replay_dir, f"sim_{idx}") if replay_dir else None,
                seed,
            ): idx
            for idx, payload in enumerate(simulation_payloads)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            simulation_rollouts[idx] = future.result()
            on_progress(f"Finished rollout for simulation {idx + 1} of {len(simulations)}")

    return simulation_rollouts
