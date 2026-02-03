"""
Aligner role for CoGsGuard.

Aligners find supply depots and align them to the cogs commons to take control.
With aligner gear, they get +20 influence capacity.

Strategy:
- Find ALL junctions on the map
- Prioritize aligning neutral and enemy (clips) junctions
- Systematically work through all junctions to take them over
- Check energy before moving to targets
- Retry failed align actions up to MAX_RETRIES times
"""

from __future__ import annotations

from typing import Optional

from cogames_agents.policy.scripted_agent.utils import is_adjacent
from mettagrid.simulator import Action

from .policy import DEBUG, CogsguardAgentPolicyImpl
from .types import CogsguardAgentState, Role, StructureType

# Maximum number of times to retry a failed align action
MAX_RETRIES = 3
# HP buffer to start returning to the hub before gear is lost.
HP_RETURN_BUFFER = 12


class AlignerAgentPolicyImpl(CogsguardAgentPolicyImpl):
    """Aligner agent: align ALL supply depots to cogs."""

    ROLE = Role.ALIGNER

    def execute_role(self, s: CogsguardAgentState) -> Action:
        """Execute aligner behavior: find and align ALL supply depots.

        Energy-aware behavior:
        - Check if we have enough energy before attempting to move to targets
        - If energy is low, go recharge at the nexus
        - Retry failed align actions up to MAX_RETRIES times
        - Require gear, heart, and influence before attempting to align
        - If gear acquisition fails repeatedly, get hearts first
        """
        if DEBUG and s.step_count % 50 == 0:
            num_junctions = len(s.get_structures_by_type(StructureType.CHARGER))
            num_worked = len(s.worked_junctions)
            print(
                f"[A{s.agent_id}] ALIGNER: step={s.step_count} influence={s.influence} "
                f"heart={s.heart} energy={s.energy} gear={s.aligner} "
                f"junctions_known={num_junctions} worked={num_worked}"
            )

        hub_pos = s.get_structure_position(StructureType.HUB)
        if hub_pos is not None:
            dist_to_hub = abs(hub_pos[0] - s.row) + abs(hub_pos[1] - s.col)
            if s.hp <= dist_to_hub + HP_RETURN_BUFFER:
                if DEBUG and s.step_count % 10 == 0:
                    print(f"[A{s.agent_id}] ALIGNER: Low HP ({s.hp}), returning to hub")
                return self._do_recharge(s)

        # === Resource check: need gear, heart, and influence to align ===
        has_gear = s.aligner >= 1
        has_heart = s.heart >= 1
        has_influence = s.influence >= 1

        # If we don't have gear, try to get it
        if not has_gear:
            return self._handle_no_gear(s)

        # If we have gear but are missing resources, go get them
        if not has_heart or not has_influence:
            if DEBUG and s.step_count % 10 == 0:
                print(
                    f"[A{s.agent_id}] ALIGNER: Have gear but missing resources "
                    f"(heart={has_heart}, influence={has_influence}), getting them first"
                )
            return self._get_resources(s, need_influence=not has_influence, need_heart=not has_heart)

        # Check if last action succeeded (for retry logic)
        # Actions can fail due to insufficient energy - agents auto-regen so just retry
        if s._pending_action_type == "align":
            target = s._pending_action_target
            if s.check_action_success():
                if DEBUG:
                    print(f"[A{s.agent_id}] ALIGNER: Previous align succeeded!")
                if target is not None and self._smart_role_coordinator is not None:
                    hub_pos = s.stations.get("hub")
                    self._smart_role_coordinator.register_junction_alignment(
                        target,
                        "c",
                        hub_pos,
                        s.step_count,
                    )
            elif s.should_retry_action(MAX_RETRIES):
                retry_count = s.increment_retry()
                if DEBUG:
                    print(
                        f"[A{s.agent_id}] ALIGNER: Align failed, retrying ({retry_count}/{MAX_RETRIES}) "
                        f"at {s._pending_action_target}"
                    )
                # Retry the same action - agent will have auto-regenerated some energy
                if s._pending_action_target and is_adjacent((s.row, s.col), s._pending_action_target):
                    return self._use_object_at(s, s._pending_action_target)
            else:
                if DEBUG:
                    print(f"[A{s.agent_id}] ALIGNER: Align failed after {MAX_RETRIES} retries, moving on")
                if target is not None and target == s._pending_alignment_target:
                    s._pending_alignment_target = None
                s.clear_pending_action()

        # Find the best depot to align (prioritize closest non-cogs junction)
        target_depot = None
        pending_target = s._pending_alignment_target
        if pending_target is not None:
            pending_struct = s.get_structure_at(pending_target)
            if pending_struct is None or pending_struct.structure_type == StructureType.CHARGER:
                if pending_struct is None or pending_struct.alignment in (None, "neutral"):
                    target_depot = pending_target
                elif pending_struct.alignment == "cogs":
                    s._pending_alignment_target = None

        if target_depot is None:
            target_depot = self._find_best_target(s)

        if target_depot is None:
            if DEBUG and s.step_count % 50 == 0:
                print(f"[A{s.agent_id}] ALIGNER: No targets, exploring for junctions")
            return self._explore_for_junctions(s)

        # Navigate to depot
        # Note: moves require energy. If move fails due to low energy,
        # action failure detection will catch it and we'll retry next step
        # (agents auto-regen energy every step, and regen full near aligned buildings)
        if not is_adjacent((s.row, s.col), target_depot):
            if DEBUG and s.step_count % 20 == 0:
                print(f"[A{s.agent_id}] ALIGNER: Moving to junction at {target_depot}")
            return self._move_towards(s, target_depot, reach_adjacent=True)

        # Align the depot by bumping it
        # Mark this junction as worked for a while (align multiple times then move on)
        last_worked = s.worked_junctions.get(target_depot, 0)
        times_worked = s.step_count - last_worked if last_worked > 0 else 0
        s.worked_junctions[target_depot] = s.step_count

        # Start tracking this align attempt
        s.start_action_attempt("align", target_depot)

        if DEBUG and times_worked < 5:
            print(f"[A{s.agent_id}] ALIGNER: ALIGNING junction at {target_depot} (energy={s.energy}, heart={s.heart})!")
        return self._use_object_at(s, target_depot)

    def _handle_no_gear(self, s: CogsguardAgentState) -> Action:
        """Handle behavior when aligner doesn't have gear.

        Strategy: Go to gear station and wait there until gear is available.
        Can't do much without gear, so just wait.
        """
        station_pos = s.get_structure_position(StructureType.ALIGNER_STATION)

        # If we don't know where the station is, explore to find it
        if station_pos is None:
            if DEBUG:
                print(f"[A{s.agent_id}] ALIGNER_NO_GEAR: Station unknown, exploring")
            return self._explore(s)

        # Go to gear station
        if not is_adjacent((s.row, s.col), station_pos):
            if DEBUG and s.step_count % 10 == 0:
                print(f"[A{s.agent_id}] ALIGNER_NO_GEAR: Moving to station at {station_pos}")
            return self._move_towards(s, station_pos, reach_adjacent=True)

        # At station - keep trying to get gear
        if DEBUG and s.step_count % 10 == 0:
            print(f"[A{s.agent_id}] ALIGNER_NO_GEAR: At station, waiting for gear")
        return self._use_object_at(s, station_pos)

    def _get_resources(self, s: CogsguardAgentState, need_influence: bool, need_heart: bool) -> Action:
        """Get hearts from the chest (primary source).

        The chest can produce hearts from resources:
        1. First tries to withdraw existing hearts from cogs commons (get_heart handler)
        2. If no hearts available, converts 1 of each element into 1 heart (make_heart handler)

        So as long as miners deposit resources, aligners can get hearts.
        If we've been trying to get hearts for too long, go explore instead.
        """
        if need_heart:
            # If we've waited more than 40 steps for hearts, go explore instead
            if s._heart_wait_start == 0:
                s._heart_wait_start = s.step_count
            if s.step_count - s._heart_wait_start > 40:
                if DEBUG:
                    print(f"[A{s.agent_id}] ALIGNER: Waited 40+ steps for hearts, exploring instead")
                s._heart_wait_start = 0
                return self._explore_for_junctions(s)

            # Try chest first - it's the primary heart source
            chest_pos = s.get_structure_position(StructureType.CHEST)
            if chest_pos is not None:
                if DEBUG and s.step_count % 10 == 0:
                    adj = is_adjacent((s.row, s.col), chest_pos)
                    print(f"[A{s.agent_id}] ALIGNER: Getting hearts from chest at {chest_pos}, adjacent={adj}")
                if not is_adjacent((s.row, s.col), chest_pos):
                    return self._move_towards(s, chest_pos, reach_adjacent=True)
                return self._use_object_at(s, chest_pos)

            # Try hub as fallback (may have heart AOE or deposit function)
            hub_pos = s.get_structure_position(StructureType.HUB)
            if hub_pos is not None:
                if DEBUG:
                    print(f"[A{s.agent_id}] ALIGNER: No chest found, trying hub at {hub_pos}")
                if not is_adjacent((s.row, s.col), hub_pos):
                    return self._move_towards(s, hub_pos, reach_adjacent=True)
                return self._use_object_at(s, hub_pos)

            # Neither found - explore to find them
            if DEBUG:
                print(f"[A{s.agent_id}] ALIGNER: No chest/hub found, exploring")
            s._heart_wait_start = 0
            return self._explore(s)

        # Just need influence - wait for AOE regeneration near hub
        hub_pos = s.get_structure_position(StructureType.HUB)
        if hub_pos is None:
            return self._explore(s)
        if not is_adjacent((s.row, s.col), hub_pos):
            return self._move_towards(s, hub_pos, reach_adjacent=True)
        return self._noop()

    def _find_best_target(self, s: CogsguardAgentState) -> Optional[tuple[int, int]]:
        """Find the closest un-aligned junction to align.

        Prioritizes by distance - aligns the closest junction that isn't already cogs-aligned.
        Skips junctions that were recently worked on to ensure we visit multiple junctions.
        """
        # Get all known junctions from structures map
        junctions = s.get_structures_by_type(StructureType.CHARGER)

        # How long to ignore a junction after working on it (steps)
        cooldown = 50

        recent_candidates: list[tuple[int, tuple[int, int]]] = []
        if self._smart_role_coordinator is not None:
            hub_pos = s.stations.get("hub")
            recent_targets = self._smart_role_coordinator.recent_scramble_targets(hub_pos, s.step_count)
            for pos in recent_targets:
                last_worked = s.worked_junctions.get(pos, 0)
                if last_worked > 0 and s.step_count - last_worked < cooldown:
                    continue
                junction = s.get_structure_at(pos)
                if junction is not None and junction.alignment in ("c", "clips"):
                    continue
                dist = abs(pos[0] - s.row) + abs(pos[1] - s.col)
                recent_candidates.append((dist, pos))

        if recent_candidates:
            recent_candidates.sort()
            target_idx = 0
            if self._smart_role_coordinator is not None:
                aligner_ids = sorted(
                    agent_id
                    for agent_id, snapshot in self._smart_role_coordinator.agent_snapshots.items()
                    if snapshot.role == Role.ALIGNER
                )
                if aligner_ids:
                    target_idx = aligner_ids.index(s.agent_id) if s.agent_id in aligner_ids else 0
            return recent_candidates[target_idx % len(recent_candidates)][1]

        # Collect all un-aligned junctions (not cogs) and sort by distance
        unaligned_junctions: list[tuple[int, tuple[int, int]]] = []

        for junction in junctions:
            pos = junction.position
            dist = abs(pos[0] - s.row) + abs(pos[1] - s.col)

            # Skip recently worked junctions
            last_worked = s.worked_junctions.get(pos, 0)
            if last_worked > 0 and s.step_count - last_worked < cooldown:
                continue

            # Skip already cogs-aligned junctions
            if junction.alignment is not None:
                continue

            # Add neutral junctions only
            unaligned_junctions.append((dist, pos))

        # Sort by distance and return closest
        if unaligned_junctions:
            unaligned_junctions.sort()
            if DEBUG and s.step_count % 20 == 0:
                count = len(unaligned_junctions)
                closest = unaligned_junctions[0][1]
                print(f"[A{s.agent_id}] ALIGNER: Found {count} un-aligned junctions, closest at {closest}")
            target_idx = 0
            if self._smart_role_coordinator is not None:
                aligner_ids = sorted(
                    agent_id
                    for agent_id, snapshot in self._smart_role_coordinator.agent_snapshots.items()
                    if snapshot.role == Role.ALIGNER
                )
                if aligner_ids:
                    target_idx = aligner_ids.index(s.agent_id) if s.agent_id in aligner_ids else 0
            return unaligned_junctions[target_idx % len(unaligned_junctions)][1]

        return None

    def _explore_for_junctions(self, s: CogsguardAgentState) -> Action:
        """Explore aggressively to find more junctions spread around the map."""
        frontier_action = self._explore_frontier(s)
        if frontier_action is not None:
            return frontier_action

        # Move in a direction based on agent ID and step count to spread out
        directions = ["north", "south", "east", "west"]
        # Cycle through directions, spending 20 steps in each direction
        dir_idx = (s.agent_id + s.step_count // 20) % 4
        direction = directions[dir_idx]

        dr, dc = self._move_deltas[direction]
        next_r, next_c = s.row + dr, s.col + dc

        # Check if we can move in that direction
        from cogames_agents.policy.scripted_agent.pathfinding import is_traversable  # noqa: PLC0415
        from cogames_agents.policy.scripted_agent.types import CellType  # noqa: PLC0415

        if is_traversable(s, next_r, next_c, CellType):  # type: ignore[arg-type]
            return self._move(direction)

        # Fall back to regular exploration if blocked
        return self._explore(s)
