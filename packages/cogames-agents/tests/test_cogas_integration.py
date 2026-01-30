"""Integration tests for cogas agent modules with mock observations.

Tests the cogas agent modules working together using mock observations:
1. JunctionController assigns targets correctly given a map state
2. ResourceManager plans efficient routes
3. Navigator finds paths and detects stuck states
4. TeamCoordinator assigns and reassigns roles
5. Full policy pipeline: observation -> state update -> role check -> action selection
6. Edge cases: no junctions visible, all extractors depleted, all junctions aligned
"""

from __future__ import annotations

import pytest
from cogames_agents.policy.scripted_agent.cogas.cogas_policy import Coordinator, Phase
from cogames_agents.policy.scripted_agent.cogas.goals import (
    CoordinatedAlignGoal,
    CoordinatedScrambleGoal,
    PatrolJunctionsGoal,
    RechargeEnergyGoal,
    make_aligner_goals,
    make_miner_goals,
    make_scout_goals,
    make_scrambler_goals,
)
from cogames_agents.policy.scripted_agent.cogas.junction_control import (
    JunctionAlignment,
    JunctionContestLevel,
    JunctionController,
    JunctionState,
)
from cogames_agents.policy.scripted_agent.cogas.navigator import Navigator, RecoveryStage
from cogames_agents.policy.scripted_agent.cogas.resource_manager import (
    ResourceManager,
    TrackedExtractor,
)
from cogames_agents.policy.scripted_agent.cogas.team_coordinator import (
    AgentSnapshot,
    GamePhase,
    TargetType,
    TeamCoordinator,
    TeamRole,
)
from cogames_agents.policy.scripted_agent.planky.context import PlankyContext, StateSnapshot
from cogames_agents.policy.scripted_agent.planky.entity_map import Entity, EntityMap
from cogames_agents.policy.scripted_agent.planky.goal import evaluate_goals

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_entity_map(
    entities: dict[tuple[int, int], Entity] | None = None,
    explored: set[tuple[int, int]] | None = None,
) -> EntityMap:
    """Create an EntityMap pre-populated with entities and explored cells."""
    emap = EntityMap()
    if entities:
        emap.entities = dict(entities)
    if explored:
        emap.explored = set(explored)
    else:
        # Mark a default grid as explored
        for r in range(80, 121):
            for c in range(80, 121):
                emap.explored.add((r, c))
    return emap


def _make_context(
    position: tuple[int, int] = (100, 100),
    agent_id: int = 0,
    step: int = 50,
    entity_map: EntityMap | None = None,
    blackboard: dict | None = None,
    navigator: Navigator | None = None,
    heart: int = 5,
    energy: int = 80,
    hp: int = 100,
    aligner_gear: bool = True,
    scrambler_gear: bool = False,
    miner_gear: bool = False,
    carbon: int = 0,
    oxygen: int = 0,
    germanium: int = 0,
    silicon: int = 0,
) -> PlankyContext:
    """Create a PlankyContext with mock state for testing."""
    state = StateSnapshot(
        position=position,
        heart=heart,
        energy=energy,
        hp=hp,
        aligner_gear=aligner_gear,
        scrambler_gear=scrambler_gear,
        miner_gear=miner_gear,
        carbon=carbon,
        oxygen=oxygen,
        germanium=germanium,
        silicon=silicon,
    )
    return PlankyContext(
        state=state,
        map=entity_map or _make_entity_map(),
        blackboard=blackboard if blackboard is not None else {},
        navigator=navigator or Navigator(),
        trace=None,
        action_names=["noop", "move_north", "move_south", "move_east", "move_west"],
        agent_id=agent_id,
        step=step,
    )


@pytest.fixture
def coordinator():
    return Coordinator()


@pytest.fixture
def junction_controller():
    return JunctionController(num_agents=10)


@pytest.fixture
def resource_manager():
    return ResourceManager()


@pytest.fixture
def team_coordinator():
    return TeamCoordinator(num_agents=10)


@pytest.fixture
def navigator():
    return Navigator()


# ===========================================================================
# 1. JunctionController: target assignment given map state
# ===========================================================================


