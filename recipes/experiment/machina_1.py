"""Machina v1 open-world recipe using the full vibe set and sweep helpers."""

from __future__ import annotations

from typing import Optional, Sequence

import metta.cogworks.curriculum as cc
import metta.tools as tools
from cogames.cli.client import TournamentServerClient
from metta.agent.policies.default import DefaultPolicyConfig
from metta.agent.policy import PolicyArchitecture
from metta.rl.policy_assets import PolicyAssetConfig
from metta.rl.training.teacher import TeacherConfig
from metta.sim.simulation_config import SimulationConfig
from metta.sweep.core import Distribution as D
from metta.sweep.core import ParameterSpec, make_sweep
from metta.sweep.core import SweepParameters as SP
from metta.tools.utils.auto_config import auto_stats_server_uri
from mettagrid.config import vibes
from recipes.experiment import cogsguard

DEFAULT_TEACHER_SERVER_URL = "https://api.observatory.softmax-research.net"
DEFAULT_TEACHER_SEASON = "beta-cvc"
DEFAULT_TEACHER_POLICY_NAME = "dinky"
DEFAULT_MISSION = "machina_1.open_world"


def _normalize_variant_names(
    *,
    initial: Optional[Sequence[str]] = None,
    variants: Optional[Sequence[str]] = None,
) -> list[str]:
    names: list[str] = []
    for source in (initial, variants):
        if not source:
            continue
        for name in source:
            if name not in names:
                names.append(name)
    return names


def make_training_env(
    *,
    num_cogs: int = 4,
    mission: str = DEFAULT_MISSION,
    variants: Optional[Sequence[str]] = None,
):
    if mission != DEFAULT_MISSION:
        raise ValueError(f"machina_1 only supports mission={DEFAULT_MISSION!r}, got {mission!r}")
    variant_names = _normalize_variant_names(variants=variants)
    return cogsguard.make_env(
        num_agents=num_cogs,
        max_steps=10000,
        variants=variant_names or None,
        layout="machina_1",
    )


def train_single_mission(
    *,
    mission: str = DEFAULT_MISSION,
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
    eval_variants: Optional[Sequence[str]] = None,
    teacher: TeacherConfig | None = None,
    maps_cache_size: Optional[int] = None,
) -> tools.TrainTool:
    _ = eval_variants, maps_cache_size
    env = make_training_env(num_cogs=num_cogs, mission=mission, variants=variants)
    curriculum_cfg = cc.env_curriculum(env)
    return cogsguard.train(
        curriculum=curriculum_cfg,
        teacher=teacher,
        variants=variants,
        layout="machina_1",
        num_agents=num_cogs,
        max_steps=10000,
    )


def get_cvc_sweep_search_space() -> dict[str, ParameterSpec]:
    return {
        **SP.param(
            "trainer.optimizer.learning_rate",
            D.LOG_NORMAL,
            min=1e-3,
            max=3e-2,
            search_center=1e-2,
        ),
        **SP.param(
            "trainer.optimizer.eps",
            D.LOG_NORMAL,
            min=1e-8,
            max=5e-5,
            search_center=1e-6,
        ),
        **SP.param(
            "trainer.optimizer.warmup_steps",
            D.INT_UNIFORM,
            min=0,
            max=10_000,
            search_center=2300,
        ),
        **SP.param(
            "trainer.optimizer.weight_decay",
            D.LOG_NORMAL,
            min=1e-5,
            max=1e-1,
            search_center=1e-2,
        ),
        **SP.param(
            "trainer.optimizer.momentum",
            D.UNIFORM,
            min=0.7,
            max=0.99,
            search_center=0.9,
        ),
        **SP.param(
            "trainer.losses.ppo_actor.clip_coef",
            D.UNIFORM,
            min=0.05,
            max=0.4,
            search_center=0.26,
        ),
        **SP.param(
            "trainer.advantage.gae_lambda",
            D.UNIFORM,
            min=0.8,
            max=0.995,
            search_center=0.97,
        ),
        **SP.param(
            "trainer.losses.ppo_critic.vf_coef",
            D.UNIFORM,
            min=0.1,
            max=2.0,
            search_center=0.75,
        ),
        **SP.param(
            "trainer.losses.ppo_actor.ent_coef",
            D.LOG_NORMAL,
            min=0.001,
            max=0.1,
            search_center=0.025,
        ),
        **SP.param(
            "trainer.advantage.gamma",
            D.UNIFORM,
            min=0.95,
            max=0.9995,
            search_center=0.99,
        ),
        **SP.categorical(
            "trainer.losses.ppo_critic.vf_clip_coef",
            choices=[0.0, 0.1, 0.2, 0.3],
        ),
        **SP.categorical(
            "trainer.sampling.method",
            choices=["sequential", "prioritized"],
        ),
        **SP.param(
            "trainer.sampling.prio_alpha",
            D.UNIFORM,
            min=0.0,
            max=1.0,
            search_center=0.4,
        ),
        **SP.param(
            "trainer.sampling.prio_beta0",
            D.UNIFORM,
            min=0.2,
            max=1.0,
            search_center=0.6,
        ),
        **SP.categorical(
            "policy_architecture.core_resnet_layers",
            choices=[1, 2, 3, 4],
        ),
        **SP.categorical(
            "policy_architecture.latent_dim",
            choices=[64, 96, 128],
        ),
        **SP.categorical(
            "policy_architecture.actor_hidden",
            choices=[256, 384, 512],
        ),
        **SP.categorical(
            "policy_architecture.core_num_heads",
            choices=[2, 4, 6],
        ),
        **SP.categorical(
            "policy_architecture.critic_hidden",
            choices=[512, 768, 1024],
        ),
        **SP.categorical(
            "policy_architecture.core_num_latents",
            choices=[12, 16, 20],
        ),
    }


def _apply_full_vibes(env_cfg) -> None:
    env_cfg.game.vibe_names = [v.name for v in vibes.VIBES]
    change_vibe = getattr(env_cfg.game.actions, "change_vibe", None)
    if change_vibe is not None:
        change_vibe.vibes = list(vibes.VIBES)
    if env_cfg.game.agent.vibe >= len(vibes.VIBES):
        env_cfg.game.agent.vibe = 0


def _lookup_default_teacher_policy_uri(
    *,
    server_url: str | None = None,
    season_name: str = DEFAULT_TEACHER_SEASON,
    policy_name: str = DEFAULT_TEACHER_POLICY_NAME,
) -> str:
    resolved_server_url = server_url or auto_stats_server_uri() or DEFAULT_TEACHER_SERVER_URL
    with TournamentServerClient(server_url=resolved_server_url) as client:
        leaderboard = client.get_leaderboard(season_name)

    matching_entries = [
        entry for entry in leaderboard if entry.policy.name == policy_name and entry.policy.id is not None
    ]
    if not matching_entries:
        raise RuntimeError(f"Could not find policy '{policy_name}' on the {season_name} leaderboard")

    top_entry = min(matching_entries, key=lambda entry: entry.rank)
    return f"metta://policy/{top_entry.policy.id}"


def train(
    num_cogs: int = 4,
    variants: Optional[Sequence[str]] = None,
    eval_variants: Optional[Sequence[str]] = None,
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
            policy_uri=_lookup_default_teacher_policy_uri(),
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
        teacher=teacher,
        maps_cache_size=None,
    )
    resolved_arch = policy_architecture or DefaultPolicyConfig()
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
