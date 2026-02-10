from recipes.experiment import meta_learning_sanity


def test_meta_learning_sanity_recipe_builds_train_tool() -> None:
    tool = meta_learning_sanity.train(num_agents=2, goal_obs=True, observe_last_reward=True, max_steps=50)

    assert tool.training_env is not None
    assert tool.training_env.curriculum.num_active_tasks == 2
    assert tool.training_env.curriculum.max_task_id == 1

    assert tool.evaluator is not None
    assert len(tool.evaluator.simulations) == 2
    assert {sim.name for sim in tool.evaluator.simulations} == {"collect_ore_red", "collect_battery_red"}