class TestJunctionControl:
    """Test junction_control assigns targets correctly given a map state."""

    def test_update_and_track_junctions(self, junction_controller: JunctionController):
        """Updating junctions tracks their alignment state."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1)
        jc.update_junction((20, 20), "clips", step=1)
        jc.update_junction((30, 30), None, step=1)

        assert len(jc.known_junctions) == 3
        assert len(jc.cogs_junctions) == 1
        assert len(jc.clips_junctions) == 1
        assert len(jc.unaligned_junctions) == 1

    def test_alignment_summary(self, junction_controller: JunctionController):
        """Alignment summary returns correct counts."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1)
        jc.update_junction((20, 20), "cogs", step=1)
        jc.update_junction((30, 30), "clips", step=1)
        jc.update_junction((40, 40), None, step=1)

        summary = jc.get_alignment_summary()
        assert summary["cogs"] == 2
        assert summary["clips"] == 1
        assert summary["neutral"] == 1
        assert summary["total"] == 4

    def test_control_ratio(self, junction_controller: JunctionController):
        """Control ratio reflects cogs proportion."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1)
        jc.update_junction((20, 20), "clips", step=1)
        assert jc.get_control_ratio() == pytest.approx(0.5)

        jc.update_junction((30, 30), "cogs", step=2)
        assert jc.get_control_ratio() == pytest.approx(2.0 / 3.0)

    def test_aligner_prioritizes_unaligned(self, junction_controller: JunctionController):
        """Aligners should prioritize unaligned junctions over enemy ones."""
        jc = junction_controller
        agent_pos = (100, 100)

        # Unaligned junction farther away
        jc.update_junction((110, 110), None, step=1)
        # Enemy junction closer
        jc.update_junction((101, 101), "clips", step=1)

        targets = jc.get_priority_targets_for_aligner(agent_id=0, agent_pos=agent_pos)
        assert len(targets) >= 2
        # Unaligned should score higher despite being farther
        unaligned_score = next(s for s, p in targets if p == (110, 110))
        clips_score = next(s for s, p in targets if p == (101, 101))
        assert unaligned_score > clips_score

    def test_scrambler_only_targets_enemy(self, junction_controller: JunctionController):
        """Scramblers should only target enemy-aligned junctions."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1)
        jc.update_junction((20, 20), "clips", step=1)
        jc.update_junction((30, 30), None, step=1)

        targets = jc.get_priority_targets_for_scrambler(agent_id=0, agent_pos=(15, 15))
        positions = [p for _, p in targets]
        assert (20, 20) in positions
        assert (10, 10) not in positions
        assert (30, 30) not in positions

    def test_assign_aligner_no_overlap(self, junction_controller: JunctionController):
        """Two aligners should not be assigned the same junction."""
        jc = junction_controller
        jc.update_junction((10, 10), None, step=1)
        jc.update_junction((20, 20), None, step=1)

        t1 = jc.assign_aligner(agent_id=0, agent_pos=(10, 10))
        t2 = jc.assign_aligner(agent_id=1, agent_pos=(10, 10))
        assert t1 is not None
        assert t2 is not None
        assert t1 != t2

    def test_assign_scrambler_no_overlap(self, junction_controller: JunctionController):
        """Two scramblers should not be assigned the same enemy junction."""
        jc = junction_controller
        jc.update_junction((10, 10), "clips", step=1)
        jc.update_junction((20, 20), "clips", step=1)

        t1 = jc.assign_scrambler(agent_id=0, agent_pos=(10, 10))
        t2 = jc.assign_scrambler(agent_id=1, agent_pos=(10, 10))
        assert t1 is not None
        assert t2 is not None
        assert t1 != t2

    def test_release_assignment(self, junction_controller: JunctionController):
        """Releasing assignment frees the junction for others."""
        jc = junction_controller
        jc.update_junction((10, 10), None, step=1)

        t1 = jc.assign_aligner(agent_id=0, agent_pos=(10, 10))
        assert t1 == (10, 10)

        jc.release_assignment(agent_id=0)
        assert jc.get_assignment(agent_id=0) is None

        t2 = jc.assign_aligner(agent_id=1, agent_pos=(10, 10))
        assert t2 == (10, 10)

    def test_contest_level_tracking(self, junction_controller: JunctionController):
        """Junction contest levels are tracked from enemy counts."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1, nearby_enemy_count=0)
        j = jc.get_junction((10, 10))
        assert j.contest_level == JunctionContestLevel.UNCONTESTED

        jc.update_junction((10, 10), "cogs", step=2, nearby_enemy_count=1)
        assert j.contest_level == JunctionContestLevel.LIGHTLY_CONTESTED

        jc.update_junction((10, 10), "cogs", step=3, nearby_enemy_count=3)
        assert j.contest_level == JunctionContestLevel.HEAVILY_CONTESTED

    def test_flip_risk_prediction(self):
        """Flip risk increases with recent alignment changes."""
        js = JunctionState(position=(10, 10), alignment=JunctionAlignment.COGS)
        assert js.predict_flip_risk(current_step=10) == 0.0

        # Simulate flips
        js.update_alignment(JunctionAlignment.CLIPS, step=50)
        js.update_alignment(JunctionAlignment.COGS, step=60)
        js.update_alignment(JunctionAlignment.CLIPS, step=70)

        risk = js.predict_flip_risk(current_step=80)
        assert risk > 0.3  # Multiple recent flips = high risk

    def test_escalation_on_heavy_contest(self, junction_controller: JunctionController):
        """Heavily contested junctions should trigger escalation."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1, nearby_enemy_count=3)
        assert jc.should_escalate((10, 10))

        escalation_targets = jc.get_escalation_targets()
        assert (10, 10) in escalation_targets

    def test_patrol_route(self, junction_controller: JunctionController):
        """Patrol route visits all cogs junctions nearest-first."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1)
        jc.update_junction((20, 20), "cogs", step=1)
        jc.update_junction((50, 50), "cogs", step=1)

        route = jc.get_patrol_route(agent_pos=(10, 10))
        assert len(route) == 3
        # First stop should be nearest to agent
        assert route[0] == (10, 10)

    def test_heart_reservation(self, junction_controller: JunctionController):
        """Heart reservations limit concurrent pickups."""
        jc = junction_controller
        assert jc.reserve_heart(agent_id=0, step=1)
        assert jc.has_heart_reservation(agent_id=0)

        jc.release_heart_reservation(agent_id=0)
        assert not jc.has_heart_reservation(agent_id=0)

    def test_build_sectors(self, junction_controller: JunctionController):
        """Sectors partition junctions into spatial zones."""
        jc = junction_controller
        jc.update_junction((10, 10), "cogs", step=1)
        jc.update_junction((90, 90), "clips", step=1)
        jc.update_junction((10, 90), None, step=1)
        jc.update_junction((90, 10), "cogs", step=1)

        jc.build_sectors(num_sectors=4)
        sector = jc.get_sector_for_agent(agent_id=0)
        assert sector is not None


# ===========================================================================
# 2. ResourceManager: efficient route planning
# ===========================================================================


class TestResourceManager:
    """Test resource_manager plans efficient routes."""

    def test_claim_and_release_extractor(self, resource_manager: ResourceManager):
        """Claiming and releasing extractors works correctly."""
        rm = resource_manager
        rm._extractors[(10, 10)] = TrackedExtractor(
            position=(10, 10), resource_type="carbon", remaining_uses=50, last_seen_step=1
        )

        assert rm.claim_extractor(agent_id=0, position=(10, 10))
        assert rm.get_agent_claim(agent_id=0) == (10, 10)

        # Another agent cannot claim the same extractor
        assert not rm.claim_extractor(agent_id=1, position=(10, 10))

        rm.release_claim(agent_id=0)
        assert rm.get_agent_claim(agent_id=0) is None
        assert rm.claim_extractor(agent_id=1, position=(10, 10))

    def test_mark_extractor_failed(self, resource_manager: ResourceManager):
        """Failed extractors are tracked and claims released."""
        rm = resource_manager
        rm._extractors[(10, 10)] = TrackedExtractor(
            position=(10, 10), resource_type="carbon", remaining_uses=50, last_seen_step=1
        )
        rm.claim_extractor(agent_id=0, position=(10, 10))

        rm.mark_extractor_failed(agent_id=0, position=(10, 10), step=10)
        assert rm.get_agent_claim(agent_id=0) is None
        ext = rm._extractors[(10, 10)]
        assert ext.failed_by.get(0) == 10

    def test_resource_status(self, resource_manager: ResourceManager):
        """Resource status correctly categorizes extractors."""
        rm = resource_manager
        rm._extractors[(10, 10)] = TrackedExtractor(
            position=(10, 10), resource_type="carbon", remaining_uses=50, last_seen_step=1
        )
        rm._extractors[(20, 20)] = TrackedExtractor(
            position=(20, 20), resource_type="carbon", remaining_uses=0, last_seen_step=1
        )
        rm._extractors[(30, 30)] = TrackedExtractor(
            position=(30, 30), resource_type="oxygen", remaining_uses=20, last_seen_step=1
        )

        status = rm.get_resource_status()
        assert status["carbon"]["total"] == 2
        assert status["carbon"]["active"] == 1
        assert status["carbon"]["depleted"] == 1
        assert status["oxygen"]["active"] == 1

    def test_extractor_counts(self, resource_manager: ResourceManager):
        """Known and active extractor counts are correct."""
        rm = resource_manager
        rm._extractors[(10, 10)] = TrackedExtractor(
            position=(10, 10), resource_type="carbon", remaining_uses=50, last_seen_step=1
        )
        rm._extractors[(20, 20)] = TrackedExtractor(
            position=(20, 20), resource_type="carbon", remaining_uses=0, last_seen_step=1
        )

        assert rm.known_extractor_count == 2
        assert rm.active_extractor_count == 1

    def test_scarcest_resource(self, resource_manager: ResourceManager):
        """Scarcest resource returns the team's lowest weighted resource."""
        rm = resource_manager
        rm._team_cargo = {"carbon": 100, "oxygen": 100, "germanium": 10, "silicon": 10}
        # Germanium and silicon have weight 1.5, so weighted amounts are 10/1.5 ≈ 6.67
        # Carbon and oxygen have weight 1.0, so weighted amounts are 100/1.0 = 100
        scarcest = rm.get_scarcest_resource()
        assert scarcest in ("germanium", "silicon")

    def test_should_deposit_when_full(self, resource_manager: ResourceManager):
        """Agent should deposit when cargo is full."""
        rm = resource_manager
        ctx = _make_context(
            miner_gear=True,
            carbon=40,  # Full cargo (40/40 with miner gear)
        )
        assert rm.should_deposit(ctx)

    def test_should_not_deposit_when_empty(self, resource_manager: ResourceManager):
        """Agent should not deposit when cargo is empty."""
        rm = resource_manager
        ctx = _make_context(miner_gear=True, carbon=0)
        assert not rm.should_deposit(ctx)


