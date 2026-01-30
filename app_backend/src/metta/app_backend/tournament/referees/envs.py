from cogames.cogs_vs_clips.missions import (
    MettaGridConfig,
    make_cogsguard_mission,
)


def make_shared_rewards_env(seed: int, num_agents: int) -> MettaGridConfig:
    """Legacy shared rewards env - now uses CogsGuard mission."""
    return make_cogsguard_env(seed=seed, num_agents=num_agents)


def make_cogsguard_env(seed: int, num_agents: int = 10, max_steps: int = 1000) -> MettaGridConfig:
    mission = make_cogsguard_mission(num_agents=num_agents, max_steps=max_steps)
    env = mission.make_env()
    env.game.map_builder.seed = seed  # type: ignore
    return env
