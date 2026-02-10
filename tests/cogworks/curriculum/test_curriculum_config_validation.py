import pytest

import mettagrid.builder.envs as eb
from metta.cogworks.curriculum import CurriculumConfig, SingleTaskGenerator


def test_curriculum_config_allows_num_active_tasks_up_to_max_task_id_plus_one() -> None:
    env = eb.make_arena(num_agents=1)
    CurriculumConfig(task_generator=SingleTaskGenerator.Config(env=env), max_task_id=1, num_active_tasks=2)


def test_curriculum_config_rejects_num_active_tasks_above_max_task_id_plus_one() -> None:
    env = eb.make_arena(num_agents=1)
    with pytest.raises(ValueError, match="max_task_id\\+1"):
        CurriculumConfig(task_generator=SingleTaskGenerator.Config(env=env), max_task_id=1, num_active_tasks=3)
