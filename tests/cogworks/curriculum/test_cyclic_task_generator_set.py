import mettagrid.builder.envs as eb
from metta.cogworks.curriculum import CyclicTaskGeneratorSet, SingleTaskGenerator


def test_cyclic_task_generator_set_cycles_by_task_id() -> None:
    env_a = eb.make_arena(num_agents=1)
    env_a.label = "a"
    env_b = eb.make_arena(num_agents=1)
    env_b.label = "b"

    gen = CyclicTaskGeneratorSet(
        CyclicTaskGeneratorSet.Config(
            task_generators=[
                SingleTaskGenerator.Config(env=env_a),
                SingleTaskGenerator.Config(env=env_b),
            ]
        )
    )

    assert gen.get_task(0).label == "a"
    assert gen.get_task(1).label == "b"
    assert gen.get_task(2).label == "a"
