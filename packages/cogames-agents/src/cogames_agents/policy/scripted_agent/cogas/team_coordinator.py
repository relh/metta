"""
Team Coordinator for CoGas multi-agent coordination.

Manages shared state across agents that share a single policy instance:
1. Role assignment at spawn based on URI params and game state
2. Dynamic role reassignment based on game conditions (junction control, score)
3. Target deconfliction - no two agents target the same junction/extractor
4. Priority queue for targets - agents pick from a shared ordered target list
5. Emergency coordination - aggressive role redistribution when score drops
6. Communication via shared state (agents share a policy instance)

Usage:
    coordinator = TeamCoordinator(num_agents=10)

    # Each agent calls on its step:
    coordinator.update_agent(agent_id, snapshot)
    role = coordinator.assign_role(agent_id)
    target = coordinator.claim_target(agent_id, target_type)
    coordinator.release_target(agent_id)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TeamRole(Enum):
    """Roles an agent can be assigned in the team."""

    MINER = "miner"
    SCOUT = "scout"
    ALIGNER = "aligner"
    SCRAMBLER = "scrambler"
    DEFENDER = "defender"


class TargetType(Enum):
    """Types of targets agents can claim."""

    JUNCTION = "junction"
    EXTRACTOR = "extractor"
    DEFEND_JUNCTION = "defend_junction"


class GamePhase(Enum):
    """High-level game phase for strategic decisions."""

    EARLY = "early"  # Explore, discover map
    MID = "mid"  # Establish junction control, mine resources
    LATE = "late"  # Defend leads, aggressive if behind
    EMERGENCY = "emergency"  # Score dropping, redistribute aggressively


@dataclass
class AgentSnapshot:
    """Lightweight per-agent state snapshot for coordination decisions."""

    agent_id: int
    step: int = 0
    role: TeamRole = TeamRole.MINER
    has_gear: bool = False
    position: tuple[int, int] = (0, 0)
    energy: int = 100
    heart_count: int = 0
    influence_count: int = 0
    total_cargo: int = 0
    assigned_target: Optional[tuple[int, int]] = None
    structures_seen: int = 0


@dataclass
class JunctionState:
    """Tracks the state of a known junction (junction/supply depot)."""

    position: tuple[int, int]
    alignment: Optional[str] = None  # "cogs", "clips", or None (neutral)
    last_seen_step: int = 0
    claimed_by: Optional[int] = None  # agent_id that claimed this target
    defend_claimed_by: Optional[int] = None  # agent_id defending this junction


@dataclass
class ExtractorState:
    """Tracks the state of a known extractor for deconfliction."""

    position: tuple[int, int]
    resource_type: str
    depleted: bool = False
    last_seen_step: int = 0
    claimed_by: Optional[int] = None  # agent_id that claimed this target


@dataclass
class ScoreTracker:
    """Tracks score history for emergency detection."""

    scores: list[int] = field(default_factory=list)
    check_interval: int = 50  # Check score every N steps
    decline_threshold: int = 3  # Number of consecutive declines to trigger emergency
    last_check_step: int = 0

    def record(self, score: int, step: int) -> None:
        if step - self.last_check_step >= self.check_interval:
            self.scores.append(score)
            self.last_check_step = step
            # Keep only recent history
            if len(self.scores) > 20:
                self.scores = self.scores[-20:]

    def is_declining(self) -> bool:
        """Check if score has been declining over recent checks."""
        if len(self.scores) < self.decline_threshold + 1:
            return False
        recent = self.scores[-(self.decline_threshold + 1) :]
        return all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))


# Default role distribution ratios by game phase
_DEFAULT_ROLE_RATIOS: dict[GamePhase, dict[TeamRole, float]] = {
    GamePhase.EARLY: {
        TeamRole.SCOUT: 0.3,
        TeamRole.MINER: 0.5,
        TeamRole.ALIGNER: 0.1,
        TeamRole.SCRAMBLER: 0.1,
        TeamRole.DEFENDER: 0.0,
    },
    GamePhase.MID: {
        TeamRole.SCOUT: 0.1,
        TeamRole.MINER: 0.4,
        TeamRole.ALIGNER: 0.2,
        TeamRole.SCRAMBLER: 0.2,
        TeamRole.DEFENDER: 0.1,
    },
    GamePhase.LATE: {
        TeamRole.SCOUT: 0.05,
        TeamRole.MINER: 0.35,
        TeamRole.ALIGNER: 0.15,
        TeamRole.SCRAMBLER: 0.15,
        TeamRole.DEFENDER: 0.3,
    },
    GamePhase.EMERGENCY: {
        TeamRole.SCOUT: 0.05,
        TeamRole.MINER: 0.2,
        TeamRole.ALIGNER: 0.25,
        TeamRole.SCRAMBLER: 0.25,
        TeamRole.DEFENDER: 0.25,
    },
}

# Thresholds for game phase transitions
_EARLY_PHASE_MAX_STEP = 100
_MID_PHASE_MAX_STEP = 500
_MIN_STRUCTURES_FOR_MID = 6
_JUNCTION_WIN_RATIO_FOR_DEFENSE = 0.6  # If we control >60% of junctions, shift to defense


class TeamCoordinator:
    """Shared coordinator for multi-agent team strategy.

    This object is shared across all agents in a policy instance.
    Each agent calls update_agent() and assign_role() on its step.

    Target deconfliction ensures no two agents pursue the same
    junction or extractor simultaneously.
    """

    def __init__(
        self,
        num_agents: int,
        initial_roles: Optional[dict[int, TeamRole]] = None,
    ):
        self.num_agents = num_agents
        self.agents: dict[int, AgentSnapshot] = {}
        self.junctions: dict[tuple[int, int], JunctionState] = {}
        self.extractors: dict[tuple[int, int], ExtractorState] = {}
        self.score_tracker = ScoreTracker()
        self._game_phase = GamePhase.EARLY
        self._initial_roles = initial_roles or {}
        self._role_lock_until: dict[int, int] = {}  # agent_id -> step until role is locked
        self._role_lock_cooldown = 40  # Steps before an agent can switch roles again

        # Target claim tracking: agent_id -> (target_type, position)
        self._claims: dict[int, tuple[TargetType, tuple[int, int]]] = {}

    # ------------------------------------------------------------------
    # Agent state updates
    # ------------------------------------------------------------------

    def update_agent(self, agent_id: int, snapshot: AgentSnapshot) -> None:
        """Update the coordinator with an agent's latest state."""
        self.agents[agent_id] = snapshot

    def update_junction(
        self,
        position: tuple[int, int],
        alignment: Optional[str],
        step: int,
    ) -> None:
        """Update or register a known junction."""
        if position in self.junctions:
            junc = self.junctions[position]
            junc.alignment = alignment
            junc.last_seen_step = step
        else:
            self.junctions[position] = JunctionState(
                position=position,
                alignment=alignment,
                last_seen_step=step,
            )

    def update_extractor(
        self,
        position: tuple[int, int],
        resource_type: str,
        depleted: bool,
        step: int,
    ) -> None:
        """Update or register a known extractor."""
        if position in self.extractors:
            ext = self.extractors[position]
            ext.depleted = depleted
            ext.resource_type = resource_type
            ext.last_seen_step = step
        else:
            self.extractors[position] = ExtractorState(
                position=position,
                resource_type=resource_type,
                depleted=depleted,
                last_seen_step=step,
            )

    def update_score(self, score: int, step: int) -> None:
        """Record team score for emergency detection."""
        self.score_tracker.record(score, step)

    # ------------------------------------------------------------------
    # Game phase detection
    # ------------------------------------------------------------------

    @property
    def game_phase(self) -> GamePhase:
        return self._game_phase

    def update_game_phase(self, step: int) -> GamePhase:
        """Determine current game phase from step count, map knowledge, and score."""
        # Emergency overrides everything
        if self.score_tracker.is_declining():
            self._game_phase = GamePhase.EMERGENCY
            return self._game_phase

        if step < _EARLY_PHASE_MAX_STEP and len(self.junctions) < _MIN_STRUCTURES_FOR_MID:
            self._game_phase = GamePhase.EARLY
        elif step < _MID_PHASE_MAX_STEP:
            self._game_phase = GamePhase.MID
        else:
            self._game_phase = GamePhase.LATE

        # If we're winning on junctions in mid/late game, shift toward defense
        if self._game_phase in (GamePhase.MID, GamePhase.LATE):
            cogs_junctions = sum(1 for j in self.junctions.values() if j.alignment == "cogs")
            total_junctions = len(self.junctions)
            if total_junctions > 0 and cogs_junctions / total_junctions > _JUNCTION_WIN_RATIO_FOR_DEFENSE:
                # Winning - shift scramblers to defense
                if self._game_phase == GamePhase.MID:
                    # Stay mid but the role assignment will reflect the win
                    pass
                else:
                    self._game_phase = GamePhase.LATE

        return self._game_phase

    # ------------------------------------------------------------------
    # Role assignment
    # ------------------------------------------------------------------

    def assign_role(self, agent_id: int, step: int) -> TeamRole:
        """Assign or reassign a role to an agent based on team needs.

        Considers:
        - Initial role assignments from URI params
        - Current game phase and role ratios
        - Junction control state (shift scramblers to defense if winning)
        - Role lock cooldown to prevent thrashing
        """
        # Respect initial assignment for first spawn
        if agent_id in self._initial_roles and agent_id not in self.agents:
            return self._initial_roles[agent_id]

        # Respect role lock cooldown
        lock_until = self._role_lock_until.get(agent_id, 0)
        if step < lock_until:
            snapshot = self.agents.get(agent_id)
            if snapshot is not None:
                return snapshot.role
            return self._initial_roles.get(agent_id, TeamRole.MINER)

        # Update game phase
        self.update_game_phase(step)

        # Calculate target role counts from ratios
        ratios = _DEFAULT_ROLE_RATIOS[self._game_phase]
        target_counts = {role: max(1, round(ratio * self.num_agents)) for role, ratio in ratios.items() if ratio > 0}

        # Dynamic adjustment: if winning on junctions, reduce scramblers, increase defenders
        cogs_junctions = sum(1 for j in self.junctions.values() if j.alignment == "cogs")
        clips_junctions = sum(1 for j in self.junctions.values() if j.alignment == "clips")
        neutral_junctions = sum(1 for j in self.junctions.values() if j.alignment is None)

        if cogs_junctions > clips_junctions + neutral_junctions:
            # Winning - shift scramblers to defense
            scrambler_target = target_counts.get(TeamRole.SCRAMBLER, 0)
            shift = max(0, scrambler_target - 1)
            target_counts[TeamRole.SCRAMBLER] = max(1, scrambler_target - shift)
            target_counts[TeamRole.DEFENDER] = target_counts.get(TeamRole.DEFENDER, 0) + shift

        if clips_junctions > cogs_junctions:
            # Losing - need more scramblers and aligners
            miner_target = target_counts.get(TeamRole.MINER, 0)
            shift = max(0, miner_target - 2)
            target_counts[TeamRole.MINER] = max(2, miner_target - shift)
            target_counts[TeamRole.SCRAMBLER] = target_counts.get(TeamRole.SCRAMBLER, 0) + shift // 2
            target_counts[TeamRole.ALIGNER] = target_counts.get(TeamRole.ALIGNER, 0) + (shift - shift // 2)

        # Count current role distribution
        current_counts: dict[TeamRole, int] = {role: 0 for role in TeamRole}
        for aid, snap in self.agents.items():
            if aid != agent_id:  # Exclude self to avoid double-counting
                current_counts[snap.role] += 1

        # Find the role with the biggest deficit
        best_role = TeamRole.MINER
        best_deficit = -999
        for role, target in target_counts.items():
            deficit = target - current_counts.get(role, 0)
            if deficit > best_deficit:
                best_deficit = deficit
                best_role = role

        # Check if role actually changed
        current_snapshot = self.agents.get(agent_id)
        if current_snapshot is not None and current_snapshot.role != best_role:
            self._role_lock_until[agent_id] = step + self._role_lock_cooldown

        return best_role

    # ------------------------------------------------------------------
    # Target deconfliction
    # ------------------------------------------------------------------

    def claim_target(
        self,
        agent_id: int,
        target_type: TargetType,
        position: tuple[int, int],
    ) -> bool:
        """Attempt to claim a target. Returns True if successfully claimed.

        An agent can only hold one claim at a time. Claiming a new target
        releases any previous claim.
        """
        # Check if already claimed by another agent
        if target_type == TargetType.JUNCTION:
            junc = self.junctions.get(position)
            if junc is not None and junc.claimed_by is not None and junc.claimed_by != agent_id:
                # Already claimed by someone else
                return False
        elif target_type == TargetType.DEFEND_JUNCTION:
            junc = self.junctions.get(position)
            if junc is not None and junc.defend_claimed_by is not None and junc.defend_claimed_by != agent_id:
                return False
        elif target_type == TargetType.EXTRACTOR:
            ext = self.extractors.get(position)
            if ext is not None and ext.claimed_by is not None and ext.claimed_by != agent_id:
                return False

        # Release previous claim
        self.release_target(agent_id)

        # Set new claim
        self._claims[agent_id] = (target_type, position)

        if target_type == TargetType.JUNCTION:
            if position in self.junctions:
                self.junctions[position].claimed_by = agent_id
        elif target_type == TargetType.DEFEND_JUNCTION:
            if position in self.junctions:
                self.junctions[position].defend_claimed_by = agent_id
        elif target_type == TargetType.EXTRACTOR:
            if position in self.extractors:
                self.extractors[position].claimed_by = agent_id

        return True

    def release_target(self, agent_id: int) -> None:
        """Release any target claimed by this agent."""
        prev = self._claims.pop(agent_id, None)
        if prev is None:
            return

        target_type, position = prev
        if target_type == TargetType.JUNCTION:
            junc = self.junctions.get(position)
            if junc is not None and junc.claimed_by == agent_id:
                junc.claimed_by = None
        elif target_type == TargetType.DEFEND_JUNCTION:
            junc = self.junctions.get(position)
            if junc is not None and junc.defend_claimed_by == agent_id:
                junc.defend_claimed_by = None
        elif target_type == TargetType.EXTRACTOR:
            ext = self.extractors.get(position)
            if ext is not None and ext.claimed_by == agent_id:
                ext.claimed_by = None

    def get_agent_target(self, agent_id: int) -> Optional[tuple[TargetType, tuple[int, int]]]:
        """Get the current target claim for an agent."""
        return self._claims.get(agent_id)

    # ------------------------------------------------------------------
    # Priority target selection
    # ------------------------------------------------------------------

    def get_priority_junctions(
        self,
        agent_id: int,
        agent_pos: tuple[int, int],
        role: TeamRole,
    ) -> list[tuple[int, int]]:
        """Get prioritized list of junctions for an agent to target.

        Priority order depends on role:
        - SCRAMBLER: enemy (clips) junctions first, then neutral
        - ALIGNER: neutral junctions first, then unclaimed cogs junctions
        - DEFENDER: cogs-aligned junctions that need protection

        Excludes junctions already claimed by other agents.
        Returns positions sorted by priority (best first).
        """
        candidates: list[tuple[tuple[int, int], int]] = []  # (position, priority_score)

        for pos, junc in self.junctions.items():
            # Skip if claimed by another agent for the same purpose
            if role == TeamRole.SCRAMBLER:
                if junc.claimed_by is not None and junc.claimed_by != agent_id:
                    continue
                if junc.alignment == "clips":
                    score = 100  # Highest priority: enemy junctions
                elif junc.alignment is None:
                    score = 50  # Medium: neutral junctions
                else:
                    continue  # Skip cogs-aligned junctions
            elif role == TeamRole.ALIGNER:
                if junc.claimed_by is not None and junc.claimed_by != agent_id:
                    continue
                if junc.alignment is None:
                    score = 100  # Highest: neutral junctions
                elif junc.alignment == "clips":
                    score = 50  # Medium: enemy junctions (scramble first)
                else:
                    continue  # Skip already-aligned cogs junctions
            elif role == TeamRole.DEFENDER:
                if junc.defend_claimed_by is not None and junc.defend_claimed_by != agent_id:
                    continue
                if junc.alignment == "cogs":
                    score = 100  # Defend our junctions
                else:
                    continue
            else:
                continue

            # Distance penalty (prefer closer targets)
            dist = abs(pos[0] - agent_pos[0]) + abs(pos[1] - agent_pos[1])
            score -= dist // 5

            candidates.append((pos, score))

        # Sort by score descending (highest priority first)
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [pos for pos, _score in candidates]

    def get_priority_extractors(
        self,
        agent_id: int,
        agent_pos: tuple[int, int],
        needed_resources: Optional[set[str]] = None,
    ) -> list[tuple[int, int]]:
        """Get prioritized list of extractors for mining.

        Excludes extractors claimed by other agents and depleted extractors.
        Optionally filters by needed resource types.
        Returns positions sorted by distance (nearest first).
        """
        candidates: list[tuple[tuple[int, int], int]] = []

        for pos, ext in self.extractors.items():
            if ext.depleted:
                continue
            if ext.claimed_by is not None and ext.claimed_by != agent_id:
                continue
            if needed_resources is not None and ext.resource_type not in needed_resources:
                continue

            dist = abs(pos[0] - agent_pos[0]) + abs(pos[1] - agent_pos[1])
            candidates.append((pos, dist))

        candidates.sort(key=lambda x: x[1])
        return [pos for pos, _dist in candidates]

    # ------------------------------------------------------------------
    # Emergency coordination
    # ------------------------------------------------------------------

    def trigger_emergency_redistribution(self) -> dict[int, TeamRole]:
        """Aggressively redistribute roles when score is dropping.

        Pulls miners and scouts toward scrambler/aligner/defender roles
        to recover junction control.

        Returns a mapping of agent_id -> new_role for agents that should switch.
        """
        reassignments: dict[int, TeamRole] = {}

        # Count current roles
        role_counts: dict[TeamRole, list[int]] = {role: [] for role in TeamRole}
        for aid, snap in self.agents.items():
            role_counts[snap.role].append(aid)

        # Emergency ratios
        emergency_ratios = _DEFAULT_ROLE_RATIOS[GamePhase.EMERGENCY]
        target_counts = {
            role: max(1, round(ratio * self.num_agents)) for role, ratio in emergency_ratios.items() if ratio > 0
        }

        # Identify surplus and deficit roles
        for role, target in target_counts.items():
            current = len(role_counts.get(role, []))
            if current < target:
                # Need more of this role - pull from surplus roles
                deficit = target - current
                for donor_role in (TeamRole.MINER, TeamRole.SCOUT):
                    donor_agents = role_counts.get(donor_role, [])
                    donor_target = target_counts.get(donor_role, 0)
                    surplus = len(donor_agents) - donor_target
                    if surplus > 0 and deficit > 0:
                        to_move = min(surplus, deficit)
                        for _i in range(to_move):
                            aid = donor_agents.pop()
                            reassignments[aid] = role
                            role_counts[role].append(aid)
                            deficit -= 1

        return reassignments

    # ------------------------------------------------------------------
    # Stale claim cleanup
    # ------------------------------------------------------------------

    def cleanup_stale_claims(self, current_step: int, max_age: int = 200) -> None:
        """Release claims from agents that haven't updated recently.

        Prevents deadlocks where an agent claims a target but gets stuck
        or destroyed before releasing it.
        """
        stale_agents: list[int] = []
        for aid, snap in self.agents.items():
            if current_step - snap.step > max_age:
                stale_agents.append(aid)

        for aid in stale_agents:
            self.release_target(aid)

    # ------------------------------------------------------------------
    # Team summary (for debugging / vibe display)
    # ------------------------------------------------------------------

    def role_summary(self) -> dict[TeamRole, int]:
        """Get count of agents in each role."""
        counts: dict[TeamRole, int] = {role: 0 for role in TeamRole}
        for snap in self.agents.values():
            counts[snap.role] += 1
        return counts

    def junction_summary(self) -> dict[str, int]:
        """Get count of junctions by alignment."""
        counts = {"cogs": 0, "clips": 0, "neutral": 0}
        for junc in self.junctions.values():
            if junc.alignment == "cogs":
                counts["cogs"] += 1
            elif junc.alignment == "clips":
                counts["clips"] += 1
            else:
                counts["neutral"] += 1
        return counts
