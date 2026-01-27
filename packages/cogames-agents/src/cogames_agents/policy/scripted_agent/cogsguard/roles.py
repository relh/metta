from __future__ import annotations

from cogames_agents.policy.scripted_agent.cogsguard.policy import CogsguardPolicy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class _CogsguardRolePolicy(CogsguardPolicy):
    role_name: str = ""

    def __init__(self, policy_env_info: PolicyEnvInterface, device: str = "cpu", **_ignored: int) -> None:
        super().__init__(policy_env_info, device=device, **{self.role_name: policy_env_info.num_agents})


class MinerPolicy(_CogsguardRolePolicy):
    short_names = ["miner"]
    role_name = "miner"


class ScoutPolicy(_CogsguardRolePolicy):
    short_names = ["scout"]
    role_name = "scout"


class AlignerPolicy(_CogsguardRolePolicy):
    short_names = ["aligner"]
    role_name = "aligner"


class ScramblerPolicy(_CogsguardRolePolicy):
    short_names = ["scrambler"]
    role_name = "scrambler"
