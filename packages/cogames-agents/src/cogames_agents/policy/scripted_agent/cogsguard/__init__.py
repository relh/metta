"""CoGsGuard scripted agent with role-based behavior."""

from cogames_agents.policy.evolution.cogsguard.evolution import (
    BehaviorDef,
    BehaviorSource,
    EvolutionConfig,
    RoleCatalog,
    RoleDef,
    RoleTier,
    TierSelection,
    materialize_role_behaviors,
    mutate_role,
    pick_role_id_weighted,
    recombine_roles,
    record_behavior_score,
    record_role_score,
    sample_role,
)
from cogames_agents.policy.evolution.cogsguard.evolutionary_coordinator import (
    EvolutionaryRoleCoordinator,
)
from cogames_agents.policy.scripted_agent.cogsguard.behavior_hooks import build_cogsguard_behavior_hooks
from cogames_agents.policy.scripted_agent.cogsguard.control_agent import CogsguardControlAgent
from cogames_agents.policy.scripted_agent.cogsguard.policy import CogsguardPolicy, CogsguardWomboPolicy
from cogames_agents.policy.scripted_agent.cogsguard.roles import (
    AlignerPolicy,
    MinerPolicy,
    ScoutPolicy,
    ScramblerPolicy,
)
from cogames_agents.policy.scripted_agent.cogsguard.targeted_agent import CogsguardTargetedAgent
from cogames_agents.policy.scripted_agent.cogsguard.v2_agent import CogsguardV2Agent

try:
    from cogames_agents.policy.scripted_agent.cogsguard.teacher import CogsguardTeacherPolicy
except ModuleNotFoundError as exc:  # pragma: no cover - optional for environments without nim agents
    if exc.name and exc.name.startswith("cogames_agents.policy.nim_agents"):
        CogsguardTeacherPolicy = None
    else:
        raise

__all__ = [
    "CogsguardControlAgent",
    "CogsguardPolicy",
    "CogsguardWomboPolicy",
    "CogsguardTargetedAgent",
    "CogsguardV2Agent",
    "MinerPolicy",
    "ScoutPolicy",
    "AlignerPolicy",
    "ScramblerPolicy",
    # Evolution types
    "BehaviorDef",
    "BehaviorSource",
    "EvolutionConfig",
    "RoleCatalog",
    "RoleDef",
    "RoleTier",
    "TierSelection",
    # Evolution functions
    "materialize_role_behaviors",
    "mutate_role",
    "pick_role_id_weighted",
    "recombine_roles",
    "record_behavior_score",
    "record_role_score",
    "sample_role",
    # Coordinator + hooks
    "EvolutionaryRoleCoordinator",
    "build_cogsguard_behavior_hooks",
]

if CogsguardTeacherPolicy is not None:
    __all__.append("CogsguardTeacherPolicy")
