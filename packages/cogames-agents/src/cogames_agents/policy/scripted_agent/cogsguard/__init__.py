"""CoGsGuard scripted agent with role-based behavior."""

from .control_agent import CogsguardControlAgent
from .policy import CogsguardPolicy, CogsguardWomboMixPolicy, CogsguardWomboPolicy
from .roles import AlignerPolicy, MinerPolicy, ScoutPolicy, ScramblerPolicy
from .targeted_agent import CogsguardTargetedAgent
from .v2_agent import CogsguardV2Agent

try:
    from .teacher import CogsguardTeacherPolicy
except (ImportError, ValueError):
    CogsguardTeacherPolicy = None

__all__ = [
    "CogsguardControlAgent",
    "CogsguardPolicy",
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
