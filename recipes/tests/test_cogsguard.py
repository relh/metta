"""Tests for the cogsguard recipe.

These tests verify that the cogsguard environment can be created and played.
"""

from __future__ import annotations

import random

import pytest

from cogames.cogs_vs_clips.config import CvCConfig
from metta.agent.policies.puffer_default import PufferDefaultConfig
from metta.cogworks.curriculum.task_generator import BucketedTaskGenerator, SingleTaskGenerator, TaskGeneratorSet
from metta.rl.training.teacher import TeacherConfig
from metta.sweep.parameter_config import ParameterConfig

# Import after cogsguard to avoid circular import issues
from mettagrid.simulator import Simulation
from recipes.experiment import cogsguard


class TestCogsguardEnvironment:
    """Test cogsguard environment creation and basic operation."""

    @pytest.mark.parametrize(
        ("layout", "expected_label"),
        [
            ("machina_1", "cogsguard_machina_1.basic"),
            ("arena", "cogsguard_arena.basic"),
        ],
    )
    def test_make_env_layout_switches_map(self, layout: str, expected_label: str) -> None:
        env_config = cogsguard.make_env(num_agents=4, max_steps=10, layout=layout)  # type: ignore[arg-type]
        assert env_config.label == expected_label

    def test_make_env_creates_valid_config(self) -> None:
        """Test that make_env creates a valid MettaGridConfig."""
        env_config = cogsguard.make_env(num_agents=4, max_steps=100)

        assert env_config is not None
        assert env_config.game.num_agents == 4
        assert env_config.game.max_steps == 100

        # Check resources are configured
        assert "energy" in env_config.game.resource_names
        assert "heart" in env_config.game.resource_names
        assert "hp" in env_config.game.resource_names

        # Check gear resources
        for gear_type in CvCConfig.GEAR:
            assert gear_type in env_config.game.resource_names

        # Check element resources
        for element in CvCConfig.ELEMENTS:
            assert element in env_config.game.resource_names

    def test_environment_simulation_runs(self) -> None:
        """Test that the environment can be simulated for multiple steps."""
        env_config = cogsguard.make_env(num_agents=4, max_steps=100)
        sim = Simulation(env_config)

        # Verify simulation initialized correctly
        assert sim.num_agents == 4
        assert len(sim.action_names) > 0
        assert "noop" in sim.action_names

        # Run simulation for a few steps with random actions
        num_steps = 10
        for _step in range(num_steps):
            # Set random actions for each agent
            for agent_id in range(sim.num_agents):
                action = random.choice(sim.action_names)
                sim.agent(agent_id).set_action(action)

            sim.step()

            # Verify observations and rewards are valid
            obs = sim._c_sim.observations()
            rewards = sim._c_sim.rewards()
            terminals = sim._c_sim.terminals()

            assert obs.shape[0] == sim.num_agents
            assert rewards.shape[0] == sim.num_agents
            assert terminals.shape[0] == sim.num_agents

    def test_environment_with_noop_actions(self) -> None:
        """Test that the environment works with noop actions."""
        env_config = cogsguard.make_env(num_agents=2, max_steps=50)
        sim = Simulation(env_config)

        # Run with noop actions only
        for _ in range(5):
            for agent_id in range(sim.num_agents):
                sim.agent(agent_id).set_action("noop")
            sim.step()

        # Should complete without errors
        assert sim.current_step == 5

    def test_objects_configured_correctly(self) -> None:
        """Test that game objects are configured properly."""
        env_config = cogsguard.make_env(num_agents=4, max_steps=100)

        objects = env_config.game.objects
        assert len(objects) > 0

        # Check that key object types exist
        assert "wall" in objects
        # Station object names are team-prefixed (e.g. "c:hub"), while render_name
        # is unprefixed (e.g. "hub").
        assert "c:hub" in objects
        assert "junction" in objects
        assert "c:miner" in objects
        assert "c:scout" in objects
        assert "c:aligner" in objects
        assert "c:scrambler" in objects

        # Check extractors for all elements
        for element in CvCConfig.ELEMENTS:
            assert f"{element}_extractor" in objects


