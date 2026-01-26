"""CogsGuard scripted policy with a tuned default role mix."""

from __future__ import annotations

from typing import Any

from mettagrid.policy.policy_env_interface import PolicyEnvInterface

from .policy import CogsguardPolicy


def _default_role_counts(num_agents: int) -> dict[str, int]:
    if num_agents <= 1:
        return {"miner": 1}
    if num_agents == 2:
        return {"scrambler": 1, "miner": 1}
    if num_agents == 3:
        return {"scrambler": 1, "miner": 1, "scout": 1}
    if num_agents <= 7:
        scramblers = 1
        aligners = 1
        scouts = 1
    else:
        scramblers = max(2, num_agents // 6)
        aligners = max(2, num_agents // 6)
        scouts = 1
    miners = max(1, num_agents - scramblers - scouts - aligners)
    return {
        "scrambler": scramblers,
        "aligner": aligners,
        "miner": miners,
        "scout": scouts,
    }


class CogsguardV2Agent(CogsguardPolicy):
    """Scripted cogsguard policy with better default role allocation."""

    short_names = ["cogsguard_v2"]

    def __init__(
        self,
        policy_env_info: PolicyEnvInterface,
        device: str = "cpu",
        **vibe_counts: Any,
    ):
        if not any(isinstance(v, int) for v in vibe_counts.values()):
            vibe_counts = {**vibe_counts, **_default_role_counts(policy_env_info.num_agents)}
        super().__init__(policy_env_info, device=device, **vibe_counts)
