"""Junction control strategy module for the cogas agent.

Centralized junction tracking, prioritization, and agent assignment for
competitive junction control. This module is the core competitive advantage
for the cogas agent, implementing:

1. Junction tracking with alignment status
2. Target prioritization: unaligned > enemy-aligned > already-ours (defense)
3. Aligner assignment to nearest unaligned junctions (no overlap)
4. Scrambler assignment to enemy-held junctions
5. Zone control - divide map into sectors, assign agents per sector
6. Contested junction handling - escalate by sending more agents
7. Alignment progress tracking and flip prediction
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class JunctionAlignment(Enum):
    """Alignment state of a junction."""

    UNALIGNED = "unaligned"  # Neutral / unknown
    COGS = "cogs"  # Ours
    CLIPS = "clips"  # Enemy


class JunctionContestLevel(Enum):
    """How contested a junction is."""

    UNCONTESTED = "uncontested"
    LIGHTLY_CONTESTED = "lightly_contested"  # 1 enemy nearby
    HEAVILY_CONTESTED = "heavily_contested"  # 2+ enemies nearby


@dataclass
class JunctionState:
    """Full state tracking for a single junction."""

    position: tuple[int, int]
    alignment: JunctionAlignment = JunctionAlignment.UNALIGNED
    last_seen_step: int = 0

    # Alignment history for flip prediction
    alignment_history: list[tuple[int, JunctionAlignment]] = field(default_factory=list)

    # Contest tracking
    contest_level: JunctionContestLevel = JunctionContestLevel.UNCONTESTED
    nearby_enemy_count: int = 0

    # Assignment tracking
    assigned_agent_id: Optional[int] = None
    assigned_role: Optional[str] = None  # "aligner" or "scrambler"

    # Time tracking for scoring
    steps_held_by_enemy: int = 0
    steps_held_by_us: int = 0
    last_flip_step: int = 0

    def update_alignment(self, alignment: JunctionAlignment, step: int) -> None:
        """Update alignment and record in history."""
        if alignment != self.alignment:
            self.alignment_history.append((step, alignment))
            self.last_flip_step = step
        self.alignment = alignment
        self.last_seen_step = step

    def predict_flip_risk(self, current_step: int) -> float:
        """Predict risk of this junction flipping based on history.

        Returns a score 0.0 (stable) to 1.0 (likely to flip).
        """
        if len(self.alignment_history) < 2:
            return 0.0

        # More recent flips = higher risk
        recent_flips = sum(1 for step, _ in self.alignment_history if current_step - step < 200)

        # Scale: 0 flips = 0.0, 1 flip = 0.3, 2 = 0.6, 3+ = 0.9
        risk = min(recent_flips * 0.3, 0.9)

        # If enemy agents nearby, increase risk
        if self.contest_level == JunctionContestLevel.HEAVILY_CONTESTED:
            risk = min(risk + 0.3, 1.0)
        elif self.contest_level == JunctionContestLevel.LIGHTLY_CONTESTED:
            risk = min(risk + 0.15, 1.0)

        return risk


@dataclass
class ZoneSector:
    """A map sector for zone control."""

    sector_id: int
    center: tuple[int, int]
    junctions: list[tuple[int, int]] = field(default_factory=list)
    assigned_agents: list[int] = field(default_factory=list)

    @property
    def junction_count(self) -> int:
        return len(self.junctions)


class JunctionController:
    """Centralized junction control strategy.

    Shared across all cogas agents via the coordinator. Tracks junction state,
    assigns agents to targets, and implements zone control.
    """

    def __init__(self, num_agents: int) -> None:
        self.num_agents = num_agents

        # Junction state: position -> JunctionState
        self._junctions: dict[tuple[int, int], JunctionState] = {}

        # Agent assignments: agent_id -> target junction position
        self._aligner_assignments: dict[int, tuple[int, int]] = {}
        self._scrambler_assignments: dict[int, tuple[int, int]] = {}

        # Zone control
        self._sectors: list[ZoneSector] = []
        self._sectors_dirty = True

        # Heart reservation: agent_id -> reservation step
        self._heart_reservations: dict[int, int] = {}

        # Stats
        self._total_junctions_aligned = 0
        self._total_junctions_scrambled = 0

    # =========================================================================
    # Junction tracking
    # =========================================================================

    def update_junction(
        self,
        position: tuple[int, int],
        alignment_str: Optional[str],
        step: int,
        nearby_enemy_count: int = 0,
    ) -> None:
        """Update or register a junction's state.

        Args:
            position: Junction (row, col) in agent-relative coordinates.
            alignment_str: "cogs", "clips", or None (neutral/unknown).
            step: Current simulation step.
            nearby_enemy_count: Number of enemy agents near this junction.
        """
        alignment = self._parse_alignment(alignment_str)

        if position not in self._junctions:
            self._junctions[position] = JunctionState(position=position)
            self._sectors_dirty = True

        junction = self._junctions[position]
        old_alignment = junction.alignment

        junction.update_alignment(alignment, step)
        junction.nearby_enemy_count = nearby_enemy_count

        # Update contest level
        if nearby_enemy_count >= 2:
            junction.contest_level = JunctionContestLevel.HEAVILY_CONTESTED
        elif nearby_enemy_count >= 1:
            junction.contest_level = JunctionContestLevel.LIGHTLY_CONTESTED
        else:
            junction.contest_level = JunctionContestLevel.UNCONTESTED

        # Track time held
        if alignment == JunctionAlignment.CLIPS:
            junction.steps_held_by_enemy += 1
        elif alignment == JunctionAlignment.COGS:
            junction.steps_held_by_us += 1

        # Track alignment transitions for stats
        if old_alignment != alignment:
            if alignment == JunctionAlignment.COGS:
                self._total_junctions_aligned += 1
            if old_alignment == JunctionAlignment.CLIPS and alignment != JunctionAlignment.CLIPS:
                self._total_junctions_scrambled += 1

    def get_junction(self, position: tuple[int, int]) -> Optional[JunctionState]:
        """Get junction state by position."""
        return self._junctions.get(position)

    @property
    def known_junctions(self) -> list[JunctionState]:
        """All known junctions."""
        return list(self._junctions.values())

    @property
    def cogs_junctions(self) -> list[JunctionState]:
        """Junctions currently aligned to cogs."""
        return [j for j in self._junctions.values() if j.alignment == JunctionAlignment.COGS]

    @property
    def clips_junctions(self) -> list[JunctionState]:
        """Junctions currently aligned to clips (enemy)."""
        return [j for j in self._junctions.values() if j.alignment == JunctionAlignment.CLIPS]

    @property
    def unaligned_junctions(self) -> list[JunctionState]:
        """Junctions that are neutral/unaligned."""
        return [j for j in self._junctions.values() if j.alignment == JunctionAlignment.UNALIGNED]

    # =========================================================================
    # Target prioritization
    # =========================================================================

    def score_junction_for_aligner(
        self,
        junction: JunctionState,
        agent_pos: tuple[int, int],
        hub_pos: Optional[tuple[int, int]] = None,
    ) -> float:
        """Score a junction for aligner targeting.

        Higher score = higher priority target.

        Prioritization order:
        1. Unaligned junctions (highest priority - free points)
        2. Enemy-aligned junctions (need scramble first, but worth contesting)
        3. Already-ours junctions with flip risk (defense)

        Within each tier, prefer:
        - Closer junctions (less travel time)
        - Junctions near hub (energy sustainability)
        - Junctions in clusters (zone control)
        - Uncontested junctions (easier to capture)
        """
        score = 0.0
        dist = _manhattan_distance(agent_pos, junction.position)

        # Base priority by alignment
        if junction.alignment == JunctionAlignment.UNALIGNED:
            score += 1000.0  # Highest priority: free points
        elif junction.alignment == JunctionAlignment.CLIPS:
            score += 500.0  # Worth contesting after scramble
        elif junction.alignment == JunctionAlignment.COGS:
            # Only defend if at risk
            flip_risk = junction.predict_flip_risk(junction.last_seen_step)
            if flip_risk > 0.3:
                score += 200.0 * flip_risk
            else:
                return -1.0  # Skip stable friendly junctions

        # Proximity bonus (closer = better). Normalize to ~0-100 range.
        max_dist = 50.0
        proximity = max(0.0, (max_dist - dist) / max_dist) * 100.0
        score += proximity

        # Hub proximity bonus (junctions near hub sustain energy)
        if hub_pos is not None:
            hub_dist = _manhattan_distance(hub_pos, junction.position)
            hub_proximity = max(0.0, (max_dist - hub_dist) / max_dist) * 50.0
            score += hub_proximity

        # Cluster bonus: count nearby cogs junctions (zone control)
        cluster_count = self._count_nearby_cogs_junctions(junction.position, radius=10)
        score += cluster_count * 20.0

        # Contest penalty: avoid heavily contested junctions
        if junction.contest_level == JunctionContestLevel.HEAVILY_CONTESTED:
            score -= 150.0
        elif junction.contest_level == JunctionContestLevel.LIGHTLY_CONTESTED:
            score -= 50.0

        # Nearby resource bonus (junctions near extractors help miners)
        # This is approximated by distance from hub since extractors cluster near hub

        return score

    def score_junction_for_scrambler(
        self,
        junction: JunctionState,
        agent_pos: tuple[int, int],
    ) -> float:
        """Score an enemy junction for scrambler targeting.

        Higher score = higher disruption value.

        Prefers:
        - Longer-held enemy junctions (more valuable to disrupt)
        - Enemy clusters (breaking clusters fragments control)
        - Reachable targets (distance penalty)
        """
        if junction.alignment != JunctionAlignment.CLIPS:
            return -1.0  # Only target enemy junctions

        score = 0.0
        dist = _manhattan_distance(agent_pos, junction.position)

        # Time held by enemy: longer = more valuable to disrupt
        score += min(junction.steps_held_by_enemy, 500) * 0.5

        # Enemy cluster bonus: breaking clusters denies zone control
        enemy_cluster_count = self._count_nearby_clips_junctions(junction.position, radius=10)
        score += enemy_cluster_count * 80.0

        # Base value for being an enemy junction
        score += 200.0

        # Distance penalty (still prefer reachable targets)
        max_dist = 50.0
        distance_penalty = (dist / max_dist) * 100.0
        score -= distance_penalty

        return score

    def get_priority_targets_for_aligner(
        self,
        agent_id: int,
        agent_pos: tuple[int, int],
        hub_pos: Optional[tuple[int, int]] = None,
        max_targets: int = 5,
    ) -> list[tuple[float, tuple[int, int]]]:
        """Get prioritized junction targets for an aligner agent.

        Returns list of (score, position) sorted by score descending.
        Excludes junctions already assigned to other aligners.
        """
        candidates: list[tuple[float, tuple[int, int]]] = []

        for junction in self._junctions.values():
            # Skip junctions assigned to other aligners
            if (
                junction.assigned_agent_id is not None
                and junction.assigned_agent_id != agent_id
                and junction.assigned_role == "aligner"
            ):
                continue

            score = self.score_junction_for_aligner(junction, agent_pos, hub_pos)
            if score > 0:
                candidates.append((score, junction.position))

        candidates.sort(reverse=True)
        return candidates[:max_targets]

    def get_priority_targets_for_scrambler(
        self,
        agent_id: int,
        agent_pos: tuple[int, int],
        max_targets: int = 5,
    ) -> list[tuple[float, tuple[int, int]]]:
        """Get prioritized junction targets for a scrambler agent.

        Returns list of (score, position) sorted by score descending.
        Excludes junctions already assigned to other scramblers.
        """
        candidates: list[tuple[float, tuple[int, int]]] = []

        for junction in self._junctions.values():
            # Skip junctions assigned to other scramblers
            if (
                junction.assigned_agent_id is not None
                and junction.assigned_agent_id != agent_id
                and junction.assigned_role == "scrambler"
            ):
                continue

            score = self.score_junction_for_scrambler(junction, agent_pos)
            if score > 0:
                candidates.append((score, junction.position))

        candidates.sort(reverse=True)
        return candidates[:max_targets]

    # =========================================================================
    # Agent assignment (no overlap)
    # =========================================================================

    def assign_aligner(
        self,
        agent_id: int,
        agent_pos: tuple[int, int],
        hub_pos: Optional[tuple[int, int]] = None,
    ) -> Optional[tuple[int, int]]:
        """Assign an aligner to the best available junction.

        Returns the target junction position, or None if no targets available.
        Ensures no two aligners target the same junction.
        """
        # Clear stale assignment
        if agent_id in self._aligner_assignments:
            old_target = self._aligner_assignments[agent_id]
            junction = self._junctions.get(old_target)
            if junction is not None and junction.assigned_agent_id == agent_id:
                # Check if the old target is still valid
                if junction.alignment == JunctionAlignment.COGS:
                    # Already aligned - release
                    junction.assigned_agent_id = None
                    junction.assigned_role = None
                    del self._aligner_assignments[agent_id]
                else:
                    # Still valid - keep assignment
                    return old_target

        targets = self.get_priority_targets_for_aligner(agent_id, agent_pos, hub_pos)
        if not targets:
            return None

        _, target_pos = targets[0]
        junction = self._junctions[target_pos]

        # Claim this junction
        junction.assigned_agent_id = agent_id
        junction.assigned_role = "aligner"
        self._aligner_assignments[agent_id] = target_pos

        return target_pos

    def assign_scrambler(
        self,
        agent_id: int,
        agent_pos: tuple[int, int],
    ) -> Optional[tuple[int, int]]:
        """Assign a scrambler to the best available enemy junction.

        Returns the target junction position, or None if no targets available.
        Ensures no two scramblers target the same junction.
        """
        # Clear stale assignment
        if agent_id in self._scrambler_assignments:
            old_target = self._scrambler_assignments[agent_id]
            junction = self._junctions.get(old_target)
            if junction is not None and junction.assigned_agent_id == agent_id:
                if junction.alignment != JunctionAlignment.CLIPS:
                    # No longer enemy - release
                    junction.assigned_agent_id = None
                    junction.assigned_role = None
                    del self._scrambler_assignments[agent_id]
                else:
                    # Still valid
                    return old_target

        targets = self.get_priority_targets_for_scrambler(agent_id, agent_pos)
        if not targets:
            return None

        _, target_pos = targets[0]
        junction = self._junctions[target_pos]

        # Claim this junction
        junction.assigned_agent_id = agent_id
        junction.assigned_role = "scrambler"
        self._scrambler_assignments[agent_id] = target_pos

        return target_pos

    def release_assignment(self, agent_id: int) -> None:
        """Release any junction assignment for an agent."""
        for assignments in (self._aligner_assignments, self._scrambler_assignments):
            if agent_id in assignments:
                target = assignments[agent_id]
                junction = self._junctions.get(target)
                if junction is not None and junction.assigned_agent_id == agent_id:
                    junction.assigned_agent_id = None
                    junction.assigned_role = None
                del assignments[agent_id]

    def get_assignment(self, agent_id: int) -> Optional[tuple[int, int]]:
        """Get the current junction assignment for an agent."""
        if agent_id in self._aligner_assignments:
            return self._aligner_assignments[agent_id]
        if agent_id in self._scrambler_assignments:
            return self._scrambler_assignments[agent_id]
        return None

    # =========================================================================
    # Zone control
    # =========================================================================

    def build_sectors(self, num_sectors: int = 4) -> None:
        """Divide known junctions into map sectors.

        Uses simple grid-based partitioning. Sectors are rebuilt when
        new junctions are discovered.
        """
        if not self._junctions:
            self._sectors = []
            return

        positions = [j.position for j in self._junctions.values()]

        # Find bounding box
        min_r = min(p[0] for p in positions)
        max_r = max(p[0] for p in positions)
        min_c = min(p[1] for p in positions)
        max_c = max(p[1] for p in positions)

        # Grid dimensions
        grid_size = max(1, int(math.ceil(math.sqrt(num_sectors))))
        row_step = max(1, (max_r - min_r + 1) // grid_size)
        col_step = max(1, (max_c - min_c + 1) // grid_size)

        self._sectors = []
        sector_id = 0

        for gi in range(grid_size):
            for gj in range(grid_size):
                r_start = min_r + gi * row_step
                r_end = r_start + row_step if gi < grid_size - 1 else max_r + 1
                c_start = min_c + gj * col_step
                c_end = c_start + col_step if gj < grid_size - 1 else max_c + 1

                center = ((r_start + r_end) // 2, (c_start + c_end) // 2)
                sector_junctions = [p for p in positions if r_start <= p[0] < r_end and c_start <= p[1] < c_end]

                if sector_junctions:
                    self._sectors.append(
                        ZoneSector(
                            sector_id=sector_id,
                            center=center,
                            junctions=sector_junctions,
                        )
                    )
                    sector_id += 1

        self._sectors_dirty = False

    def get_sector_for_agent(self, agent_id: int) -> Optional[ZoneSector]:
        """Get the sector assigned to an agent.

        Distributes agents across sectors round-robin, prioritizing
        sectors with more junctions.
        """
        if self._sectors_dirty:
            self.build_sectors()

        if not self._sectors:
            return None

        # Sort sectors by junction count descending for priority assignment
        sorted_sectors = sorted(self._sectors, key=lambda s: s.junction_count, reverse=True)
        idx = agent_id % len(sorted_sectors)
        return sorted_sectors[idx]

    def get_junctions_in_sector(self, sector_id: int) -> list[JunctionState]:
        """Get all junction states within a sector."""
        for sector in self._sectors:
            if sector.sector_id == sector_id:
                return [self._junctions[pos] for pos in sector.junctions if pos in self._junctions]
        return []

    # =========================================================================
    # Contested junction escalation
    # =========================================================================

    def get_contested_junctions(self) -> list[JunctionState]:
        """Get all contested junctions (enemy activity detected)."""
        return [j for j in self._junctions.values() if j.contest_level != JunctionContestLevel.UNCONTESTED]

    def should_escalate(self, position: tuple[int, int]) -> bool:
        """Check if a junction needs escalation (more agents sent).

        Escalation criteria:
        - Junction is heavily contested
        - Junction was recently flipped from cogs to enemy
        - Junction has high flip risk
        """
        junction = self._junctions.get(position)
        if junction is None:
            return False

        if junction.contest_level == JunctionContestLevel.HEAVILY_CONTESTED:
            return True

        # Recently flipped away from us
        if (
            junction.alignment != JunctionAlignment.COGS
            and junction.last_flip_step > 0
            and junction.last_seen_step - junction.last_flip_step < 100
            and any(align == JunctionAlignment.COGS for _, align in junction.alignment_history[-3:])
        ):
            return True

        return junction.predict_flip_risk(junction.last_seen_step) > 0.6

    def get_escalation_targets(self) -> list[tuple[int, int]]:
        """Get junctions that need escalation (additional agent support)."""
        return [j.position for j in self._junctions.values() if self.should_escalate(j.position)]

    # =========================================================================
    # Heart reservation
    # =========================================================================

    def reserve_heart(self, agent_id: int, step: int) -> bool:
        """Reserve a heart for an agent to prevent contention.

        Returns True if reservation is granted.
        Reservations expire after 50 steps.
        """
        # Clean expired reservations
        expired = [aid for aid, reserve_step in self._heart_reservations.items() if step - reserve_step > 50]
        for aid in expired:
            del self._heart_reservations[aid]

        # Check if agent already has a reservation
        if agent_id in self._heart_reservations:
            return True

        # Grant reservation
        self._heart_reservations[agent_id] = step
        return True

    def release_heart_reservation(self, agent_id: int) -> None:
        """Release a heart reservation."""
        self._heart_reservations.pop(agent_id, None)

    def has_heart_reservation(self, agent_id: int) -> bool:
        """Check if an agent has an active heart reservation."""
        return agent_id in self._heart_reservations

    # =========================================================================
    # Alignment progress tracking
    # =========================================================================

    def get_alignment_summary(self) -> dict[str, int]:
        """Get a summary of junction alignment counts."""
        cogs_count = len(self.cogs_junctions)
        clips_count = len(self.clips_junctions)
        neutral_count = len(self.unaligned_junctions)
        return {
            "cogs": cogs_count,
            "clips": clips_count,
            "neutral": neutral_count,
            "total": len(self._junctions),
            "total_aligned": self._total_junctions_aligned,
            "total_scrambled": self._total_junctions_scrambled,
        }

    def get_control_ratio(self) -> float:
        """Get the fraction of known junctions controlled by cogs.

        Returns 0.0 if no junctions known.
        """
        total = len(self._junctions)
        if total == 0:
            return 0.0
        return len(self.cogs_junctions) / total

    def get_patrol_route(self, agent_pos: tuple[int, int]) -> list[tuple[int, int]]:
        """Compute a patrol route through all cogs-aligned junctions.

        Uses nearest-neighbor heuristic for a short cycle starting
        from the agent's current position. Used by sentinel agents
        in the SUSTAIN phase.
        """
        cogs = self.cogs_junctions
        if not cogs:
            return []

        # Nearest-neighbor TSP heuristic
        positions = [j.position for j in cogs]
        route: list[tuple[int, int]] = []
        remaining = set(range(len(positions)))

        # Start from the junction nearest to the agent
        current = agent_pos
        while remaining:
            best_idx = min(remaining, key=lambda i: _manhattan_distance(current, positions[i]))
            remaining.remove(best_idx)
            route.append(positions[best_idx])
            current = positions[best_idx]

        return route

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _count_nearby_cogs_junctions(self, position: tuple[int, int], radius: int) -> int:
        """Count cogs-aligned junctions within radius."""
        count = 0
        for junction in self._junctions.values():
            if junction.alignment != JunctionAlignment.COGS:
                continue
            if junction.position == position:
                continue
            if _manhattan_distance(position, junction.position) <= radius:
                count += 1
        return count

    def _count_nearby_clips_junctions(self, position: tuple[int, int], radius: int) -> int:
        """Count clips-aligned junctions within radius."""
        count = 0
        for junction in self._junctions.values():
            if junction.alignment != JunctionAlignment.CLIPS:
                continue
            if junction.position == position:
                continue
            if _manhattan_distance(position, junction.position) <= radius:
                count += 1
        return count

    @staticmethod
    def _parse_alignment(alignment_str: Optional[str]) -> JunctionAlignment:
        """Convert alignment string to enum."""
        if alignment_str == "cogs":
            return JunctionAlignment.COGS
        if alignment_str == "clips":
            return JunctionAlignment.CLIPS
        return JunctionAlignment.UNALIGNED


def _manhattan_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
    """Manhattan distance between two positions."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])
