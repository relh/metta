"""Miner goals — pick resource, mine, deposit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext

# Resource types that can be mined
RESOURCE_TYPES = ["carbon", "oxygen", "germanium", "silicon"]


class PickResourceGoal(Goal):
    """Select a target resource and write to blackboard."""

    name = "PickResource"

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return "target_resource" in ctx.blackboard

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Pick the resource with the most available extractors
        best_resource = None
        best_count = -1

        for resource in RESOURCE_TYPES:
            extractors = ctx.map.find(type=f"{resource}_extractor")
            # Filter to usable ones (and not recently failed)
            usable = [
                (pos, e)
                for pos, e in extractors
                if e.properties.get("remaining_uses", 999) > 0
                and e.properties.get("inventory_amount", -1) != 0
                and not _extractor_recently_failed(ctx, pos)
            ]
            if len(usable) > best_count:
                best_count = len(usable)
                best_resource = resource

        if best_resource is None:
            # No extractors known — default to carbon
            best_resource = "carbon"

        ctx.blackboard["target_resource"] = best_resource
        # Return noop — next tick will pick up the mining goal
        return Action(name="noop")


def _extractor_recently_failed(ctx: PlankyContext, pos: tuple[int, int]) -> bool:
    """Check if we recently failed to mine from this extractor."""
    failed_step = ctx.blackboard.get(f"mine_failed_{pos}", -9999)
    return ctx.step - failed_step < 100  # 100 step cooldown


class DepositCargoGoal(Goal):
    """Deposit resources at nearest cogs-aligned building when cargo is full.

    Tracks attempts and marks depots as failed if cargo doesn't decrease.
    """

    name = "DepositCargo"
    MAX_ATTEMPTS_PER_DEPOT = 5

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        return ctx.state.cargo_total < ctx.state.cargo_capacity

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Track cargo to detect successful deposit
        prev_cargo = ctx.blackboard.get("prev_deposit_cargo", ctx.state.cargo_total)
        current_cargo = ctx.state.cargo_total
        ctx.blackboard["prev_deposit_cargo"] = current_cargo

        # Find nearest cogs depot
        depot_pos = _find_cogs_depot(ctx)
        if depot_pos is None:
            return ctx.navigator.explore(ctx.state.position, ctx.map)

        if ctx.trace:
            ctx.trace.nav_target = depot_pos

        dist = _manhattan(ctx.state.position, depot_pos)
        if dist <= 1:
            # Adjacent to depot - track attempts
            attempts_key = f"deposit_attempts_{depot_pos}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1

            # Reset if cargo decreased (deposit succeeded)
            if current_cargo < prev_cargo:
                ctx.blackboard[attempts_key] = 0
            else:
                ctx.blackboard[attempts_key] = attempts

                if attempts > self.MAX_ATTEMPTS_PER_DEPOT:
                    # Mark as failed temporarily
                    ctx.blackboard[f"deposit_failed_{depot_pos}"] = ctx.step
                    ctx.blackboard[attempts_key] = 0
                    if ctx.trace:
                        ctx.trace.activate(self.name, f"giving up on {depot_pos}")
                    return ctx.navigator.explore(ctx.state.position, ctx.map)

            return _move_toward(ctx.state.position, depot_pos)

        # Not adjacent - reset attempts
        ctx.blackboard[f"deposit_attempts_{depot_pos}"] = 0
        return ctx.navigator.get_action(ctx.state.position, depot_pos, ctx.map, reach_adjacent=True)


class MineResourceGoal(Goal):
    """Navigate to extractor for target_resource and bump it.

    Tracks attempts at each extractor and marks them as failed if
    cargo doesn't increase after several bumps (extractor empty/broken).
    """

    name = "MineResource"
    MAX_ATTEMPTS_PER_EXTRACTOR = 5

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Never satisfied while we have cargo space — keep mining
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        target_resource = ctx.blackboard.get("target_resource", "carbon")

        # Track cargo to detect successful mining
        prev_cargo = ctx.blackboard.get("prev_cargo", 0)
        current_cargo = ctx.state.cargo_total
        ctx.blackboard["prev_cargo"] = current_cargo

        # Find nearest usable extractor for this resource
        target_pos = self._find_extractor(ctx, target_resource)

        if target_pos is None:
            # Try any resource type
            for resource in RESOURCE_TYPES:
                if resource == target_resource:
                    continue
                target_pos = self._find_extractor(ctx, resource)
                if target_pos:
                    ctx.blackboard["target_resource"] = resource
                    break

        if target_pos is None:
            # No extractors found — explore
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
            )

        if ctx.trace:
            ctx.trace.nav_target = target_pos

        dist = _manhattan(ctx.state.position, target_pos)
        if dist <= 1:
            # Adjacent to extractor — track attempts
            attempts_key = f"mine_attempts_{target_pos}"
            attempts = ctx.blackboard.get(attempts_key, 0) + 1

            # Reset attempts if cargo increased (mining succeeded)
            if current_cargo > prev_cargo:
                ctx.blackboard[attempts_key] = 0
            else:
                ctx.blackboard[attempts_key] = attempts

                if attempts > self.MAX_ATTEMPTS_PER_EXTRACTOR:
                    # Mark as failed
                    ctx.blackboard[f"mine_failed_{target_pos}"] = ctx.step
                    ctx.blackboard[attempts_key] = 0
                    if ctx.trace:
                        ctx.trace.activate(self.name, f"giving up on {target_pos}")
                    return ctx.navigator.explore(
                        ctx.state.position,
                        ctx.map,
                        direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                    )

            return _move_toward(ctx.state.position, target_pos)

        # Not adjacent - reset attempts
        ctx.blackboard[f"mine_attempts_{target_pos}"] = 0
        return ctx.navigator.get_action(ctx.state.position, target_pos, ctx.map, reach_adjacent=True)

    def _find_extractor(self, ctx: PlankyContext, resource: str) -> Optional[tuple[int, int]]:
        """Find nearest usable extractor for a resource type."""
        extractors = ctx.map.find(type=f"{resource}_extractor")
        usable = [
            (pos, e)
            for pos, e in extractors
            if e.properties.get("remaining_uses", 999) > 0
            and e.properties.get("inventory_amount", -1) != 0
            and not _extractor_recently_failed(ctx, pos)
        ]

        if not usable:
            return None

        # Sort by distance
        usable.sort(key=lambda x: _manhattan(ctx.state.position, x[0]))
        return usable[0][0]


def _find_cogs_depot(ctx: PlankyContext) -> tuple[int, int] | None:
    """Find nearest cogs-aligned depot (assembler or cogs junction)."""
    pos = ctx.state.position

    def recently_failed(p: tuple[int, int]) -> bool:
        failed_step = ctx.blackboard.get(f"deposit_failed_{p}", -9999)
        return ctx.step - failed_step < 100

    candidates: list[tuple[int, tuple[int, int]]] = []

    for apos, _ in ctx.map.find(type="assembler"):
        if not recently_failed(apos):
            candidates.append((_manhattan(pos, apos), apos))
    for jpos, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
        if not recently_failed(jpos):
            candidates.append((_manhattan(pos, jpos), jpos))
    for cpos, _ in ctx.map.find(type_contains="charger", property_filter={"alignment": "cogs"}):
        if not recently_failed(cpos):
            candidates.append((_manhattan(pos, cpos), cpos))

    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


def _move_toward(current: tuple[int, int], target: tuple[int, int]) -> Action:
    dr = target[0] - current[0]
    dc = target[1] - current[1]
    if abs(dr) >= abs(dc):
        if dr > 0:
            return Action(name="move_south")
        elif dr < 0:
            return Action(name="move_north")
    if dc > 0:
        return Action(name="move_east")
    elif dc < 0:
        return Action(name="move_west")
    return Action(name="move_north")
