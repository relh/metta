from __future__ import annotations

from cogames_agents.policy.scripted_agent.cogsguard.policy import CogsguardPolicy

from mettagrid.policy.policy_env_interface import PolicyEnvInterface


def _policy_env_info(*, num_agents: int) -> PolicyEnvInterface:
    return PolicyEnvInterface(
        obs_features=[],
        tags=["agent", "hub", "junction"],
        action_names=[
            "noop",
            "move_north",
            "move_south",
            "move_east",
            "move_west",
            "change_vibe_default",
            "change_vibe_gear",
            "change_vibe_miner",
            "change_vibe_scout",
            "change_vibe_aligner",
            "change_vibe_scrambler",
        ],
        num_agents=num_agents,
        observation_shape=(1, 1),
        egocentric_shape=(5, 5),
    )


def test_static_role_order_pins_expected_initial_vibes() -> None:
    env = _policy_env_info(num_agents=4)
    policy = CogsguardPolicy(env, role_order="miner,scout,aligner,scrambler")

    assert policy._initial_vibes == ["miner", "scout", "aligner", "scrambler"]


def test_static_role_order_creates_single_role_agent_contracts() -> None:
    env = _policy_env_info(num_agents=3)
    policy = CogsguardPolicy(env, role_order="scout,aligner,scrambler")

    expected = ["scout", "aligner", "scrambler"]
    for agent_id, expected_vibe in enumerate(expected):
        agent = policy.agent_policy(agent_id)
        impl = agent._base_policy
        assert impl._initial_target_vibe == expected_vibe
        assert impl._smart_role_enabled is False


def test_role_gear_mode_enables_smart_role_for_all_agents() -> None:
    env = _policy_env_info(num_agents=4)
    policy = CogsguardPolicy(env, gear=env.num_agents)

    assert policy._initial_vibes == ["gear"] * env.num_agents
    for agent_id in range(env.num_agents):
        agent = policy.agent_policy(agent_id)
        impl = agent._base_policy
        assert impl._initial_target_vibe == "gear"
        assert impl._smart_role_enabled is True
