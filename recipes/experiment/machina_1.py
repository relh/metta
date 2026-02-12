"""Machina v1 open-world recipe using the full vibe set and sweep helpers."""

from __future__ import annotations

from typing import Optional, Sequence

import metta.tools as tools
from metta.agent.policies.core_policy import CorePolicyConfig
from metta.agent.policy import PolicyArchitecture
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.training.teacher import TeacherConfig
from metta.sim.simulation_config import SimulationConfig
from metta.sweep.core import make_sweep
from mettagrid.config import vibes
from recipes.experiment.cogs_v_clips import (
    _normalize_variant_names,
    get_cvc_sweep_search_space,
    make_training_env,
    train_single_mission,
)


def _apply_full_vibes(env_cfg) -> None:
    env_cfg.game.vibe_names = [v.name for v in vibes.VIBES]
    change_vibe = getattr(env_cfg.game.actions, "change_vibe", None)
    if change_vibe is not None:
        change_vibe.vibes = list(vibes.VIBES)
    if env_cfg.game.agent.vibe >= len(vibes.VIBES):
        env_cfg.game.agent.vibe = 0


def train(
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
    eval_variants: Optional[Sequence[str]] = None,
    eval_difficulty: str | None = None,
    policy_architecture: PolicyArchitecture | None = None,
    teacher: TeacherConfig | None = None,
    use_default_teacher: bool = False,
) -> tools.TrainTool:
    """Train on machina_1.open_world with leaderboard-aligned defaults and single-map eval."""
    if eval_variants is None:
        eval_variants = variants

    if teacher is None and use_default_teacher:
        teacher = TeacherConfig(
            mode="scripted.supervisor.mixed",
            policy_uri="metta://policy/dinky:v15",
            steps=5_500_000_000,
            teacher_led_proportion=0.0,
            anneal_start_step=2_500_000_000,
            ppo_begin_step=0,
        )

    tt = train_single_mission(
        mission="machina_1.open_world",
        num_cogs=num_cogs,
        variants=variants,
        eval_variants=eval_variants,
        eval_difficulty=eval_difficulty,
        teacher=teacher,
        maps_cache_size=None,
    )
    resolved_arch = policy_architecture or CorePolicyConfig()
    learner_cfg = tt.policy_assets.get("learner0")
    if learner_cfg is None:
        tt.policy_assets["learner0"] = PolicyAssetConfig(architecture=resolved_arch)
    else:
        learner_cfg.architecture = resolved_arch
    tt.system.torch_deterministic = False

    # Explicitly keep full vibe/action definitions so saved checkpoints remain compatible.
    env_cfg = tt.training_env.curriculum.task_generator.env
    env_cfg.game.max_steps = 10000
    _apply_full_vibes(env_cfg)

    eval_variant_names = _normalize_variant_names(
        initial=[eval_difficulty] if eval_difficulty else None,
        variants=eval_variants,
    )
    eval_env = make_training_env(
        num_cogs=num_cogs,
        mission="machina_1.open_world",
        variants=eval_variant_names or None,
    )
    eval_env.game.max_steps = 10000
    _apply_full_vibes(eval_env)
    tt.evaluator.simulations = [
        SimulationConfig(
            suite="cogs_vs_clips",
            name=f"machina_1_open_world_{num_cogs}cogs",
            env=eval_env,
        )
    ]
    # Run evals periodically during long runs
    tt.evaluator.epoch_interval = 150
    return tt


def _make_play_sim(
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
):
    variant_names = _normalize_variant_names(variants=variants)
    env_cfg = make_training_env(
        num_cogs=num_cogs,
        mission="machina_1.open_world",
        variants=variant_names or None,
    )
    env_cfg.game.max_steps = 10000
    _apply_full_vibes(env_cfg)
    return SimulationConfig(
        suite="cogs_vs_clips",
        name=f"machina_1_open_world_{num_cogs}cogs",
        env=env_cfg,
    )


def play(
    policy_uri: str | None = None,
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
) -> tools.PlayTool:
    """Interactive play on machina_1.open_world."""
    return tools.PlayTool(sim=_make_play_sim(num_cogs=num_cogs, variants=variants), policy_uri=policy_uri)


def replay(
    policy_uri: str | None = None,
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
) -> tools.ReplayTool:
    """Generate a replay for machina_1.open_world."""
    return tools.ReplayTool(sim=_make_play_sim(num_cogs=num_cogs, variants=variants), policy_uri=policy_uri)


def train_sweep(
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
    eval_variants: Optional[Sequence[str]] = None,
    eval_difficulty: str | None = None,
    policy_architecture: PolicyArchitecture | None = None,
    teacher: TeacherConfig | None = None,
    use_default_teacher: bool = False,
) -> tools.TrainTool:
    """Sweep-friendly train with heart_chorus baked in."""
    base_variants = _normalize_variant_names(initial=["heart_chorus"], variants=variants)

    tt = train(
        num_cogs=num_cogs,
        variants=base_variants,
        eval_variants=eval_variants or base_variants,
        eval_difficulty=eval_difficulty,
        policy_architecture=policy_architecture,
        teacher=teacher,
        use_default_teacher=use_default_teacher,
    )
    # Sweep-friendly default (kept consistent with the shared CvC sweep search space).
    tt.trainer.total_timesteps = 1_000_000_000
    return tt


def evaluate_stub(*args, **kwargs) -> tools.StubTool:
    """No-op evaluator for sweeps."""

    return tools.StubTool()


def sweep(
    sweep_name: str,
    num_cogs: int = 4,
    eval_difficulty: str | None = "standard",
    max_trials: int = 80,
    num_parallel_trials: int = 12,
) -> tools.SweepTool:
    """Hyperparameter sweep targeting train_sweep (heart_chorus baked in)."""
    search_space = get_cvc_sweep_search_space()

    return make_sweep(
        name=sweep_name,
        recipe="recipes.experiment.machina_1",
        train_entrypoint="train_sweep",
        eval_entrypoint="evaluate_stub",
        metric_key="env_game/hub.heart.created",
        search_space=search_space,
        cost_key="metric/total_time",
        max_trials=max_trials,
        num_parallel_trials=num_parallel_trials,
    )