class TestCogsguardCurriculum:
    """Test cogsguard curriculum configuration."""

    def test_make_curriculum_returns_valid_config(self) -> None:
        """Test that make_curriculum creates a valid curriculum config."""
        curriculum = cogsguard.make_curriculum()

        assert curriculum is not None
        # Check that the curriculum has tasks configured
        assert curriculum.task_generator is not None

    def test_make_curriculum_includes_fixed_maps(self) -> None:
        curriculum = cogsguard.make_curriculum(
            num_agents=4,
            include_fixed_maps=True,
            include_eval_missions=False,
        )
        task_generator = curriculum.task_generator
        assert task_generator is not None
        configs = (
            task_generator.task_generators if isinstance(task_generator, TaskGeneratorSet.Config) else [task_generator]
        )
        labels = []
        for config in configs:
            if not isinstance(config, BucketedTaskGenerator.Config):
                continue
            child = config.child_generator_config
            if isinstance(child, SingleTaskGenerator.Config):
                labels.append(child.env.label)
        assert any("cogsguard_fixed_" in label for label in labels)

    def test_make_curriculum_max_steps_buckets(self) -> None:
        buckets = [500, 1000, 2000]
        curriculum = cogsguard.make_curriculum(
            layout="arena",
            include_eval_missions=False,
            include_fixed_maps=False,
            max_steps=2000,
            max_steps_buckets=buckets,
        )
        task_generator = curriculum.task_generator
        assert isinstance(task_generator, TaskGeneratorSet.Config)
        steps = []
        for config in task_generator.task_generators:
            assert isinstance(config, BucketedTaskGenerator.Config)
            child = config.child_generator_config
            assert isinstance(child, SingleTaskGenerator.Config)
            steps.append(child.env.game.max_steps)
        assert sorted(set(steps)) == buckets

    def test_simulations_returns_valid_configs(self) -> None:
        """Test that simulations() returns valid simulation configs."""
        sims = cogsguard.simulations()

        assert len(sims) > 0
        for sim in sims:
            assert sim.suite == "cogsguard"
            assert sim.env is not None


def test_wave_only_variant_disables_followup_events() -> None:
    env_config = cogsguard.make_env(num_agents=4, max_steps=100, variants="clips_wave_only")
    events = env_config.game.events
    assert events["cogs_to_neutral"].timesteps == []
    assert events["neutral_to_clips"].timesteps == []


@pytest.mark.parametrize("num_agents", [2, 4, 8])
def test_environment_scales_with_agents(num_agents: int) -> None:
    """Test that the environment works with different agent counts."""
    env_config = cogsguard.make_env(num_agents=num_agents, max_steps=50)
    sim = Simulation(env_config)

    assert sim.num_agents == num_agents

    # Run a few steps
    for _ in range(3):
        for agent_id in range(sim.num_agents):
            sim.agent(agent_id).set_action("noop")
        sim.step()

    assert sim.current_step == 3


def test_train_with_smart_gear_teacher_policy_uri() -> None:
    teacher_uri = "metta://policy/role?gear=10"
    teacher = TeacherConfig(policy_uri=teacher_uri, mode="scripted.eer_cloner.sliced")

    tool = cogsguard.train(teacher=teacher)

    assert tool.training_env.supervisor_policy_uri == teacher_uri
    assert tool.trainer.losses.has_loss("teacher_led")
    assert tool.trainer.losses.has_loss("student_led")
    assert tool.scheduler is not None


def test_train_does_not_enable_teacher_by_default() -> None:
    tool = cogsguard.train()

    assert tool.training_env.supervisor_policy_uri is None
    assert not tool.trainer.losses.has_loss("teacher_led")
    assert not tool.trainer.losses.has_loss("student_led")
    assert tool.scheduler is None


def test_train_uses_best_auc_routed_adapter_defaults() -> None:
    tool = cogsguard.train()
    learner_arch = tool.policy_assets["learner0"].architecture
    assert learner_arch is not None
    assert learner_arch.cortex_routed_adapter is not None
    assert learner_arch.cortex_routed_adapter.rank == 8
    assert learner_arch.cortex_routed_adapter.trunk_lr_mult == pytest.approx(0.5476294593341358)


def test_train_accepts_policy_architecture_spec_string() -> None:
    tool = cogsguard.train(
        policy_architecture="metta.agent.policies.puffer_default.PufferDefaultConfig(hidden_size=64)"
    )
    assert isinstance(tool.policy_assets["learner0"].architecture, PufferDefaultConfig)
    assert tool.policy_assets["learner0"].architecture.hidden_size == 64


def test_sweep_sweeps_hypers_and_fixes_variants_and_timesteps() -> None:
    tool = cogsguard.sweep("cogsguard.test")
    space = tool.search_space

    assert space["variants"] == ["milestones", "credit", "penalize_vibe_change"]
    assert space["trainer.total_timesteps"] == 3_000_000_000

    # Ensure we sweep PPO/training hypers rather than the environment variants.
    assert isinstance(space["trainer.optimizer.learning_rate"], ParameterConfig)
    assert isinstance(space["trainer.losses.ppo_actor.clip_coef"], ParameterConfig)
