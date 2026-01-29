"""
Resource Manager for CoGas multi-agent mining coordination.

Manages team-wide resource gathering strategy:
1. Track all known extractors and their status (depleted, cooldown, claimed)
2. Plan efficient mining routes to minimize travel time
3. Balance resource gathering with alignment tool usage
4. Manage inventory -- decide when to deposit vs keep mining
5. Coordinate miners to avoid targeting the same extractor
6. Prioritize resources needed for alignment gear crafting
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from cogames_agents.policy.scripted_agent.planky.context import PlankyContext

# Resource types
RESOURCE_TYPES = ("carbon", "oxygen", "germanium", "silicon")

# Cargo thresholds for deposit decisions
DEPOSIT_THRESHOLD_RATIO = 0.8  # Deposit when cargo >= 80% full
EMERGENCY_DEPOSIT_RATIO = 1.0  # Must deposit when full
MIN_CARGO_FOR_DETOUR = 10  # Don't detour to deposit for tiny loads

# Route planning
MAX_ROUTE_LENGTH = 5  # Max extractors in a planned route
STALE_EXTRACTOR_AGE = 200  # Steps before extractor info is stale

# Alignment gear resource priorities (resources needed for team gear crafting)
# Assemblers convert deposited resources into gear -- prioritize balance
GEAR_RESOURCE_WEIGHTS = {
    "carbon": 1.0,
    "oxygen": 1.0,
    "germanium": 1.5,  # Rarer, slightly prioritized
    "silicon": 1.5,
}


@dataclass
class TrackedExtractor:
    """State of a known extractor across all agent observations."""

    position: tuple[int, int]
    resource_type: str
    remaining_uses: int = 999
    inventory_amount: int = -1  # -1 = unknown
    cooldown: int = 0
    last_seen_step: int = 0
    claimed_by: Optional[int] = None
    failed_by: dict[int, int] = field(default_factory=dict)  # agent_id -> step failed


@dataclass
class DepotInfo:
    """Tracked deposit location."""

    position: tuple[int, int]
    depot_type: str  # "assembler", "junction", "charger"
    alignment: Optional[str] = None
    last_seen_step: int = 0


class ResourceManager:
    """Team-wide resource management for coordinated mining.

    Shared across all miner agents via the blackboard. Tracks extractor
    state from all agents' observations and coordinates mining assignments
    to maximize throughput and minimize contention.

    Usage:
        # In cogas_policy.py, stored in coordinator or blackboard:
        resource_mgr = ResourceManager()

        # Each miner calls per-step:
        resource_mgr.update_from_context(ctx)
        target = resource_mgr.select_mining_target(ctx)
        should_deposit = resource_mgr.should_deposit(ctx)
    """

    def __init__(self) -> None:
        self._extractors: dict[tuple[int, int], TrackedExtractor] = {}
        self._depots: dict[tuple[int, int], DepotInfo] = {}
        # Mining claims: agent_id -> extractor position
        self._mining_claims: dict[int, tuple[int, int]] = {}
        # Resource tallies from last team update
        self._team_cargo: dict[str, int] = {r: 0 for r in RESOURCE_TYPES}
        self._team_collective: dict[str, int] = {r: 0 for r in RESOURCE_TYPES}

    # ------------------------------------------------------------------
    # Observation updates
    # ------------------------------------------------------------------

    def update_from_context(self, ctx: PlankyContext) -> None:
        """Update resource state from an agent's current observation.

        Should be called once per step by each miner agent.
        """
        self._update_extractors(ctx)
        self._update_depots(ctx)
        self._update_team_resources(ctx)
        self._cleanup_stale_claims(ctx.step)

    def _update_extractors(self, ctx: PlankyContext) -> None:
        """Scan visible extractors and update tracking."""
        for resource in RESOURCE_TYPES:
            for pos, entity in ctx.map.find(type=f"{resource}_extractor"):
                remaining = entity.properties.get("remaining_uses", 999)
                inventory = entity.properties.get("inventory_amount", -1)
                cooldown = entity.properties.get("cooldown", 0)

                if pos in self._extractors:
                    ext = self._extractors[pos]
                    ext.remaining_uses = remaining
                    ext.inventory_amount = inventory
                    ext.cooldown = cooldown
                    ext.last_seen_step = ctx.step
                else:
                    self._extractors[pos] = TrackedExtractor(
                        position=pos,
                        resource_type=resource,
                        remaining_uses=remaining,
                        inventory_amount=inventory,
                        cooldown=cooldown,
                        last_seen_step=ctx.step,
                    )

    def _update_depots(self, ctx: PlankyContext) -> None:
        """Scan visible depots (assemblers, cogs junctions/chargers)."""
        for pos, _ in ctx.map.find(type="assembler"):
            self._depots[pos] = DepotInfo(
                position=pos,
                depot_type="assembler",
                alignment="cogs",
                last_seen_step=ctx.step,
            )
        for pos, e in ctx.map.find(type_contains="junction", property_filter={"alignment": "cogs"}):
            self._depots[pos] = DepotInfo(
                position=pos,
                depot_type="junction",
                alignment=e.properties.get("alignment"),
                last_seen_step=ctx.step,
            )
        for pos, e in ctx.map.find(type_contains="charger", property_filter={"alignment": "cogs"}):
            self._depots[pos] = DepotInfo(
                position=pos,
                depot_type="charger",
                alignment=e.properties.get("alignment"),
                last_seen_step=ctx.step,
            )

    def _update_team_resources(self, ctx: PlankyContext) -> None:
        """Track team-wide resource levels for balancing."""
        self._team_cargo["carbon"] = ctx.state.collective_carbon
        self._team_cargo["oxygen"] = ctx.state.collective_oxygen
        self._team_cargo["germanium"] = ctx.state.collective_germanium
        self._team_cargo["silicon"] = ctx.state.collective_silicon

    def _cleanup_stale_claims(self, current_step: int) -> None:
        """Release mining claims from agents that haven't updated recently."""
        stale: list[int] = []
        for agent_id, pos in self._mining_claims.items():
            ext = self._extractors.get(pos)
            if ext is not None and current_step - ext.last_seen_step > STALE_EXTRACTOR_AGE:
                stale.append(agent_id)
        for agent_id in stale:
            self.release_claim(agent_id)

    # ------------------------------------------------------------------
    # Mining target selection
    # ------------------------------------------------------------------

    def select_mining_target(
        self,
        ctx: PlankyContext,
        preferred_resource: Optional[str] = None,
    ) -> Optional[tuple[int, int]]:
        """Select the best extractor for this agent to mine.

        Considers:
        - Distance (nearest-neighbor heuristic)
        - Whether extractor is claimed by another miner
        - Extractor health (remaining uses, not depleted)
        - Resource balancing (team needs)
        - Alignment gear priority
        - Recent failure history

        Returns extractor position or None if no viable target.
        """
        agent_id = ctx.agent_id

        # Determine which resource to prioritize
        target_resource = preferred_resource or self._pick_priority_resource(ctx)

        # Score all viable extractors
        scored: list[tuple[float, tuple[int, int]]] = []
        for epos, ext in self._extractors.items():
            score = self._score_extractor(ctx, ext, target_resource)
            if score is None:
                continue
            scored.append((score, epos))

        if not scored:
            return None

        scored.sort()
        best_pos = scored[0][1]

        # Claim the target
        self.claim_extractor(agent_id, best_pos)
        return best_pos

    def _score_extractor(
        self,
        ctx: PlankyContext,
        ext: TrackedExtractor,
        target_resource: str,
    ) -> Optional[float]:
        """Score an extractor (lower is better). Returns None if unusable."""
        # Filter out unusable extractors
        if ext.remaining_uses <= 0:
            return None
        if ext.inventory_amount == 0:
            return None

        # Check if recently failed by this agent
        failed_step = ext.failed_by.get(ctx.agent_id, -9999)
        if ctx.step - failed_step < 100:
            return None

        # Check if claimed by another agent
        if ext.claimed_by is not None and ext.claimed_by != ctx.agent_id:
            return None

        # Base score: distance
        dist = _manhattan(ctx.state.position, ext.position)
        score = float(dist)

        # Resource match bonus (prefer target resource)
        if ext.resource_type == target_resource:
            score -= 15.0

        # Resource balancing: prefer scarce resources
        weight = GEAR_RESOURCE_WEIGHTS.get(ext.resource_type, 1.0)
        team_amount = self._team_cargo.get(ext.resource_type, 0)
        scarcity_bonus = weight * max(0.0, 10.0 - team_amount * 0.1)
        score -= scarcity_bonus

        # Freshness penalty: prefer recently observed extractors
        age = ctx.step - ext.last_seen_step
        if age > STALE_EXTRACTOR_AGE:
            score += 20.0

        # Remaining uses bonus: prefer healthier extractors
        if ext.remaining_uses < 10:
            score += 5.0

        return score

    def _pick_priority_resource(self, ctx: PlankyContext) -> str:
        """Choose which resource type the team needs most.

        Balances resource gathering toward alignment gear needs and
        overall team resource balance.
        """
        # Find which resource we have least of (weighted by gear priority)
        best_resource = "carbon"
        best_score = float("inf")

        for resource in RESOURCE_TYPES:
            amount = self._team_cargo.get(resource, 0)
            weight = GEAR_RESOURCE_WEIGHTS.get(resource, 1.0)
            # Lower weighted amount = higher priority
            weighted = amount / weight
            if weighted < best_score:
                best_score = weighted
                best_resource = resource

        return best_resource

    # ------------------------------------------------------------------
    # Mining route planning
    # ------------------------------------------------------------------

    def plan_mining_route(
        self,
        ctx: PlankyContext,
        max_stops: int = MAX_ROUTE_LENGTH,
    ) -> list[tuple[int, int]]:
        """Plan an efficient multi-extractor route using nearest-neighbor.

        Returns ordered list of extractor positions to visit.
        Useful for miners planning ahead when multiple extractors are nearby.
        """
        target_resource = self._pick_priority_resource(ctx)
        current = ctx.state.position
        visited: set[tuple[int, int]] = set()
        route: list[tuple[int, int]] = []

        for _ in range(max_stops):
            best_pos: Optional[tuple[int, int]] = None
            best_dist = float("inf")

            for epos, ext in self._extractors.items():
                if epos in visited:
                    continue
                if self._score_extractor(ctx, ext, target_resource) is None:
                    continue
                dist = _manhattan(current, epos)
                # Prefer target resource along the route
                if ext.resource_type == target_resource:
                    dist -= 5
                if dist < best_dist:
                    best_dist = dist
                    best_pos = epos

            if best_pos is None:
                break

            route.append(best_pos)
            visited.add(best_pos)
            current = best_pos

        return route

    # ------------------------------------------------------------------
    # Deposit decisions
    # ------------------------------------------------------------------

    def should_deposit(self, ctx: PlankyContext) -> bool:
        """Decide whether the agent should go deposit resources.

        Considers cargo fullness, distance to depot, and opportunity cost.
        """
        cargo = ctx.state.cargo_total
        capacity = ctx.state.cargo_capacity

        if capacity <= 0:
            return False

        ratio = cargo / capacity

        # Must deposit if full
        if ratio >= EMERGENCY_DEPOSIT_RATIO:
            return True

        # Deposit if above threshold and a depot is reasonably close
        if ratio >= DEPOSIT_THRESHOLD_RATIO:
            depot = self.find_best_depot(ctx)
            if depot is not None:
                dist = _manhattan(ctx.state.position, depot)
                # Only deposit if depot isn't too far away
                return dist < 40
            return True  # No known depot, deposit at first opportunity

        # Don't bother depositing small loads unless very close to a depot
        if cargo >= MIN_CARGO_FOR_DETOUR:
            depot = self.find_best_depot(ctx)
            if depot is not None and _manhattan(ctx.state.position, depot) < 8:
                return True

        return False

    def find_best_depot(self, ctx: PlankyContext) -> Optional[tuple[int, int]]:
        """Find nearest cogs-aligned depot for depositing.

        Prefers assemblers over junctions (assemblers convert to gear).
        """
        pos = ctx.state.position
        candidates: list[tuple[float, tuple[int, int]]] = []

        for dpos, depot in self._depots.items():
            if depot.alignment != "cogs":
                continue
            dist = float(_manhattan(pos, dpos))
            # Assemblers are preferred (convert resources to gear)
            if depot.depot_type == "assembler":
                dist -= 5.0
            candidates.append((dist, dpos))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    # ------------------------------------------------------------------
    # Claim management (miner deconfliction)
    # ------------------------------------------------------------------

    def claim_extractor(self, agent_id: int, position: tuple[int, int]) -> bool:
        """Claim an extractor for mining. Returns True if successfully claimed.

        Releases any previous claim by this agent first.
        """
        ext = self._extractors.get(position)
        if ext is None:
            return False

        # Check if already claimed by another agent
        if ext.claimed_by is not None and ext.claimed_by != agent_id:
            return False

        # Release previous claim
        self.release_claim(agent_id)

        # Set new claim
        self._mining_claims[agent_id] = position
        ext.claimed_by = agent_id
        return True

    def release_claim(self, agent_id: int) -> None:
        """Release any extractor claim held by this agent."""
        prev_pos = self._mining_claims.pop(agent_id, None)
        if prev_pos is not None:
            ext = self._extractors.get(prev_pos)
            if ext is not None and ext.claimed_by == agent_id:
                ext.claimed_by = None

    def mark_extractor_failed(self, agent_id: int, position: tuple[int, int], step: int) -> None:
        """Mark an extractor as failed by this agent (cooldown before retry)."""
        ext = self._extractors.get(position)
        if ext is not None:
            ext.failed_by[agent_id] = step
        # Release claim so others can try
        if self._mining_claims.get(agent_id) == position:
            self.release_claim(agent_id)

    def get_agent_claim(self, agent_id: int) -> Optional[tuple[int, int]]:
        """Get the extractor position currently claimed by an agent."""
        return self._mining_claims.get(agent_id)

    # ------------------------------------------------------------------
    # Resource balance queries
    # ------------------------------------------------------------------

    def get_resource_status(self) -> dict[str, dict[str, int]]:
        """Summary of known resources across all tracked extractors.

        Returns dict of resource_type -> {total_extractors, active, depleted}.
        """
        status: dict[str, dict[str, int]] = {}
        for resource in RESOURCE_TYPES:
            total = 0
            active = 0
            depleted = 0
            for ext in self._extractors.values():
                if ext.resource_type != resource:
                    continue
                total += 1
                if ext.remaining_uses <= 0 or ext.inventory_amount == 0:
                    depleted += 1
                else:
                    active += 1
            status[resource] = {"total": total, "active": active, "depleted": depleted}
        return status

    def get_scarcest_resource(self) -> str:
        """Return the resource type the team has least of (weighted)."""
        return self._pick_priority_resource_from_cargo(self._team_cargo)

    def _pick_priority_resource_from_cargo(self, cargo: dict[str, int]) -> str:
        best = "carbon"
        best_score = float("inf")
        for resource in RESOURCE_TYPES:
            amount = cargo.get(resource, 0)
            weight = GEAR_RESOURCE_WEIGHTS.get(resource, 1.0)
            weighted = amount / weight
            if weighted < best_score:
                best_score = weighted
                best = resource
        return best

    @property
    def known_extractor_count(self) -> int:
        return len(self._extractors)

    @property
    def active_extractor_count(self) -> int:
        return sum(1 for ext in self._extractors.values() if ext.remaining_uses > 0 and ext.inventory_amount != 0)

    @property
    def active_miner_count(self) -> int:
        return len(self._mining_claims)


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
