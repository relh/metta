from __future__ import annotations

from types import SimpleNamespace

from metta.rl.training.component import TrainerComponent
from metta.rl.training.training_environment import VectorizedTrainingEnvironment


class _ProbeComponent(TrainerComponent):
    pass


def test_trainer_component_disables_step_callbacks_at_zero_interval() -> None:
    component = _ProbeComponent(step_interval=0)

    assert not component.should_handle_step(current_step=10, previous_step=0)


def test_trainer_component_epoch_interval_zero_always_runs() -> None:
    component = _ProbeComponent(epoch_interval=0)

    assert component.should_handle_epoch(1)
    assert component.should_handle_epoch(2)


def test_vectorized_training_environment_exposes_curriculum() -> None:
    env = VectorizedTrainingEnvironment.__new__(VectorizedTrainingEnvironment)
    curriculum = object()
    env._curriculum = curriculum

    assert env.curriculum is curriculum


def test_vectorized_training_environment_total_parallel_agents_prefers_vecenv_count() -> None:
    env = VectorizedTrainingEnvironment.__new__(VectorizedTrainingEnvironment)
    env._vecenv = SimpleNamespace(num_agents=7)
    env._num_envs = 2
    env._num_agents = 4

    assert env.total_parallel_agents == 7


def test_vectorized_training_environment_total_parallel_agents_falls_back_to_env_shape() -> None:
    env = VectorizedTrainingEnvironment.__new__(VectorizedTrainingEnvironment)
    env._vecenv = SimpleNamespace()
    env._num_envs = 2
    env._num_agents = 4

    assert env.total_parallel_agents == 8