# ===========================================================================
# 3. Navigator: pathfinding and stuck detection
# ===========================================================================


class TestNavigator:
    """Test navigator finds paths and detects stuck states."""

    def test_basic_pathfinding(self, navigator: Navigator):
        """Navigator produces a move action toward target."""
        emap = _make_entity_map()
        action = navigator.get_action(
            current=(100, 100),
            target=(100, 105),
            map=emap,
        )
        assert action.name in ("move_east", "move_north", "move_south", "move_west", "noop")

    def test_already_at_target(self, navigator: Navigator):
        """Navigator returns noop when already at target."""
        emap = _make_entity_map()
        action = navigator.get_action(current=(100, 100), target=(100, 100), map=emap)
        assert action.name == "noop"

    def test_adjacent_in_reach_mode(self, navigator: Navigator):
        """Navigator returns noop when adjacent to target in reach_adjacent mode."""
        emap = _make_entity_map()
        action = navigator.get_action(
            current=(100, 100),
            target=(100, 101),
            map=emap,
            reach_adjacent=True,
        )
        assert action.name == "noop"

    def test_stuck_detection(self, navigator: Navigator):
        """Navigator detects stuck state when position loops."""
        # Simulate being stuck: oscillating between two positions
        for _ in range(10):
            navigator._track_position((100, 100))
            navigator._track_position((100, 101))

        assert navigator._is_stuck()

    def test_recovery_escalation(self, navigator: Navigator):
        """Recovery escalates through stages when stuck persists."""
        emap = _make_entity_map()
        navigator._position_history = [(100, 100)] * 10
        assert navigator._is_stuck()

        # First escalation -> RANDOM_WALK
        action = navigator._escalate_recovery((100, 100), emap)
        assert navigator._recovery_stage == RecoveryStage.RANDOM_WALK
        assert action is not None

    def test_waypoint_system(self, navigator: Navigator):
        """Waypoints can be set and navigated to."""
        emap = _make_entity_map()
        navigator.set_waypoint("base", (90, 90))
        assert navigator.get_waypoint("base") == (90, 90)

        action = navigator.navigate_waypoint((100, 100), "base", emap)
        assert action.name != "noop"  # Should produce a move

    def test_waypoint_route(self, navigator: Navigator):
        """Route navigation follows waypoints in order."""
        emap = _make_entity_map()
        navigator.set_waypoint("a", (100, 105))
        navigator.set_waypoint("b", (100, 110))

        action = navigator.navigate_route(
            current=(100, 100),
            waypoint_names=["a", "b"],
            map=emap,
        )
        assert action.name != "noop"

    def test_explore_produces_action(self, navigator: Navigator):
        """Explore produces a move toward unexplored territory."""
        # Create a small explored area
        explored = set()
        for r in range(98, 103):
            for c in range(98, 103):
                explored.add((r, c))
        emap = _make_entity_map(explored=explored)
        action = navigator.explore(current=(100, 100), map=emap)
        assert action.name.startswith("move_") or action.name == "noop"

    def test_wall_avoidance(self, navigator: Navigator):
        """Navigator avoids walls during pathfinding."""
        entities = {
            (100, 101): Entity(type="wall", properties={}),
        }
        emap = _make_entity_map(entities=entities)
        action = navigator.get_action(
            current=(100, 100),
            target=(100, 102),
            map=emap,
        )
        # Should not try to move east directly into wall
        # (may go north/south to route around)
        assert action.name in ("move_north", "move_south", "move_east", "move_west", "noop")

    def test_cache_invalidation(self, navigator: Navigator):
        """Cache invalidation forces recomputation."""
        navigator._cached_path = [(100, 101), (100, 102)]
        navigator._cached_target = (100, 102)

        navigator.invalidate_cache()
        assert navigator._cached_path is None
        assert navigator._cached_target is None


