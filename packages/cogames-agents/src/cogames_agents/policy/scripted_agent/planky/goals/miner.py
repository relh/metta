"""Miner goals — pick resource, mine, deposit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from cogames_agents.policy.scripted_agent.planky.goal import Goal
from cogames_agents.policy.scripted_agent.planky.navigator import _manhattan
from mettagrid.simulator import Action

from .gear import GetGearGoal

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext


class GetMinerGearGoal(GetGearGoal):
    """Get miner gear (costs C1 O1 G3 S1 from collective).

    Miners always get gear regardless of reserves — they produce resources.
    Gear provides 10x cargo capacity (40 vs 4), so always worth getting if affordable.
    """

    def __init__(self) -> None:
        super().__init__(
            gear_attr="miner_gear",
            station_type="miner_station",
            goal_name="GetMinerGear",
            gear_cost={"carbon": 1, "oxygen": 1, "germanium": 3, "silicon": 1},
        )

    def _collective_can_afford(self, ctx: "PlankyContext") -> bool:
        """Miners always get gear if affordable — 10x cargo capacity is worth it.

        Even if collective is well-stocked, get gear to mine more efficiently.
        """
        if not self._gear_cost:
            return True
        s = ctx.state
        collective = {
            "carbon": s.collective_carbon,
            "oxygen": s.collective_oxygen,
            "germanium": s.collective_germanium,
            "silicon": s.collective_silicon,
        }
        # No reserve requirement for miners — just need the cost
        return all(collective.get(res, 0) >= amt for res, amt in self._gear_cost.items())


# Resource types that can be mined
RESOURCE_TYPES = ["carbon", "oxygen", "germanium", "silicon"]

# When the collective has more than this amount of every resource, stop mining.
COLLECTIVE_SUFFICIENT_THRESHOLD = 100


def _collective_resources_sufficient(ctx: "PlankyContext") -> bool:
    """Return True when the collective has >COLLECTIVE_SUFFICIENT_THRESHOLD of every resource."""
    s = ctx.state
    return (
        s.collective_carbon > COLLECTIVE_SUFFICIENT_THRESHOLD
        and s.collective_oxygen > COLLECTIVE_SUFFICIENT_THRESHOLD
        and s.collective_germanium > COLLECTIVE_SUFFICIENT_THRESHOLD
        and s.collective_silicon > COLLECTIVE_SUFFICIENT_THRESHOLD
    )


class ExploreHubGoal(Goal):
    """Explore the hub to discover all 4 extractors before mining.

    Extractors are at hub corners: (±5, ±5) from center.
    Each miner visits corners in a rotated order based on agent_id.
    """

    name = "ExploreHub"
    # Hub corner offsets from SPAWN_POS — extractors at these positions
    HUB_OFFSETS = [(-5, -5), (-5, 5), (5, 5), (5, -5)]

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        found = sum(1 for r in RESOURCE_TYPES if ctx.map.find(type=f"{r}_extractor"))
        if found >= 4:
            return True
        # Time limit: don't explore forever
        if ctx.step > 15:
            return True
        return False

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        from cogames_agents.policy.scripted_agent.planky.policy import SPAWN_POS  # noqa: PLC0415

        corner_idx = ctx.blackboard.get("_hub_corner_idx", ctx.agent_id % 4)
        offsets = self.HUB_OFFSETS
        target = (SPAWN_POS[0] + offsets[corner_idx][0], SPAWN_POS[1] + offsets[corner_idx][1])

        dist = _manhattan(ctx.state.position, target)
        if dist <= 2:
            corner_idx = (corner_idx + 1) % 4
            ctx.blackboard["_hub_corner_idx"] = corner_idx
            target = (SPAWN_POS[0] + offsets[corner_idx][0], SPAWN_POS[1] + offsets[corner_idx][1])

        if ctx.trace:
            ctx.trace.nav_target = target
            found = sum(1 for r in RESOURCE_TYPES if ctx.map.find(type=f"{r}_extractor"))
            ctx.trace.activate(self.name, f"corner={corner_idx} found={found}/4")

        return ctx.navigator.get_action(ctx.state.position, target, ctx.map, reach_adjacent=True)


class PickResourceGoal(Goal):
    """Select a target resource based on collective needs.

    Priority order:
    1. Resources below COLLECTIVE_SUFFICIENT_THRESHOLD (100) — mine the lowest
    2. If all above threshold, pick the one we have least of (for balance)

    Bottleneck switching: If current target is >20% above mean and any element
    is <10% below mean, switch to the bottleneck element to keep resources balanced.
    Re-evaluates every 50 steps, or immediately if a resource is critically low.
    """

    name = "PickResource"
    REEVALUATE_INTERVAL = 50
    CRITICAL_THRESHOLD = 20  # Force re-evaluation if any resource below this
    ABOVE_MEAN_THRESHOLD = 0.20  # Switch if target is 20% above mean
    BELOW_MEAN_THRESHOLD = 0.10  # Switch if bottleneck is 10% below mean
    MIN_MEAN_FOR_BOTTLENECK = 30  # Don't do bottleneck switching if mean < this

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Don't bother picking a resource if collective is well-stocked
        if _collective_resources_sufficient(ctx):
            return True

        if "target_resource" not in ctx.blackboard:
            return False

        current_target = ctx.blackboard.get("target_resource")

        # Get collective resource levels
        collective = {
            "carbon": ctx.state.collective_carbon,
            "oxygen": ctx.state.collective_oxygen,
            "germanium": ctx.state.collective_germanium,
            "silicon": ctx.state.collective_silicon,
        }

        # Force re-evaluation if any resource is critically low and we're not targeting it
        critically_low = [res for res, amt in collective.items() if amt < self.CRITICAL_THRESHOLD]
        if critically_low and current_target not in critically_low:
            # Find the lowest critically low resource
            lowest = min(critically_low, key=lambda r: collective[r])
            if ctx.trace:
                ctx.trace.skip(
                    self.name,
                    f"critical: {lowest}={collective[lowest]}, switching from {current_target}",
                )
            ctx.blackboard.pop("target_resource", None)
            return False

        # Bottleneck switching: if target is >20% above mean and any element is <10% below mean
        # Only do this if mean >= MIN_MEAN_FOR_BOTTLENECK (avoid early game thrashing)
        mean_count = sum(collective.values()) / len(collective)
        if mean_count >= self.MIN_MEAN_FOR_BOTTLENECK:
            target_amount = collective.get(current_target, 0)
            above_mean_limit = mean_count * (1 + self.ABOVE_MEAN_THRESHOLD)
            below_mean_limit = mean_count * (1 - self.BELOW_MEAN_THRESHOLD)

            if target_amount > above_mean_limit:
                # Find bottleneck elements (below 10% of mean)
                bottlenecks = [res for res, amt in collective.items() if amt < below_mean_limit]
                if bottlenecks:
                    # Switch to the lowest bottleneck
                    lowest_bottleneck = min(bottlenecks, key=lambda r: collective[r])
                    if ctx.trace:
                        ctx.trace.skip(
                            self.name,
                            f"bottleneck: {current_target}={target_amount} "
                            f">{above_mean_limit:.0f} (mean={mean_count:.0f}), "
                            f"switching to {lowest_bottleneck}={collective[lowest_bottleneck]} "
                            f"<{below_mean_limit:.0f}",
                        )
                    # Set the bottleneck as explicit target so execute() uses it even without extractor
                    ctx.blackboard["_bottleneck_target"] = lowest_bottleneck
                    ctx.blackboard.pop("target_resource", None)
                    return False

        # Re-evaluate periodically to ensure we're mining what's needed
        last_pick = ctx.blackboard.get("_target_resource_step", 0)
        if ctx.step - last_pick >= self.REEVALUATE_INTERVAL:
            # Clear to force re-evaluation
            ctx.blackboard.pop("target_resource", None)
            return False

        return True

    def execute(self, ctx: PlankyContext) -> Optional[Action]:
        # Get collective resource levels
        collective = {
            "carbon": ctx.state.collective_carbon,
            "oxygen": ctx.state.collective_oxygen,
            "germanium": ctx.state.collective_germanium,
            "silicon": ctx.state.collective_silicon,
        }

        # Check if we have a bottleneck target from is_satisfied (use it even if no extractor known)
        bottleneck_target = ctx.blackboard.pop("_bottleneck_target", None)
        if bottleneck_target:
            ctx.blackboard["target_resource"] = bottleneck_target
            ctx.blackboard["_target_resource_step"] = ctx.step
            if ctx.trace:
                ctx.trace.activate(
                    self.name, f"bottleneck={bottleneck_target} (will explore if no extractor) coll={collective}"
                )
            # Return None to let MineResource run in the same tick
            return None

        # Find resources with available extractors
        available_resources: list[tuple[int, str]] = []
        for resource in RESOURCE_TYPES:
            extractors = ctx.map.find(type=f"{resource}_extractor")
            usable = [
                (pos, e)
                for pos, e in extractors
                if e.properties.get("remaining_uses", 999) > 0
                and e.properties.get("inventory_amount", -1) != 0
                and not _extractor_recently_failed(ctx, pos)
            ]
            if usable:
                amount = collective.get(resource, 0)
                available_resources.append((amount, resource))

        if not available_resources:
            # No extractors known — pick carbon as default, MineResource will explore
            ctx.blackboard["target_resource"] = "carbon"
            ctx.blackboard["_target_resource_step"] = ctx.step
            if ctx.trace:
                ctx.trace.activate(self.name, "no extractors known, defaulting to carbon")
            # Return None to let MineResource explore in the same tick
            return None

        # Priority: resources below threshold first (sorted by amount), then others
        below_threshold = [(amt, res) for amt, res in available_resources if amt < COLLECTIVE_SUFFICIENT_THRESHOLD]
        if below_threshold:
            # Mine the resource we have least of that's below 100
            below_threshold.sort()
            best_resource = below_threshold[0][1]
            if ctx.trace:
                ctx.trace.activate(self.name, f"need={best_resource} (below 100) coll={collective}")
        else:
            # All above threshold — pick the one with least (for balance)
            available_resources.sort()
            best_resource = available_resources[0][1]
            if ctx.trace:
                ctx.trace.activate(self.name, f"need={best_resource} (all above 100) coll={collective}")

        ctx.blackboard["target_resource"] = best_resource
        ctx.blackboard["_target_resource_step"] = ctx.step
        # Return None to let MineResource run in the same tick
        return None


def _extractor_recently_failed(ctx: PlankyContext, pos: tuple[int, int]) -> bool:
    """Check if we recently failed to mine from this extractor."""
    failed_step = ctx.blackboard.get(f"mine_failed_{pos}", -9999)
    return ctx.step - failed_step < 30  # Short cooldown — come back after depositing


class DepositCargoGoal(Goal):
    """Deposit resources at nearest cogs-aligned building when cargo is reasonably full.

    Triggers when cargo is >= 50% full (or >= 10 resources for small capacity).
    Once triggered, keeps depositing until cargo is EMPTY.
    Tracks attempts and marks depots as failed if cargo doesn't decrease.
    """

    name = "DepositCargo"
    MAX_ATTEMPTS_PER_DEPOT = 5

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        cargo = ctx.state.cargo_total

        # If we're currently depositing (flag set), keep going until empty
        if ctx.blackboard.get("_depositing", False):
            if cargo == 0:
                ctx.blackboard["_depositing"] = False
                return True
            return False  # Keep depositing until empty

        # Not currently depositing - check if we should start
        # Deposit when at least 50% full (but always deposit if cargo == capacity)
        capacity = ctx.state.cargo_capacity
        threshold = max(2, capacity // 2)

        if cargo >= threshold:
            ctx.blackboard["_depositing"] = True
            return False  # Start depositing

        return True  # Don't need to deposit yet

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
    # How many consecutive bumps without cargo increase before giving up on this extractor.
    # Keep high — miners should keep tapping as long as inventory is increasing.
    MAX_ATTEMPTS_PER_EXTRACTOR = 5

    def is_satisfied(self, ctx: PlankyContext) -> bool:
        # Stop mining when the collective is well-stocked
        if _collective_resources_sufficient(ctx) and ctx.state.cargo_total == 0:
            if ctx.trace:
                ctx.trace.skip(self.name, "collective resources sufficient, idling")
            return True
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
                    ctx.blackboard["_target_resource_step"] = ctx.step
                    break

        if target_pos is None:
            # No extractors found — explore in agent-specific direction to discover them
            ctx.blackboard.pop("target_resource", None)
            directions = ["north", "east", "south", "west"]
            return ctx.navigator.explore(
                ctx.state.position,
                ctx.map,
                direction_bias=directions[ctx.agent_id % 4],
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
                    # Mark as temporarily failed — will retry after cooldown
                    ctx.blackboard[f"mine_failed_{target_pos}"] = ctx.step
                    ctx.blackboard[attempts_key] = 0
                    # Also clear target resource to force re-evaluation
                    ctx.blackboard.pop("target_resource", None)
                    if ctx.trace:
                        ctx.trace.activate(self.name, f"giving up on {target_pos}")
                    return ctx.navigator.explore(
                        ctx.state.position,
                        ctx.map,
                        direction_bias=["north", "east", "south", "west"][ctx.agent_id % 4],
                    )

            return _move_toward(ctx.state.position, target_pos)

        # Don't reset attempts when moving away - only reset on successful mine
        return ctx.navigator.get_action(ctx.state.position, target_pos, ctx.map, reach_adjacent=True)

    def _find_extractor(self, ctx: PlankyContext, resource: str) -> Optional[tuple[int, int]]:
        """Find nearest usable extractor."""
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

        # Sort by distance to agent
        usable.sort(key=lambda x: _manhattan(ctx.state.position, x[0]))
        return usable[0][0]


def _find_cogs_depot(ctx: PlankyContext) -> tuple[int, int] | None:
    """Find nearest cogs-aligned depot, prioritizing hub."""
    from cogames_agents.policy.scripted_agent.planky.policy import SPAWN_POS  # noqa: PLC0415

    pos = ctx.state.position

    def recently_failed(p: tuple[int, int]) -> bool:
        failed_step = ctx.blackboard.get(f"deposit_failed_{p}", -9999)
        return ctx.step - failed_step < 100

    # Prioritize own team's hub
    hub_filter = {"collective_id": ctx.my_collective_id} if ctx.my_collective_id is not None else None
    for apos, _ in ctx.map.find(type_contains="hub", property_filter=hub_filter):
        if not recently_failed(apos):
            return apos

    # Fallback: nearest cogs junction near hub
    candidates: list[tuple[int, tuple[int, int]]] = []
    for jpos, _ in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
        if not recently_failed(jpos) and _manhattan(jpos, SPAWN_POS) <= 15:
            candidates.append((_manhattan(pos, jpos), jpos))

    if not candidates:
        # Last resort: navigate to hub area
        return SPAWN_POS
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
