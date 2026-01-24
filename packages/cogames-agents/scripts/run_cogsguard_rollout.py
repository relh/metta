#!/usr/bin/env -S uv run
"""Run a short CoGsGuard scripted rollout and sanity-check structure discovery."""

from __future__ import annotations

import argparse
from typing import Iterable

from cogames_agents.policy.scripted_agent.cogsguard.debug_agent import DebugHarness
from cogames_agents.policy.scripted_agent.cogsguard.types import StructureType


def _is_assembler_tag(name: str, tags: Iterable[str]) -> bool:
    tag_set = set(tags)
    return name in {"assembler", "main_nexus", "hub"} or bool({"assembler", "main_nexus", "hub"} & tag_set)


def _is_charger_tag(name: str, tags: Iterable[str]) -> bool:
    combined = {name, *tags}
    return any("charger" in tag or "supply_depot" in tag or "junction" in tag for tag in combined)


def _has_alignment_tag(name: str, tags: Iterable[str]) -> bool:
    combined = {name, *tags}
    return any("cogs" in tag or "clips" in tag for tag in combined)


def run_rollout(
    *,
    steps: int,
    num_agents: int,
    max_steps: int,
    seed: int,
    recipe_module: str,
    policy_uri: str,
    allow_missing_roles: bool,
) -> int:
    harness = DebugHarness.from_recipe(
        recipe_module=recipe_module,
        num_agents=num_agents,
        max_steps=max_steps,
        seed=seed,
        policy_uri=policy_uri,
    )

    assembler_seen = False
    assembler_missing = 0
    charger_alignment_checks = 0
    charger_alignment_mismatches = 0
    neutral_charger_checks = 0
    neutral_charger_mismatches = 0
    expected_roles = {"miner", "scout", "aligner", "scrambler"}
    observed_roles: set[str] = set()

    role_stats = {
        "miner": {
            "agents": set(),
            "gear_seen": False,
            "mine_attempts": 0,
            "mine_mismatches": 0,
            "deposit_attempts": 0,
        },
        "scout": {
            "agents": set(),
            "gear_seen": False,
            "unique_positions": {},
            "max_structures_seen": 0,
        },
        "aligner": {
            "agents": set(),
            "gear_seen": False,
            "align_attempts": 0,
            "align_mismatches": 0,
            "align_cogs_targets": 0,
        },
        "scrambler": {
            "agents": set(),
            "gear_seen": False,
            "scramble_attempts": 0,
            "scramble_mismatches": 0,
            "scramble_cogs_targets": 0,
        },
    }

    last_pending_action: dict[int, str | None] = {}
    last_cargo: dict[int, int] = {}

    for _ in range(steps):
        harness.step(1)
        for agent_id in range(harness.num_agents):
            policy = harness.agent_policies[agent_id]
            base_policy = policy._base_policy if hasattr(policy, "_base_policy") else policy
            state = harness.get_agent_state(agent_id)
            if state is None or state.current_obs is None:
                continue
            role = state.role.value if hasattr(state.role, "value") else str(state.role)
            if role in role_stats:
                observed_roles.add(role)
                role_stats[role]["agents"].add(agent_id)
                if state.has_gear():
                    role_stats[role]["gear_seen"] = True
            parsed = base_policy._parse_observation(state, state.current_obs)
            for pos, obj_state in parsed.nearby_objects.items():
                obj_name = obj_state.name.lower()
                obj_tags = [tag.lower() for tag in obj_state.tags]

                if _is_assembler_tag(obj_name, obj_tags):
                    assembler_seen = True
                    if state.stations.get("assembler") is None:
                        assembler_missing += 1

                if not _is_charger_tag(obj_name, obj_tags):
                    continue

                expected_alignment = None
                if _has_alignment_tag(obj_name, obj_tags):
                    if any("cogs" in tag for tag in obj_tags):
                        expected_alignment = "cogs"
                    elif any("clips" in tag for tag in obj_tags):
                        expected_alignment = "clips"
                elif obj_state.clipped > 0:
                    expected_alignment = "clips"

                struct = state.structures.get(pos)
                if struct is None or struct.structure_type != StructureType.CHARGER:
                    continue

                if expected_alignment is not None:
                    charger_alignment_checks += 1
                    if struct.alignment != expected_alignment:
                        charger_alignment_mismatches += 1
                    continue

                neutral_charger_checks += 1
                if struct.alignment == "clips":
                    neutral_charger_mismatches += 1

            if role == "scout":
                positions = role_stats["scout"]["unique_positions"].setdefault(agent_id, set())
                positions.add((state.row, state.col))
                role_stats["scout"]["max_structures_seen"] = max(
                    role_stats["scout"]["max_structures_seen"],
                    len(state.structures),
                )

            if role == "miner":
                current_cargo = state.total_cargo
                previous_cargo = last_cargo.get(agent_id, current_cargo)
                if current_cargo < previous_cargo:
                    aligned_positions: list[tuple[int, int]] = []
                    assembler_pos = state.stations.get("assembler")
                    if assembler_pos is not None:
                        aligned_positions.append(assembler_pos)
                    for charger in state.get_structures_by_type(StructureType.CHARGER):
                        if charger.alignment == "cogs":
                            aligned_positions.append(charger.position)
                    if aligned_positions:
                        dist = min(abs(state.row - pos[0]) + abs(state.col - pos[1]) for pos in aligned_positions)
                        if dist <= 1:
                            role_stats["miner"]["deposit_attempts"] += 1
                last_cargo[agent_id] = current_cargo

            current_pending = getattr(state, "_pending_action_type", None)
            previous_pending = last_pending_action.get(agent_id)
            if current_pending != previous_pending:
                last_pending_action[agent_id] = current_pending
                target = getattr(state, "_pending_action_target", None)
                target_struct = state.structures.get(target) if target else None

                if current_pending == "mine" and role == "miner":
                    role_stats["miner"]["mine_attempts"] += 1
                    if target_struct is None or target_struct.structure_type != StructureType.EXTRACTOR:
                        role_stats["miner"]["mine_mismatches"] += 1

                if current_pending == "align" and role == "aligner":
                    role_stats["aligner"]["align_attempts"] += 1
                    if target_struct is None or target_struct.structure_type != StructureType.CHARGER:
                        role_stats["aligner"]["align_mismatches"] += 1
                    elif target_struct.alignment == "cogs":
                        role_stats["aligner"]["align_cogs_targets"] += 1

                if current_pending == "scramble" and role == "scrambler":
                    role_stats["scrambler"]["scramble_attempts"] += 1
                    if target_struct is None or target_struct.structure_type != StructureType.CHARGER:
                        role_stats["scrambler"]["scramble_mismatches"] += 1
                    elif target_struct.alignment == "cogs":
                        role_stats["scrambler"]["scramble_cogs_targets"] += 1

    print("Cogsguard rollout sanity check")
    print(f"- steps: {steps}")
    print(f"- assembler seen: {assembler_seen}")
    print(f"- assembler missing in stations: {assembler_missing}")
    print(f"- tagged/clipped chargers checked: {charger_alignment_checks}")
    print(f"- tagged/clipped charger mismatches: {charger_alignment_mismatches}")
    print(f"- neutral chargers checked: {neutral_charger_checks}")
    print(f"- neutral chargers flagged as clips: {neutral_charger_mismatches}")
    print(f"- observed roles: {sorted(observed_roles)}")
    print("Role behavior checks")
    print(
        f"- miner: agents={len(role_stats['miner']['agents'])} "
        f"gear_seen={role_stats['miner']['gear_seen']} "
        f"mine_attempts={role_stats['miner']['mine_attempts']} "
        f"mine_mismatches={role_stats['miner']['mine_mismatches']} "
        f"deposit_attempts={role_stats['miner']['deposit_attempts']}"
    )
    scout_positions = [len(pos) for pos in role_stats["scout"]["unique_positions"].values()]
    print(
        f"- scout: agents={len(role_stats['scout']['agents'])} "
        f"gear_seen={role_stats['scout']['gear_seen']} "
        f"unique_positions={scout_positions} "
        f"max_structures_seen={role_stats['scout']['max_structures_seen']}"
    )
    print(
        f"- aligner: agents={len(role_stats['aligner']['agents'])} "
        f"gear_seen={role_stats['aligner']['gear_seen']} "
        f"align_attempts={role_stats['aligner']['align_attempts']} "
        f"align_mismatches={role_stats['aligner']['align_mismatches']} "
        f"align_cogs_targets={role_stats['aligner']['align_cogs_targets']}"
    )
    print(
        f"- scrambler: agents={len(role_stats['scrambler']['agents'])} "
        f"gear_seen={role_stats['scrambler']['gear_seen']} "
        f"scramble_attempts={role_stats['scrambler']['scramble_attempts']} "
        f"scramble_mismatches={role_stats['scrambler']['scramble_mismatches']} "
        f"scramble_cogs_targets={role_stats['scrambler']['scramble_cogs_targets']}"
    )

    if assembler_seen and assembler_missing:
        return 1
    if charger_alignment_mismatches:
        return 1
    if neutral_charger_mismatches:
        return 1
    if not allow_missing_roles:
        if expected_roles - observed_roles:
            return 1
        if role_stats["miner"]["mine_attempts"] == 0 or role_stats["miner"]["mine_mismatches"] > 0:
            return 1
        if role_stats["miner"]["deposit_attempts"] == 0:
            return 1
        if role_stats["aligner"]["align_attempts"] == 0 or role_stats["aligner"]["align_mismatches"] > 0:
            return 1
        if role_stats["aligner"]["align_cogs_targets"] > 0:
            return 1
        if role_stats["scrambler"]["scramble_attempts"] == 0 or role_stats["scrambler"]["scramble_mismatches"] > 0:
            return 1
        if role_stats["scrambler"]["scramble_cogs_targets"] > 0:
            return 1
        if role_stats["scout"]["max_structures_seen"] < 5:
            return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--agents", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--recipe", default="recipes.experiment.cogsguard")
    parser.add_argument(
        "--policy-uri",
        default="metta://policy/cogsguard?miner=4&scout=2&aligner=2&scrambler=2",
    )
    parser.add_argument("--allow-missing-roles", action="store_true")
    args = parser.parse_args()

    return run_rollout(
        steps=args.steps,
        num_agents=args.agents,
        max_steps=args.max_steps,
        seed=args.seed,
        recipe_module=args.recipe,
        policy_uri=args.policy_uri,
        allow_missing_roles=args.allow_missing_roles,
    )


if __name__ == "__main__":
    raise SystemExit(main())