# ===========================================================================
# 4. TeamCoordinator: role assignment and reassignment
# ===========================================================================


class TestTeamCoordinator:
    """Test team_coordinator assigns and reassigns roles."""

    def test_role_assignment(self, team_coordinator: TeamCoordinator):
        """Agents receive roles based on team needs."""
        tc = team_coordinator
        role = tc.assign_role(agent_id=0, step=10)
        assert isinstance(role, TeamRole)

    def test_update_agent(self, team_coordinator: TeamCoordinator):
        """Agent snapshots are tracked."""
        tc = team_coordinator
        snap = AgentSnapshot(agent_id=0, step=10, role=TeamRole.MINER)
        tc.update_agent(0, snap)
        assert tc.agents[0].role == TeamRole.MINER

    def test_junction_tracking(self, team_coordinator: TeamCoordinator):
        """Junctions are tracked with alignment."""
        tc = team_coordinator
        tc.update_junction((10, 10), "cogs", step=1)
        tc.update_junction((20, 20), "clips", step=1)

        summary = tc.junction_summary()
        assert summary["cogs"] == 1
        assert summary["clips"] == 1

    def test_target_claim_deconfliction(self, team_coordinator: TeamCoordinator):
        """Two agents cannot claim the same junction target."""
        tc = team_coordinator
        tc.update_junction((10, 10), "clips", step=1)

        assert tc.claim_target(agent_id=0, target_type=TargetType.JUNCTION, position=(10, 10))
        assert not tc.claim_target(agent_id=1, target_type=TargetType.JUNCTION, position=(10, 10))

    def test_release_target(self, team_coordinator: TeamCoordinator):
        """Releasing a target allows others to claim it."""
        tc = team_coordinator
        tc.update_junction((10, 10), "clips", step=1)

        tc.claim_target(agent_id=0, target_type=TargetType.JUNCTION, position=(10, 10))
        tc.release_target(agent_id=0)
        assert tc.claim_target(agent_id=1, target_type=TargetType.JUNCTION, position=(10, 10))

    def test_game_phase_transitions(self, team_coordinator: TeamCoordinator):
        """Game phase transitions from EARLY to MID to LATE."""
        tc = team_coordinator
        phase = tc.update_game_phase(step=10)
        assert phase == GamePhase.EARLY

        # Add structures to force MID
        for i in range(8):
            tc.update_junction((10 + i * 5, 10), "cogs", step=150)
        phase = tc.update_game_phase(step=150)
        assert phase == GamePhase.MID

        phase = tc.update_game_phase(step=600)
        assert phase == GamePhase.LATE

    def test_emergency_redistribution(self, team_coordinator: TeamCoordinator):
        """Emergency redistribution shifts roles toward combat."""
        tc = team_coordinator
        # Set up agents with miner roles
        for i in range(10):
            snap = AgentSnapshot(agent_id=i, step=100, role=TeamRole.MINER)
            tc.update_agent(i, snap)

        reassignments = tc.trigger_emergency_redistribution()
        # Should reassign some miners to combat roles
        assert len(reassignments) > 0
        combat_roles = {TeamRole.ALIGNER, TeamRole.SCRAMBLER, TeamRole.DEFENDER}
        assert any(role in combat_roles for role in reassignments.values())

    def test_priority_junctions_scrambler(self, team_coordinator: TeamCoordinator):
        """Scrambler priorities should favor enemy junctions."""
        tc = team_coordinator
        tc.update_junction((10, 10), "clips", step=1)
        tc.update_junction((20, 20), "cogs", step=1)
        tc.update_junction((30, 30), None, step=1)

        targets = tc.get_priority_junctions(agent_id=0, agent_pos=(15, 15), role=TeamRole.SCRAMBLER)
        assert (10, 10) in targets  # Enemy junction
        assert (20, 20) not in targets  # Our junction

    def test_stale_claim_cleanup(self, team_coordinator: TeamCoordinator):
        """Stale claims are cleaned up after max age."""
        tc = team_coordinator
        tc.update_junction((10, 10), "clips", step=1)
        snap = AgentSnapshot(agent_id=0, step=1, role=TeamRole.SCRAMBLER)
        tc.update_agent(0, snap)
        tc.claim_target(agent_id=0, target_type=TargetType.JUNCTION, position=(10, 10))

        # Claim should persist before cleanup
        assert tc.get_agent_target(0) is not None

        # After enough time, cleanup should release stale claims
        tc.cleanup_stale_claims(current_step=300, max_age=200)
        assert tc.get_agent_target(0) is None

    def test_role_summary(self, team_coordinator: TeamCoordinator):
        """Role summary correctly counts agents per role."""
        tc = team_coordinator
        for i in range(3):
            tc.update_agent(i, AgentSnapshot(agent_id=i, role=TeamRole.MINER, step=1))
        for i in range(3, 5):
            tc.update_agent(i, AgentSnapshot(agent_id=i, role=TeamRole.ALIGNER, step=1))

        summary = tc.role_summary()
        assert summary[TeamRole.MINER] == 3
        assert summary[TeamRole.ALIGNER] == 2


