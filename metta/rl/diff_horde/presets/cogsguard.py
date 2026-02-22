from __future__ import annotations

import json
from typing import Literal, Sequence, cast

from metta.rl.diff_horde.cumulants import DiffHordeCumulantsConfig

CogsGuardHordeVariant = Literal[
    "action_counters",
    "all",
    "cortex_core",
    "economy_agent",
    "economy_team",
    "economy_flow",
    "junctions",
    "junction_events",
    "roles",
    "tempo",
    "vitals",
]

_CONCRETE_HORDE_VARIANTS: tuple[CogsGuardHordeVariant, ...] = (
    "junctions",
    "vitals",
    "roles",
    "cortex_core",
    "economy_agent",
    "economy_team",
    "tempo",
    "junction_events",
    "economy_flow",
    "action_counters",
)

AVAILABLE_HORDE_VARIANTS: tuple[CogsGuardHordeVariant, ...] = (
    "all",
    *_CONCRETE_HORDE_VARIANTS,
)


def _info_scalar(key: str) -> dict[str, object]:
    return {"kind": "info_scalar", "key": key}


_HORDE_VARIANT_SPECS: dict[CogsGuardHordeVariant, dict[str, dict[str, object]]] = {
    "junctions": {
        "cogs_junction_now": _info_scalar("env_team/cogs/aligned.junction"),
        "clips_junction_now": _info_scalar("env_team/clips/aligned.junction"),
    },
    "vitals": {
        "hp_now": _info_scalar("agent/hp.amount"),
        "energy_now": _info_scalar("agent/energy.amount"),
        "influence_now": _info_scalar("agent/influence.amount"),
        "solar_now": _info_scalar("agent/solar.amount"),
    },
    "roles": {
        "miner_gear_now": _info_scalar("agent/miner.amount"),
        "aligner_gear_now": _info_scalar("agent/aligner.amount"),
        "scrambler_gear_now": _info_scalar("agent/scrambler.amount"),
        "scout_gear_now": _info_scalar("agent/scout.amount"),
    },
    "cortex_core": {
        "cortex_core": {"kind": "td_key", "key": "core"},
    },
    "economy_agent": {
        "carbon_cargo_now": _info_scalar("agent/carbon.amount"),
        "oxygen_cargo_now": _info_scalar("agent/oxygen.amount"),
        "germanium_cargo_now": _info_scalar("agent/germanium.amount"),
        "silicon_cargo_now": _info_scalar("agent/silicon.amount"),
        "heart_cargo_now": _info_scalar("agent/heart.amount"),
    },
    "economy_team": {
        "team_carbon_now": _info_scalar("env_team/cogs/carbon.amount"),
        "team_oxygen_now": _info_scalar("env_team/cogs/oxygen.amount"),
        "team_germanium_now": _info_scalar("env_team/cogs/germanium.amount"),
        "team_silicon_now": _info_scalar("env_team/cogs/silicon.amount"),
        "team_heart_now": _info_scalar("env_team/cogs/heart.amount"),
    },
    "tempo": {
        "step_now": _info_scalar("env_attributes/steps"),
        "max_steps_now": _info_scalar("env_attributes/max_steps"),
        "reward_step_now": _info_scalar("agent/reward_step"),
    },
    "junction_events": {
        "cogs_junction_gained": _info_scalar("env_team/cogs/aligned.junction.gained"),
        "cogs_junction_lost": _info_scalar("env_team/cogs/aligned.junction.lost"),
        "clips_junction_gained": _info_scalar("env_team/clips/aligned.junction.gained"),
        "clips_junction_lost": _info_scalar("env_team/clips/aligned.junction.lost"),
        "aligned_by_agent": _info_scalar("agent/junction.aligned_by_agent"),
        "scrambled_by_agent": _info_scalar("agent/junction.scrambled_by_agent"),
    },
    "economy_flow": {
        "carbon_gained": _info_scalar("agent/carbon.gained"),
        "oxygen_gained": _info_scalar("agent/oxygen.gained"),
        "germanium_gained": _info_scalar("agent/germanium.gained"),
        "silicon_gained": _info_scalar("agent/silicon.gained"),
        "heart_gained": _info_scalar("agent/heart.gained"),
        "heart_lost": _info_scalar("agent/heart.lost"),
        "miner_gained": _info_scalar("agent/miner.gained"),
        "miner_lost": _info_scalar("agent/miner.lost"),
        "aligner_gained": _info_scalar("agent/aligner.gained"),
        "aligner_lost": _info_scalar("agent/aligner.lost"),
        "scrambler_gained": _info_scalar("agent/scrambler.gained"),
        "scrambler_lost": _info_scalar("agent/scrambler.lost"),
        "scout_gained": _info_scalar("agent/scout.gained"),
        "scout_lost": _info_scalar("agent/scout.lost"),
        "team_carbon_deposited": _info_scalar("env_team/cogs/carbon.deposited"),
        "team_oxygen_deposited": _info_scalar("env_team/cogs/oxygen.deposited"),
        "team_germanium_deposited": _info_scalar("env_team/cogs/germanium.deposited"),
        "team_silicon_deposited": _info_scalar("env_team/cogs/silicon.deposited"),
        "team_carbon_withdrawn": _info_scalar("env_team/cogs/carbon.withdrawn"),
        "team_oxygen_withdrawn": _info_scalar("env_team/cogs/oxygen.withdrawn"),
        "team_germanium_withdrawn": _info_scalar("env_team/cogs/germanium.withdrawn"),
        "team_silicon_withdrawn": _info_scalar("env_team/cogs/silicon.withdrawn"),
    },
    "action_counters": {
        "move_success": _info_scalar("agent/action.move.success"),
        "move_failed": _info_scalar("agent/action.move.failed"),
        "noop_success": _info_scalar("agent/action.noop.success"),
        "change_vibe_success": _info_scalar("agent/action.change_vibe.success"),
        "action_failed": _info_scalar("agent/action.failed"),
        "cell_visited": _info_scalar("agent/cell.visited"),
    },
}


def normalize_horde_variant_names(variants: str | Sequence[str] | None) -> list[str]:
    if variants is None:
        return []
    if isinstance(variants, str):
        if variants.startswith("["):
            parsed = json.loads(variants)
            if isinstance(parsed, list):
                return [str(name) for name in parsed]
        return [variants]
    return list(variants)


def resolve_cogsguard_horde_cumulants(variants: str | Sequence[str] | None) -> DiffHordeCumulantsConfig | None:
    variant_names = normalize_horde_variant_names(variants)
    if not variant_names:
        return None

    resolved: list[CogsGuardHordeVariant] = []
    for variant_name in variant_names:
        if variant_name not in AVAILABLE_HORDE_VARIANTS:
            available = ", ".join(AVAILABLE_HORDE_VARIANTS)
            raise ValueError(f"Unknown CogsGuard horde variant '{variant_name}'. Available: {available}")
        variant = cast(CogsGuardHordeVariant, variant_name)
        expanded = _CONCRETE_HORDE_VARIANTS if variant == "all" else (variant,)
        for expanded_variant in expanded:
            if expanded_variant in resolved:
                continue
            resolved.append(expanded_variant)

    merged_specs: dict[str, dict[str, object]] = {}
    for variant in resolved:
        merged_specs.update(_HORDE_VARIANT_SPECS[variant])
    return DiffHordeCumulantsConfig.model_validate(merged_specs)
