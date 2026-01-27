"""
Unit tests for Pinky navigation - A* pathfinding and obstacle avoidance.

Tests verify:
- A* finds paths around obstacles
- Agents avoid bumping into objects
- Position tracking based on actual moves
- Internal map building and persistence
- Change detection for moving objects/agents
"""

from __future__ import annotations

from cogames_agents.policy.scripted_agent.pinky.services.map_tracker import MapTracker
from cogames_agents.policy.scripted_agent.pinky.services.navigator import Navigator
from cogames_agents.policy.scripted_agent.pinky.state import AgentState
from cogames_agents.policy.scripted_agent.pinky.types import CellType

from mettagrid.config.id_map import ObservationFeatureSpec
from mettagrid.simulator.interface import AgentObservation, ObservationToken


class MockPolicyEnvInfo:
    """Mock PolicyEnvInterface for testing."""

    def __init__(self):
        self.obs_height = 11
        self.obs_width = 11
        self.action_names = [
            "noop",
            "move_north",
            "move_south",
            "move_east",
            "move_west",
            "change_vibe_default",
            "change_vibe_miner",
        ]
        self.tag_id_to_name = {
            1: "type:agent",
            2: "type:wall",
            3: "type:carbon_extractor",
            4: "type:miner_station",
        }


def make_token(feature_name: str, row: int, col: int, value: int) -> ObservationToken:
    """Create a mock observation token.

    Note: ObservationToken.location is stored as (col, row) to match mettagrid convention.
    The row()/col() methods extract correctly: row() = location[1], col() = location[0].
    """
    feature = ObservationFeatureSpec(id=0, name=feature_name, normalization=255.0)
    return ObservationToken(
        feature=feature,
        location=(col, row),  # mettagrid convention: (col, row)
        value=value,
        raw_token=(0, 0, 0),
    )


def make_obs(tokens: list[ObservationToken], agent_id: int = 0) -> AgentObservation:
    """Create a mock agent observation."""
    return AgentObservation(agent_id=agent_id, tokens=tokens)