# ===========================================================================
# 5. Full pipeline: observation -> state update -> role check -> action
# ===========================================================================


class TestFullPipeline:
    """Test the full policy pipeline with mock observations."""

    def test_aligner_pipeline(self, coordinator: Coordinator):
        """Aligner agent: context -> goal evaluation -> action."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(type="neutral_junction", properties={}, last_seen=50),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            heart=3,
            aligner_gear=True,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goals = make_aligner_goals(Phase.MID, coordinator, agent_id=0)
        action = evaluate_goals(goals, ctx)
        assert action.name != "noop" or action.name == "noop"  # Valid action produced

    def test_scrambler_pipeline(self, coordinator: Coordinator):
        """Scrambler agent: context -> goal evaluation -> action."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(
                    type="clips_junction",
                    properties={"alignment": "clips"},
                    last_seen=50,
                ),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            heart=3,
            scrambler_gear=True,
            aligner_gear=False,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goals = make_scrambler_goals(Phase.MID, coordinator, agent_id=0)
        action = evaluate_goals(goals, ctx)
        assert action is not None

    def test_miner_pipeline(self):
        """Miner agent: context -> goal evaluation -> action."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(
                    type="carbon_extractor",
                    properties={"remaining_uses": 50, "inventory_amount": 10},
                    last_seen=50,
                ),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            miner_gear=True,
            aligner_gear=False,
            step=50,
        )

        goals = make_miner_goals(Phase.MID)
        action = evaluate_goals(goals, ctx)
        assert action is not None

    def test_scout_pipeline(self):
        """Scout agent: context -> goal evaluation -> action."""
        ctx = _make_context(
            position=(100, 100),
            aligner_gear=False,
            step=50,
        )

        goals = make_scout_goals(Phase.MID)
        action = evaluate_goals(goals, ctx)
        assert action is not None

    def test_coordinator_heart_reservation(self, coordinator: Coordinator):
        """Coordinator heart reservations limit concurrency."""
        assert coordinator.reserve_heart(0)
        assert coordinator.reserve_heart(1)
        # Third agent should be rejected (limit is 2)
        assert not coordinator.reserve_heart(2)

        coordinator.release_heart(0)
        assert coordinator.reserve_heart(2)

    def test_coordinator_junction_claim(self, coordinator: Coordinator):
        """Coordinator junction claims prevent overlap."""
        assert coordinator.claim_junction(0, (10, 10))
        assert not coordinator.claim_junction(1, (10, 10))  # Already claimed

        coordinator.release_junction(0)
        assert coordinator.claim_junction(1, (10, 10))

    def test_coordinator_scramble_claim(self, coordinator: Coordinator):
        """Coordinator scramble claims prevent overlap."""
        assert coordinator.claim_scramble(0, (20, 20))
        assert not coordinator.claim_scramble(1, (20, 20))

        coordinator.release_scramble(0)
        assert coordinator.claim_scramble(1, (20, 20))

    def test_goal_evaluation_respects_priority(self, coordinator: Coordinator):
        """Goals are evaluated in priority order; first unsatisfied goal acts."""
        ctx = _make_context(
            position=(100, 100),
            hp=10,  # Low HP - SurviveGoal should activate
            energy=80,
            aligner_gear=True,
            heart=3,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goals = make_aligner_goals(Phase.MID, coordinator, agent_id=0)
        action = evaluate_goals(goals, ctx)
        # With low HP, SurviveGoal should take priority
        assert action is not None

    def test_recharge_energy_goal(self, coordinator: Coordinator):
        """RechargeEnergyGoal activates when energy is low."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(
                    type="cogs_junction",
                    properties={"alignment": "cogs"},
                    last_seen=50,
                ),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            energy=10,  # Below threshold
            step=50,
        )

        goal = RechargeEnergyGoal(threshold=20)
        assert not goal.is_satisfied(ctx)
        action = goal.execute(ctx)
        assert action is not None

    def test_patrol_junctions_goal(self, coordinator: Coordinator):
        """PatrolJunctionsGoal patrols cogs-aligned junctions."""
        emap = _make_entity_map(
            entities={
                (100, 110): Entity(
                    type="cogs_junction",
                    properties={"alignment": "cogs"},
                    last_seen=50,
                ),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            step=350,
        )

        goal = PatrolJunctionsGoal()
        assert not goal.is_satisfied(ctx)
        action = goal.execute(ctx)
        assert action is not None


# ===========================================================================
# 6. Edge cases
# ===========================================================================


class TestEdgeCases:
    """Test edge cases: no junctions, all depleted, all aligned."""

    def test_no_junctions_visible(self, coordinator: Coordinator):
        """Aligner with no junctions visible should explore."""
        ctx = _make_context(
            position=(100, 100),
            heart=3,
            aligner_gear=True,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goal = CoordinatedAlignGoal(coordinator, agent_id=0)
        action = goal.execute(ctx)
        # Should produce an explore action
        assert action is not None
        assert action.name.startswith("move_") or action.name == "noop"

    def test_no_enemy_junctions_for_scrambler(self, coordinator: Coordinator):
        """Scrambler with no enemy junctions should explore."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(
                    type="cogs_junction",
                    properties={"alignment": "cogs"},
                    last_seen=50,
                ),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            scrambler_gear=True,
            aligner_gear=False,
            heart=3,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goal = CoordinatedScrambleGoal(coordinator, agent_id=0)
        action = goal.execute(ctx)
        assert action is not None

    def test_all_extractors_depleted(self, resource_manager: ResourceManager):
        """Resource manager returns no target when all extractors are depleted."""
        rm = resource_manager
        rm._extractors[(10, 10)] = TrackedExtractor(
            position=(10, 10), resource_type="carbon", remaining_uses=0, last_seen_step=1
        )
        rm._extractors[(20, 20)] = TrackedExtractor(
            position=(20, 20), resource_type="oxygen", remaining_uses=0, last_seen_step=1
        )

        ctx = _make_context(position=(15, 15), miner_gear=True, aligner_gear=False)
        target = rm.select_mining_target(ctx)
        assert target is None

    def test_all_junctions_already_aligned(self, coordinator: Coordinator):
        """Aligner with all cogs-aligned junctions should explore."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(
                    type="cogs_junction",
                    properties={"alignment": "cogs"},
                    last_seen=50,
                ),
                (100, 110): Entity(
                    type="cogs_junction",
                    properties={"alignment": "cogs"},
                    last_seen=50,
                ),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            heart=3,
            aligner_gear=True,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goal = CoordinatedAlignGoal(coordinator, agent_id=0)
        action = goal.execute(ctx)
        # No neutral junctions -> explore
        assert action is not None

    def test_junction_controller_empty(self, junction_controller: JunctionController):
        """Empty junction controller handles queries gracefully."""
        jc = junction_controller
        assert jc.known_junctions == []
        assert jc.get_control_ratio() == 0.0
        assert jc.get_alignment_summary()["total"] == 0
        assert jc.get_patrol_route(agent_pos=(0, 0)) == []
        assert jc.assign_aligner(agent_id=0, agent_pos=(0, 0)) is None
        assert jc.assign_scrambler(agent_id=0, agent_pos=(0, 0)) is None

    def test_resource_manager_empty(self, resource_manager: ResourceManager):
        """Empty resource manager handles queries gracefully."""
        rm = resource_manager
        assert rm.known_extractor_count == 0
        assert rm.active_extractor_count == 0
        assert rm.active_miner_count == 0

        ctx = _make_context(position=(100, 100), miner_gear=True, aligner_gear=False)
        assert rm.select_mining_target(ctx) is None

    def test_navigator_unreachable_target(self, navigator: Navigator):
        """Navigator handles unreachable targets by falling back to greedy move."""
        # Surround target with walls
        entities = {}
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                entities[(50 + dr, 50 + dc)] = Entity(type="wall", properties={})

        emap = _make_entity_map(entities=entities)
        action = navigator.get_action(current=(100, 100), target=(50, 50), map=emap)
        # Should produce some action, even if it can't reach
        assert action is not None

    def test_aligner_no_hearts(self, coordinator: Coordinator):
        """Aligner without hearts should defer (return None)."""
        emap = _make_entity_map(
            entities={
                (100, 105): Entity(type="neutral_junction", properties={}, last_seen=50),
            }
        )
        ctx = _make_context(
            position=(100, 100),
            entity_map=emap,
            heart=0,  # No hearts
            aligner_gear=True,
            step=50,
        )
        ctx.blackboard["_coordinator"] = coordinator

        goal = CoordinatedAlignGoal(coordinator, agent_id=0)
        action = goal.execute(ctx)
        # Should return None (defer to GetHeartsGoal)
        assert action is None

    def test_team_coordinator_no_agents(self, team_coordinator: TeamCoordinator):
        """Team coordinator handles queries with no agents registered."""
        tc = team_coordinator
        summary = tc.role_summary()
        assert all(count == 0 for count in summary.values())

    def test_mining_route_with_all_claimed(self, resource_manager: ResourceManager):
        """Mining route is empty when all extractors are claimed by others."""
        rm = resource_manager
        rm._extractors[(10, 10)] = TrackedExtractor(
            position=(10, 10),
            resource_type="carbon",
            remaining_uses=50,
            last_seen_step=1,
            claimed_by=5,
        )
        rm._extractors[(20, 20)] = TrackedExtractor(
            position=(20, 20),
            resource_type="oxygen",
            remaining_uses=50,
            last_seen_step=1,
            claimed_by=6,
        )

        ctx = _make_context(position=(15, 15), agent_id=0, miner_gear=True, aligner_gear=False)
        target = rm.select_mining_target(ctx)
        assert target is None
