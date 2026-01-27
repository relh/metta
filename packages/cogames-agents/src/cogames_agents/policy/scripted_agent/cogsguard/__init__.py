"""CoGsGuard scripted agent with role-based behavior."""

from .control_agent import CogsguardControlAgent
from .policy import CogsguardPolicy, CogsguardRosterPolicy, CogsguardWomboMixPolicy, CogsguardWomboPolicy
from .roles import AlignerPolicy, MinerPolicy, ScoutPolicy, ScramblerPolicy
from .targeted_agent import CogsguardTargetedAgent
from .v2_agent import CogsguardV2Agent

try:
    from .teacher import CogsguardTeacherPolicy
except ModuleNotFoundError as exc:  # pragma: no cover - optional for environments without nim agents
    if exc.name and exc.name.startswith("cogames_agents.policy.nim_agents"):
        CogsguardTeacherPolicy = None
    else:
        raise

__all__ = [
    "CogsguardControlAgent",
    "CogsguardPolicy",
    "CogsguardRosterPolicy",
    "CogsguardWomboMixPolicy",
    "CogsguardWomboPolicy",
    "CogsguardTargetedAgent",
    "CogsguardV2Agent",
    "MinerPolicy",
    "ScoutPolicy",
    "AlignerPolicy",
    "ScramblerPolicy",
]

if CogsguardTeacherPolicy is not None:
    __all__.append("CogsguardTeacherPolicy")
