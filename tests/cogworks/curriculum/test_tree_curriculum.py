from metta.cogworks.curriculum.tree_curriculum import (
    MechanicsTreeDefinition,
    TreeTaskGenerator,
    build_tree_nodes,
    make_tree_curriculum_from_definition,
)
from metta.games.games import make_game
from metta.games.hunger.tree_curriculum import hunger_mechanics


def test_build_tree_nodes_resolves_variant_dependencies() -> None:
    nodes = build_tree_nodes(game="hunger", mechanics=["carnivore"], max_combination_size=1)
    assert len(nodes) == 1
    assert nodes[0].depth == 1
    assert nodes[0].mechanics == ("carnivore",)
    assert "food" in nodes[0].variants
    assert "carnivore" in nodes[0].variants


def test_tree_task_generator_scopes_tasks_to_interface_variants() -> None:
    full_variants = hunger_mechanics()
    generator = TreeTaskGenerator.Config(
        game="hunger",
        num_agents=8,
        max_steps=250,
        mechanics=["digest"],
        interface_variants=full_variants,
    ).create()

    task_env = generator.get_task(0)
    full_env = make_game("hunger", num_agents=8, max_steps=250, variants=full_variants)

    assert task_env.game.resource_names == full_env.game.resource_names
    assert task_env.game.id_map().tag_names() == full_env.game.id_map().tag_names()
    assert task_env.game.actions.actions() == full_env.game.actions.actions()


def test_make_tree_curriculum_from_definition_uses_definition_defaults() -> None:
    definition = MechanicsTreeDefinition(
        game="hunger",
        mechanics=("digest",),
        interface_variants=tuple(hunger_mechanics()),
        max_steps=123,
    )
    curriculum = make_tree_curriculum_from_definition(definition, num_agents=8)

    generator = curriculum.task_generator.create()
    task_env = generator.get_task(0)
    assert task_env.game.max_steps == 123
