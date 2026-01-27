"""CoGsGuard scripted agent with role-based behavior."""

from .control_agent import CogsguardControlAgent
from .policy import CogsguardPolicy, CogsguardWomboPolicy
from .roles import AlignerPolicy, MinerPolicy, ScoutPolicy, ScramblerPolicy
from .targeted_agent import CogsguardTargetedAgent
from .teacher import CogsguardTeacherPolicy
from .v2_agent import CogsguardV2Agent

__all__ = [
    "CogsguardControlAgent",
    "CogsguardPolicy",
    "CogsguardWomboPolicy",
    "CogsguardTargetedAgent",
    "CogsguardTeacherPolicy",
    "CogsguardV2Agent",
    "MinerPolicy",
    "ScoutPolicy",
    "AlignerPolicy",
    "ScramblerPolicy",
]
