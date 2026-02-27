from metta.cogworks.curriculum import Curriculum
from metta.rl.training.batch import calculate_batch_sizes
from recipes.experiment import cogsguard, game


def test_minimize_config_keeps_agent_aligned_batch_sizes() -> None:
    tool = cogsguard.train()
    tool._minimize_config_for_debugging()

    env_cfg = Curriculum(tool.training_env.curriculum).get_task().get_env_cfg()
    num_agents = int(env_cfg.game.num_agents)
    num_workers = 1 if tool.training_env.vectorization == "serial" else tool.training_env.num_workers
    _, _, num_envs = calculate_batch_sizes(
        forward_pass_minibatch_target_size=tool.training_env.forward_pass_minibatch_target_size,
        num_agents=num_agents,
        num_workers=num_workers,
        async_factor=tool.training_env.async_factor,
    )
    expected_batch_size = num_envs * num_agents * tool.trainer.bptt_horizon

    assert tool.trainer.batch_size == expected_batch_size
    assert tool.trainer.minibatch_size == expected_batch_size


def test_minimize_config_handles_non_divisible_initial_batches() -> None:
    tool = game.train(game="hunger", num_agents=40, max_steps=250)
    tool._minimize_config_for_debugging()
    assert tool.trainer.batch_size == tool.trainer.minibatch_size
