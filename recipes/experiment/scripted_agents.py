"""Recipe for running scripted agents by registry name."""

from __future__ import annotations

from typing import Optional, Sequence

from cogames_agents.policy.scripted_registry import resolve_scripted_agent_uri

from metta.sim.simulation_config import SimulationConfig
from metta.tools.eval import EvaluateTool
from metta.tools.play import PlayTool
from metta.tools.replay import ReplayTool


def _resolve_simulations(
    suite: str,
    variants: str | Sequence[str] | None = None,
) -> list[SimulationConfig]:
    if suite == "cogsguard":
        from recipes.experiment import cogsguard  # noqa: PLC0415

        return cogsguard.simulations(variants=variants)
    if suite == "cvc_arena":
        from recipes.experiment import cvc_arena  # noqa: PLC0415

        return cvc_arena.simulations()
    if suite == "arena":
        from recipes.experiment import arena  # noqa: PLC0415

        return arena.simulations()
    raise ValueError("Unknown suite. Choose from: arena, cvc_arena, cogsguard")


def _resolve_policy_uri(agent: Optional[str], policy_uri: Optional[str]) -> str:
    if agent and policy_uri:
        raise ValueError("Specify only one of agent or policy_uri.")
    if policy_uri:
        return policy_uri
    return resolve_scripted_agent_uri(agent or "thinky")


def play(
    agent: Optional[str] = None,
    policy_uri: Optional[str] = None,
    suite: str = "cogsguard",
    variants: str | Sequence[str] | None = None,
) -> PlayTool:
    """Play a single scripted agent by registry name."""
    sim = _resolve_simulations(suite, variants=variants)[0]
    return PlayTool(sim=sim, policy_uri=_resolve_policy_uri(agent, policy_uri))


def replay(
    agent: Optional[str] = None,
    policy_uri: Optional[str] = None,
    suite: str = "cogsguard",
    variants: str | Sequence[str] | None = None,
) -> ReplayTool:
    """Replay a scripted agent by registry name."""
    sim = _resolve_simulations(suite, variants=variants)[0]
    return ReplayTool(sim=sim, policy_uri=_resolve_policy_uri(agent, policy_uri))


def evaluate(
    agent: Optional[str] = None,
    policy_uri: Optional[str] = None,
    suite: str = "cogsguard",
    variants: str | Sequence[str] | None = None,
) -> EvaluateTool:
    """Evaluate a scripted agent by registry name."""
    sims = _resolve_simulations(suite, variants=variants)
    return EvaluateTool(simulations=sims, policy_uris=_resolve_policy_uri(agent, policy_uri))