class TestAStarPathfinding:
    """Test A* pathfinding in get_direction_to_nearest."""

    def test_direct_path_no_obstacles(self):
        """Agent should move directly toward target when no obstacles."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target (extractor) is 3 cells south (row 8, col 5 in 11x11 grid)
        # Center is (5, 5)
        tokens = [
            make_token("tag", 8, 5, 3),  # carbon_extractor at (8, 5)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is not None, "Should find target"
        direction, target_pos = result
        assert direction == "south", f"Expected south, got {direction}"
        # Target at obs (8,5), center is (5,5), agent at world (100,100)
        # World pos = (100 + 3, 100 + 0) = (103, 100)
        assert target_pos == (103, 100), f"Expected target pos (103, 100), got {target_pos}"

    def test_direct_path_east(self):
        """Agent should move east toward target."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target is 3 cells east (row 5, col 8)
        tokens = [
            make_token("tag", 5, 8, 3),  # carbon_extractor at (5, 8)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is not None, "Should find target"
        direction, target_pos = result
        assert direction == "east", f"Expected east, got {direction}"

    def test_avoids_obstacle_south(self):
        """Agent should path around obstacle blocking direct route."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target is south, but wall blocks direct path
        # Center is (5, 5), target at (8, 5), wall at (6, 5)
        tokens = [
            make_token("tag", 8, 5, 3),  # carbon_extractor at (8, 5)
            make_token("tag", 6, 5, 2),  # wall blocking south at (6, 5)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is not None, "Should find path"
        direction, _ = result
        # Should go east or west to path around
        assert direction in ("east", "west"), f"Expected east or west to avoid wall, got {direction}"

    def test_avoids_agent_blocking_path(self):
        """Agent should path around another agent."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target is south, but another agent blocks direct path
        tokens = [
            make_token("tag", 8, 5, 3),  # carbon_extractor at (8, 5)
            make_token("tag", 6, 5, 1),  # agent blocking at (6, 5)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is not None, "Should find path"
        direction, _ = result
        # Should go east or west to path around
        assert direction in ("east", "west"), f"Expected east or west to avoid agent, got {direction}"

    def test_complex_maze_path(self):
        """Agent should find path through more complex obstacle layout."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target is south-east, walls form an L-shape blocking direct paths
        # Center (5,5), target at (7, 7)
        # Walls at (6,5), (6,6) blocking south and south-east
        tokens = [
            make_token("tag", 7, 7, 3),  # carbon_extractor at (7, 7)
            make_token("tag", 6, 5, 2),  # wall at (6, 5)
            make_token("tag", 6, 6, 2),  # wall at (6, 6)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is not None, "Should find path"
        direction, _ = result
        # A* should find a path (likely east first, then south)
        assert direction in ("east", "west"), f"Expected to go around walls, got {direction}"

    def test_no_target_returns_none(self):
        """Should return None when no target visible."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # No target tokens
        tokens = [
            make_token("tag", 6, 5, 2),  # wall (not a target)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is None, "Should return None when no target visible"

    def test_surrounded_returns_none(self):
        """Should return None when completely surrounded by obstacles."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target exists but agent is surrounded by walls
        # Center (5,5), walls at all adjacent cells
        tokens = [
            make_token("tag", 8, 5, 3),  # carbon_extractor (unreachable)
            make_token("tag", 4, 5, 2),  # wall north
            make_token("tag", 6, 5, 2),  # wall south
            make_token("tag", 5, 4, 2),  # wall west
            make_token("tag", 5, 6, 2),  # wall east
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is None, "Should return None when surrounded"

    def test_reaches_adjacent_to_target(self):
        """Should stop when adjacent to target (since target cell is blocked)."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Target is just 1 cell south - already adjacent
        # Center (5,5), target at (6,5)
        tokens = [
            make_token("tag", 6, 5, 3),  # carbon_extractor at (6, 5)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))
        assert result is not None, "Should find target"
        direction, _ = result
        # Should return south to walk into the extractor
        assert direction == "south", f"Expected south to reach adjacent target, got {direction}"


class TestPositionTracking:
    """Test position updates based on actual executed actions."""

    def test_position_updates_on_successful_move(self):
        """Position should update when last_action_executed is a move."""
        env_info = MockPolicyEnvInfo()
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Simulate successful move south
        state.nav.last_action_executed = "move_south"
        navigator.update_position(state)

        assert state.row == 101, f"Row should be 101 after move_south, got {state.row}"
        assert state.col == 100, f"Col should stay 100, got {state.col}"

    def test_position_unchanged_on_noop(self):
        """Position should not change when last_action_executed is noop."""
        env_info = MockPolicyEnvInfo()
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Simulate noop (action was blocked)
        state.nav.last_action_executed = "noop"
        navigator.update_position(state)

        assert state.row == 100, f"Row should stay 100 after noop, got {state.row}"
        assert state.col == 100, f"Col should stay 100, got {state.col}"

    def test_position_unchanged_on_none(self):
        """Position should not change when last_action_executed is None."""
        env_info = MockPolicyEnvInfo()
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        state.nav.last_action_executed = None
        navigator.update_position(state)

        assert state.row == 100, f"Row should stay 100, got {state.row}"
        assert state.col == 100, f"Col should stay 100, got {state.col}"

    def test_position_updates_all_directions(self):
        """Position should update correctly for all move directions."""
        env_info = MockPolicyEnvInfo()
        navigator = Navigator(env_info)

        test_cases = [
            ("move_north", -1, 0),
            ("move_south", 1, 0),
            ("move_east", 0, 1),
            ("move_west", 0, -1),
        ]

        for action, expected_dr, expected_dc in test_cases:
            state = AgentState(agent_id=0)
            state.row = 100
            state.col = 100
            state.nav.last_action_executed = action
            navigator.update_position(state)

            expected_row = 100 + expected_dr
            expected_col = 100 + expected_dc
            assert state.row == expected_row, f"{action}: row should be {expected_row}, got {state.row}"
            assert state.col == expected_col, f"{action}: col should be {expected_col}, got {state.col}"

    def test_position_unchanged_on_failed_move(self):
        """Position should not change when move action fails (returns noop)."""
        env_info = MockPolicyEnvInfo()
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Agent tried to move but was blocked - last_action shows noop
        state.nav.last_action_executed = "noop"
        navigator.update_position(state)

        assert state.row == 100, "Position should not change on blocked move"
        assert state.col == 100, "Position should not change on blocked move"


class TestObstacleAvoidance:
    """Test that navigation properly avoids all obstacles."""

    def test_avoids_wall_to_reach_extractor(self):
        """Agent should navigate around wall to reach extractor."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Wall directly between agent and extractor
        tokens = [
            make_token("tag", 7, 5, 3),  # carbon_extractor
            make_token("tag", 6, 5, 2),  # wall blocking
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))

        # Should not try to move south into wall
        if result is not None:
            direction, _ = result
            assert direction != "south", "Should not move into wall"

    def test_avoids_station_as_obstacle(self):
        """Agent should treat stations as obstacles when pathfinding to target."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Miner station between agent and extractor
        tokens = [
            make_token("tag", 7, 5, 3),  # carbon_extractor (target)
            make_token("tag", 6, 5, 4),  # miner_station blocking
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))

        # Should not try to move directly south into station
        if result is not None:
            direction, _ = result
            assert direction in ("east", "west"), f"Should go around station, got {direction}"

    def test_multiple_obstacles_complex_path(self):
        """Agent should find path through multiple obstacles."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)

        # Create a corridor: walls on sides, opening to the east
        # Center (5,5), target at (5, 8)
        tokens = [
            make_token("tag", 5, 8, 3),  # carbon_extractor east
            make_token("tag", 4, 6, 2),  # wall
            make_token("tag", 6, 6, 2),  # wall
            # Opening at (5,6)
        ]
        obs = make_obs(tokens)

        result = tracker.get_direction_to_nearest(state, obs, frozenset({"carbon_extractor"}))

        # Should go east through the opening
        assert result is not None, "Should find path"
        direction, _ = result
        assert direction == "east", f"Expected east through opening, got {direction}"


class TestInternalMapBuilding:
    """Test that Pinky builds and maintains an internal map while navigating."""

    def test_map_initializes_with_unknown_cells(self):
        """Map should start with all cells as UNKNOWN."""
        state = AgentState(agent_id=0)

        # Check that cells are UNKNOWN by default
        assert state.map.occupancy[50][50] == CellType.UNKNOWN.value
        assert state.map.occupancy[0][0] == CellType.UNKNOWN.value
        assert state.map.occupancy[100][100] == CellType.UNKNOWN.value

        # Check explored is False
        assert state.map.explored[50][50] is False

    def test_observed_empty_cells_become_free(self):
        """Cells observed without objects should become FREE."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Empty observation (no objects)
        obs = make_obs([])
        tracker.update(state, obs)

        # All cells in observation window should be FREE
        # Observation window is 11x11 centered on agent
        for dr in range(-5, 6):
            for dc in range(-5, 6):
                r, c = state.row + dr, state.col + dc
                assert state.map.occupancy[r][c] == CellType.FREE.value, f"Cell ({r},{c}) should be FREE"
                assert state.map.explored[r][c] is True, f"Cell ({r},{c}) should be explored"

    def test_observed_walls_become_obstacles(self):
        """Cells with walls should become OBSTACLE."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Wall at observation position (6, 5) = world (101, 100)
        tokens = [make_token("tag", 6, 5, 2)]  # wall south of center
        obs = make_obs(tokens)
        tracker.update(state, obs)

        # Wall cell should be OBSTACLE
        assert state.map.occupancy[101][100] == CellType.OBSTACLE.value
        # Adjacent empty cell should be FREE
        assert state.map.occupancy[100][101] == CellType.FREE.value

    def test_map_persists_when_agent_moves_away(self):
        """Map knowledge should persist when agent moves to new location."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # First observation: wall at (101, 100)
        tokens = [make_token("tag", 6, 5, 2)]  # wall south
        obs = make_obs(tokens)
        tracker.update(state, obs)

        # Verify wall is recorded
        assert state.map.occupancy[101][100] == CellType.OBSTACLE.value

        # Agent moves far north (so wall is outside 11x11 observation window)
        # Observation radius is 5 cells, so move at least 7 cells to ensure wall is out of view
        state.row = 92  # Wall at (101, 100) is now 9 cells south, outside obs window

        # Second observation from new position: wall not in view
        obs2 = make_obs([])
        tracker.update(state, obs2)

        # Wall should STILL be recorded in internal map (outside observation window)
        assert state.map.occupancy[101][100] == CellType.OBSTACLE.value, "Wall knowledge should persist"

    def test_unexplored_cells_remain_unknown(self):
        """Cells outside observation window should remain UNKNOWN."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        obs = make_obs([])
        tracker.update(state, obs)

        # Cells far from agent should still be UNKNOWN
        assert state.map.occupancy[50][50] == CellType.UNKNOWN.value
        assert state.map.explored[50][50] is False
        assert state.map.occupancy[150][150] == CellType.UNKNOWN.value

    def test_wander_and_build_map(self):
        """Agent wanders around a room, building internal map that matches actual layout."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Define actual room: 10x10 room with walls around edges and a pillar in center
        # Room spans (95-105, 95-105) in world coords
        actual_room: dict[tuple[int, int], int] = {}
        for r in range(95, 106):
            for c in range(95, 106):
                # Walls at edges
                if r == 95 or r == 105 or c == 95 or c == 105:
                    actual_room[(r, c)] = CellType.OBSTACLE.value
                # Pillar at center
                elif r == 100 and c == 100:
                    actual_room[(r, c)] = CellType.OBSTACLE.value
                else:
                    actual_room[(r, c)] = CellType.FREE.value

        def get_observation_tokens(agent_row: int, agent_col: int) -> list[ObservationToken]:
            """Generate observation tokens based on actual room layout."""
            tokens = []
            obs_center_r, obs_center_c = 5, 5  # Center of 11x11 observation

            for obs_r in range(11):
                for obs_c in range(11):
                    world_r = agent_row + (obs_r - obs_center_r)
                    world_c = agent_col + (obs_c - obs_center_c)
                    pos = (world_r, world_c)

                    if pos in actual_room and actual_room[pos] == CellType.OBSTACLE.value:
                        # Skip self position
                        if obs_r != obs_center_r or obs_c != obs_center_c:
                            tokens.append(make_token("tag", obs_r, obs_c, 2))  # wall

            return tokens

        # Wander around the room in a pattern
        movements = [
            ("move_north", -1, 0),
            ("move_north", -1, 0),
            ("move_east", 0, 1),
            ("move_east", 0, 1),
            ("move_east", 0, 1),
            ("move_south", 1, 0),
            ("move_south", 1, 0),
            ("move_south", 1, 0),
            ("move_south", 1, 0),
            ("move_west", 0, -1),
            ("move_west", 0, -1),
            ("move_west", 0, -1),
            ("move_west", 0, -1),
            ("move_north", -1, 0),
            ("move_north", -1, 0),
        ]

        # Initial observation
        tokens = get_observation_tokens(state.row, state.col)
        obs = make_obs(tokens)
        tracker.update(state, obs)

        # Execute wandering
        for move_action, dr, dc in movements:
            # Check if move is valid (not into wall)
            next_r, next_c = state.row + dr, state.col + dc
            if (next_r, next_c) in actual_room and actual_room[(next_r, next_c)] == CellType.OBSTACLE.value:
                # Blocked by wall, stay in place
                state.nav.last_action_executed = "noop"
            else:
                state.nav.last_action_executed = move_action
                navigator.update_position(state)

            # Get new observation
            tokens = get_observation_tokens(state.row, state.col)
            obs = make_obs(tokens)
            tracker.update(state, obs)
            state.step += 1

        # Verify built map matches actual room for explored cells
        matches = 0
        mismatches = 0
        for pos, actual_cell in actual_room.items():
            r, c = pos
            if state.map.explored[r][c]:
                if state.map.occupancy[r][c] == actual_cell:
                    matches += 1
                else:
                    mismatches += 1

        # Should have explored most of the room with high accuracy
        assert matches > 0, "Should have explored some cells"
        assert mismatches == 0, f"Map should match actual room, but had {mismatches} mismatches"


class TestMovingAgents:
    """Test handling of moving agents in the environment."""

    def test_agent_occupancy_cleared_each_step(self):
        """Agent occupancy should be cleared and rebuilt each step."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Step 1: Other agent at (101, 100)
        tokens1 = [make_token("tag", 6, 5, 1)]  # agent south
        obs1 = make_obs(tokens1)
        tracker.update(state, obs1)

        assert (101, 100) in state.map.agent_occupancy

        # Step 2: Agent moved to (100, 101)
        tokens2 = [make_token("tag", 5, 6, 1)]  # agent east
        obs2 = make_obs(tokens2)
        tracker.update(state, obs2)

        # Old position should be cleared, new position occupied
        assert (101, 100) not in state.map.agent_occupancy, "Old agent position should be cleared"
        assert (100, 101) in state.map.agent_occupancy, "New agent position should be tracked"

    def test_agent_does_not_mark_obstacles(self):
        """Moving agents should not permanently mark cells as obstacles."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Step 1: Agent at (101, 100)
        tokens1 = [make_token("tag", 6, 5, 1)]  # agent south
        obs1 = make_obs(tokens1)
        tracker.update(state, obs1)

        # Cell should be FREE (agent is temporary), but in agent_occupancy
        assert state.map.occupancy[101][100] == CellType.FREE.value
        assert (101, 100) in state.map.agent_occupancy

        # Step 2: Agent gone
        obs2 = make_obs([])
        tracker.update(state, obs2)

        # Cell should still be FREE and no longer occupied
        assert state.map.occupancy[101][100] == CellType.FREE.value
        assert (101, 100) not in state.map.agent_occupancy

    def test_navigation_avoids_moving_agents(self):
        """Navigator should avoid cells with agents even though they're FREE."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Agent blocking south, target further south
        tokens = [
            make_token("tag", 6, 5, 1),  # agent at (101, 100)
            make_token("tag", 8, 5, 3),  # extractor at (103, 100)
        ]
        obs = make_obs(tokens)
        tracker.update(state, obs)

        # Move toward extractor using internal map
        action = navigator.move_to(state, (103, 100))

        # Should not move directly south into agent
        assert action.name != "move_south", f"Should avoid agent, got {action.name}"


class TestMovingObjects:
    """Test handling of objects that move or change state."""

    def test_removed_obstacle_updates_map(self):
        """If an obstacle is removed, map should update when observed."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Step 1: Wall at (101, 100)
        tokens1 = [make_token("tag", 6, 5, 2)]  # wall south
        obs1 = make_obs(tokens1)
        tracker.update(state, obs1)

        assert state.map.occupancy[101][100] == CellType.OBSTACLE.value

        # Step 2: Wall removed (e.g., destroyed)
        obs2 = make_obs([])  # No wall
        tracker.update(state, obs2)

        # Cell should now be FREE
        assert state.map.occupancy[101][100] == CellType.FREE.value, "Removed wall should update to FREE"

    def test_new_obstacle_updates_map(self):
        """If a new obstacle appears, map should update when observed."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Step 1: No obstacles
        obs1 = make_obs([])
        tracker.update(state, obs1)

        assert state.map.occupancy[101][100] == CellType.FREE.value

        # Step 2: Wall appears at (101, 100)
        tokens2 = [make_token("tag", 6, 5, 2)]  # wall south
        obs2 = make_obs(tokens2)
        tracker.update(state, obs2)

        # Cell should now be OBSTACLE
        assert state.map.occupancy[101][100] == CellType.OBSTACLE.value, "New wall should update to OBSTACLE"


class TestPathfindingWithInternalMap:
    """Test pathfinding behavior using the internal map."""

    def test_pathfinding_uses_remembered_obstacles(self):
        """Pathfinding should use obstacles from internal map, not just current observation."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Step 1: See wall south, then move east
        tokens1 = [make_token("tag", 6, 5, 2)]  # wall at (101, 100)
        obs1 = make_obs(tokens1)
        tracker.update(state, obs1)

        # Move east
        state.nav.last_action_executed = "move_east"
        navigator.update_position(state)
        state.col = 101

        # Step 2: Wall no longer in observation (agent moved), but target is south of wall
        obs2 = make_obs([])
        tracker.update(state, obs2)

        # Try to reach position south of the remembered wall
        target = (102, 100)  # South of where wall was

        # Path should avoid the remembered wall
        action = navigator.move_to(state, target)

        # If we moved west, we'd hit the wall we remember. Should go around.
        # Valid moves would be south or continue to navigate around
        assert action.name in ("move_south", "move_west", "noop"), (
            f"Should navigate around remembered wall, got {action.name}"
        )

    def test_pathfinding_through_unknown_when_no_known_path(self):
        """Should allow pathfinding through unknown cells when no known path exists."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Only observe immediate area, rest is UNKNOWN
        obs = make_obs([])
        tracker.update(state, obs)

        # Target is far away in unknown territory
        target = (150, 150)

        # Should be able to pathfind toward target through unknown cells
        action = navigator.move_to(state, target)

        # Should move toward target (south-east direction)
        assert action.name in ("move_south", "move_east"), f"Should move toward unknown target, got {action.name}"

    def test_prefers_known_path_over_unknown(self):
        """Should prefer paths through known FREE cells over UNKNOWN cells."""
        env_info = MockPolicyEnvInfo()
        tracker = MapTracker(env_info)
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Create scenario: target is reachable via known path or shorter unknown path
        # Agent at (100, 100), target at (100, 105)
        # Known corridor going east exists

        # First, explore eastward path
        for _ in range(6):
            obs = make_obs([])
            tracker.update(state, obs)
            state.col += 1
            state.row = 100  # Stay on same row

        # Reset position
        state.row = 100
        state.col = 100

        # Now mark some cells as obstacles to force using the explored corridor
        # (Create a wall blocking direct path)
        state.map.occupancy[100][101] = CellType.OBSTACLE.value

        # Target just beyond the wall
        target = (100, 102)

        # Since direct path is blocked, should find alternative through known cells
        action = navigator.move_to(state, target)

        # Should try to go around, not give up
        assert action.name != "noop", "Should find path around obstacle"


class TestExplorationPrioritizesUnknown:
    """Test that exploration prioritizes unknown territory."""

    def test_explore_prefers_unknown_direction(self):
        """Exploration should prefer moving toward unknown cells."""
        env_info = MockPolicyEnvInfo()
        MapTracker(env_info)
        navigator = Navigator(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Explore west side (mark as FREE)
        for c in range(95, 101):
            for r in range(95, 106):
                state.map.occupancy[r][c] = CellType.FREE.value
                state.map.explored[r][c] = True

        # East side is still UNKNOWN
        assert state.map.occupancy[100][101] == CellType.UNKNOWN.value

        # Clear exploration state
        state.nav.exploration_direction = None

        # Explore should prefer east (toward unknown)
        action = navigator.explore(state)

        # Should prefer east since that's where unknown territory is
        # (Note: exact behavior depends on implementation, but should favor unknown)
        assert action.name in ("move_east", "move_north", "move_south"), (
            f"Should move toward unknown, got {action.name}"
        )


class TestObjectNamePriority:
    """Test that object names prefer type: tags over collective: tags.

    Regression test for PR comment: When a cell has both collective:* and type:* tags,
    _get_object_name should return the type name (e.g., "charger") not the collective
    name (e.g., "collective:cogs"), so that stations/junctions/extractors are properly
    recorded and roles can find gear, depots, and targets.
    """

    def test_type_tag_preferred_over_collective_tag(self):
        """type: tags should be preferred over collective: tags for object names."""
        env_info = MockPolicyEnvInfo()
        # Add collective and type tags
        env_info.tag_id_to_name = {
            1: "type:agent",
            2: "type:wall",
            3: "type:carbon_extractor",
            4: "type:miner_station",
            5: "collective:cogs",  # Collective tag
            6: "type:charger",  # Type tag
        }
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Cell with both collective:cogs (tag 5) and type:charger (tag 6)
        # The type: tag should win
        tokens = [
            make_token("tag", 6, 5, 5),  # collective:cogs at (101, 100)
            make_token("tag", 6, 5, 6),  # type:charger at same position
        ]
        obs = make_obs(tokens)
        tracker.update(state, obs)

        # Check that the structure was found as "charger", not "collective:cogs"
        assert (101, 100) in state.map.structures, "Should record structure at (101, 100)"
        struct = state.map.structures[(101, 100)]
        assert "charger" in struct.name.lower(), (
            f"Expected charger in name, got '{struct.name}'. type: tags should be preferred over collective: tags."
        )

    def test_collective_tag_only_when_no_type_tag(self):
        """collective: tags should only be used when no type: tag exists."""
        env_info = MockPolicyEnvInfo()
        env_info.tag_id_to_name = {
            1: "type:agent",
            2: "type:wall",
            5: "collective:cogs",
            7: "some_other_tag",  # Non-collective, non-type tag
        }
        tracker = MapTracker(env_info)
        state = AgentState(agent_id=0)
        state.row = 100
        state.col = 100

        # Get object name via internal method
        features: dict = {"tags": [5, 7]}
        obj_name = tracker._get_object_name(features)

        # Should prefer "some_other_tag" over "collective:cogs"
        assert obj_name == "some_other_tag", (
            f"Expected 'some_other_tag', got '{obj_name}'. "
            "Non-collective tags should be preferred over collective: tags."
        )

    def test_type_tag_strips_prefix(self):
        """type: prefix should be stripped from the returned name."""
        env_info = MockPolicyEnvInfo()
        env_info.tag_id_to_name = {
            1: "type:junction",
        }
        tracker = MapTracker(env_info)

        features: dict = {"tags": [1]}
        obj_name = tracker._get_object_name(features)

        assert obj_name == "junction", f"Expected 'junction' (prefix stripped), got '{obj_name}'"
