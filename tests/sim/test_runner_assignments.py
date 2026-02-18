import mettagrid.builder.envs as eb
from metta.sim.runner import SimulationRunConfig, run_simulations


def test_explicit_assignments_are_fixed_across_episodes() -> None:
    env = eb.make_navigation(num_agents=4)
    env.game.max_steps = 5

    assignments = [0, 1, 0, 1]
    simulation = SimulationRunConfig(
        env=env,
        num_episodes=3,
        assignments=assignments,
        # Even if set, explicit assignments should stay fixed.
        shuffle_assignments=True,
    )
    assert simulation.shuffle_assignments is False

    results = run_simulations(
        policy_uris=["mock://noop", "mock://random"],
        simulations=[simulation],
        replay_dir=None,
        seed=42,
        max_workers=1,
    )

    episodes = results[0].results.episodes
    assert len(episodes) == 3
    for episode in episodes:
        assert episode.assignments == assignments
