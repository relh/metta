from cogames.cogs_vs_clips.missions import Machina1OpenWorldSharedRewardsMission, MettaGridConfig


def make_shared_rewards_env(seed: int, num_agents: int) -> MettaGridConfig:
    mission = Machina1OpenWorldSharedRewardsMission.model_copy(deep=True)
    mission.num_cogs = num_agents
    env = mission.make_env()
    env.game.map_builder.seed = seed  # type: ignore
    return env
