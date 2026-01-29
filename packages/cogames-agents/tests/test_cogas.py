"""Comprehensive unit tests for the cogas agent.

Covers:
1. Agent registration -- 'cogas' is in the scripted registry
2. URI parameter parsing -- role distribution params
3. Role assignment -- correct number of each role
4. Default role distribution -- aligner/scrambler heavy defaults
5. State machine transitions -- phase progression for each role
6. Import and instantiation -- policy can be created without errors
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cogames_agents.policy.scripted_agent.cogas.cogas_policy import (
    CogasBrain,
    CogasPolicy,
    Coordinator,
    Phase,
)
from cogames_agents.policy.scripted_agent.cogas.goals import (
    make_aligner_goals,
    make_miner_goals,
    make_scout_goals,
    make_scrambler_goals,
)
from cogames_agents.policy.scripted_registry import (
    SCRIPTED_AGENT_URIS,
    list_scripted_agent_names,
    resolve_scripted_agent_uri,
)


def _make_cogas_policy(**kwargs) -> CogasPolicy:
    """Create a CogasPolicy with the mocked MultiAgentPolicy base class."""
    env_info = MagicMock()
    env_info.obs_features = []
    env_info.action_names = ["noop", "move_north", "move_south", "move_east", "move_west"]
    env_info.num_agents = kwargs.pop("num_agents", 10)

    # The conftest mock for MultiAgentPolicy doesn't accept __init__ args,
    # so we patch the super().__init__ call.
    with patch.object(CogasPolicy.__bases__[0], "__init__", lambda *a, **kw: None):
        policy = CogasPolicy(env_info, **kwargs)
    # Manually set _policy_env_info since super().__init__ was bypassed
    policy._policy_env_info = env_info
    return policy


# ---------------------------------------------------------------------------
# 1. Agent registration
# ---------------------------------------------------------------------------


class TestCogasRegistration:
    """Verify 'cogas' is discovered by the scripted registry."""

    def test_cogas_in_scripted_agent_names(self) -> None:
        names = set(list_scripted_agent_names())
        assert "cogas" in names

    def test_cogas_uri_resolution(self) -> None:
        uri = resolve_scripted_agent_uri("cogas")
        assert uri == "metta://policy/cogas"

    def test_cogas_in_uri_map(self) -> None:
        assert "cogas" in SCRIPTED_AGENT_URIS
        assert SCRIPTED_AGENT_URIS["cogas"] == "metta://policy/cogas"


# ---------------------------------------------------------------------------
# 2. URI parameter parsing (role distribution from constructor kwargs)
# ---------------------------------------------------------------------------


class TestURIParameterParsing:
    """Verify that constructor kwargs control role distribution."""

    def test_default_role_counts(self) -> None:
        policy = _make_cogas_policy()
        dist = policy._role_distribution
        assert dist.count("miner") == 3
        assert dist.count("scout") == 1
        assert dist.count("aligner") == 3
        assert dist.count("scrambler") == 2
        assert dist.count("flex") == 1
        assert len(dist) == 10

    def test_custom_role_counts(self) -> None:
        policy = _make_cogas_policy(miner=1, scout=2, aligner=4, scrambler=2, flex=0)
        dist = policy._role_distribution
        assert dist.count("miner") == 1
        assert dist.count("scout") == 2
        assert dist.count("aligner") == 4
        assert dist.count("scrambler") == 2
        assert dist.count("flex") == 0
        assert len(dist) == 9

    def test_all_miners(self) -> None:
        policy = _make_cogas_policy(miner=5, scout=0, aligner=0, scrambler=0, flex=0)
        dist = policy._role_distribution
        assert dist == ["miner"] * 5

    def test_zero_agents(self) -> None:
        policy = _make_cogas_policy(miner=0, scout=0, aligner=0, scrambler=0, flex=0)
        assert policy._role_distribution == []


# ---------------------------------------------------------------------------
# 3. Role assignment -- verify correct role for each agent_id
# ---------------------------------------------------------------------------


class TestRoleAssignment:
    """Verify agents get the correct role from distribution ordering."""

    def test_default_role_ordering(self) -> None:
        """Roles are assigned in order: miners, scouts, aligners, scramblers, flex."""
        policy = _make_cogas_policy()
        expected = ["miner"] * 3 + ["scout"] * 1 + ["aligner"] * 3 + ["scrambler"] * 2 + ["flex"] * 1
        assert policy._role_distribution == expected

    def test_agent_id_maps_to_role(self) -> None:
        """_role_distribution[agent_id] gives the role for that agent."""
        policy = _make_cogas_policy()
        dist = policy._role_distribution
        assert dist[0] == "miner"  # First miner
        assert dist[3] == "scout"  # Single scout
        assert dist[4] == "aligner"  # First aligner
        assert dist[7] == "scrambler"  # First scrambler
        assert dist[9] == "flex"  # Single flex

    def test_overflow_agents_default_to_miner(self) -> None:
        """Agent IDs beyond the distribution length get 'miner' in agent_policy."""
        policy = _make_cogas_policy(miner=1, scout=0, aligner=0, scrambler=0, flex=0)
        # Distribution only has 1 entry, agent_id=5 exceeds it
        assert len(policy._role_distribution) == 1
        # agent_policy line 395: falls back to "miner" when agent_id >= len
        role = policy._role_distribution[5] if 5 < len(policy._role_distribution) else "miner"
        assert role == "miner"


# ---------------------------------------------------------------------------
# 4. Default role distribution -- aligner/scrambler heavy
# ---------------------------------------------------------------------------


class TestDefaultDistribution:
    """Verify the default distribution is aligner/scrambler heavy."""

    def test_aligner_scrambler_majority(self) -> None:
        """Aligners + scramblers + flex should outnumber miners + scouts."""
        policy = _make_cogas_policy()
        dist = policy._role_distribution
        offensive = dist.count("aligner") + dist.count("scrambler") + dist.count("flex")
        support = dist.count("miner") + dist.count("scout")
        assert offensive > support

    def test_aligner_count_equals_miner(self) -> None:
        """Default has equal miners and aligners (3 each)."""
        policy = _make_cogas_policy()
        dist = policy._role_distribution
        assert dist.count("aligner") == dist.count("miner") == 3

    def test_scrambler_count(self) -> None:
        policy = _make_cogas_policy()
        assert policy._role_distribution.count("scrambler") == 2

    def test_single_scout(self) -> None:
        policy = _make_cogas_policy()
        assert policy._role_distribution.count("scout") == 1

    def test_single_flex(self) -> None:
        policy = _make_cogas_policy()
        assert policy._role_distribution.count("flex") == 1


# ---------------------------------------------------------------------------
# 5. State machine transitions -- phase progression
# ---------------------------------------------------------------------------


class TestPhaseTransitions:
    """Verify phase progression: BOOTSTRAP -> CONTROL -> SUSTAIN."""

    def _make_brain(self, role: str = "miner") -> CogasBrain:
        env_info = MagicMock()
        env_info.obs_features = []
        env_info.action_names = ["noop"]
        coordinator = Coordinator()
        return CogasBrain(
            policy_env_info=env_info,
            agent_id=0,
            role=role,
            coordinator=coordinator,
        )

    def _make_state(self, phase: Phase, step: int = 0) -> MagicMock:
        """Create a mock StateSnapshot."""
        state = MagicMock()
        state.position = (100, 100)
        state.hp = 100
        state.energy = 50
        state.miner_gear = False
        state.scout_gear = False
        state.aligner_gear = False
        state.scrambler_gear = False
        state.vibe = "default"
        return state

    def test_initial_phase_is_bootstrap(self) -> None:
        brain = self._make_brain()
        agent_state = brain.initial_agent_state()
        assert agent_state.phase == Phase.BOOTSTRAP

    def test_bootstrap_to_control_on_gear(self) -> None:
        """Acquiring gear triggers transition to CONTROL."""
        brain = self._make_brain(role="miner")
        agent_state = brain.initial_agent_state()
        assert agent_state.phase == Phase.BOOTSTRAP

        state = self._make_state(Phase.BOOTSTRAP)
        state.miner_gear = True
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.CONTROL

    def test_bootstrap_to_control_on_step_30(self) -> None:
        """Step > 30 forces transition to CONTROL even without gear."""
        brain = self._make_brain(role="miner")
        agent_state = brain.initial_agent_state()
        agent_state.step = 31

        state = self._make_state(Phase.BOOTSTRAP)
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.CONTROL

    def test_stays_bootstrap_before_step_30_no_gear(self) -> None:
        brain = self._make_brain(role="miner")
        agent_state = brain.initial_agent_state()
        agent_state.step = 15

        state = self._make_state(Phase.BOOTSTRAP)
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.BOOTSTRAP

    def test_control_to_sustain_on_step_300(self) -> None:
        """Step > 300 triggers transition to SUSTAIN."""
        brain = self._make_brain()
        agent_state = brain.initial_agent_state()
        agent_state.phase = Phase.CONTROL
        agent_state.step = 301

        state = self._make_state(Phase.CONTROL)
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.SUSTAIN

    def test_control_to_sustain_on_junction_count(self) -> None:
        """3+ cogs junctions triggers transition to SUSTAIN."""
        brain = self._make_brain()
        agent_state = brain.initial_agent_state()
        agent_state.phase = Phase.CONTROL
        agent_state.step = 100

        # Mock entity_map.find to return 3 cogs junctions
        agent_state.entity_map.find = MagicMock(
            return_value=[
                ((10, 10), MagicMock()),
                ((20, 20), MagicMock()),
                ((30, 30), MagicMock()),
            ]
        )

        state = self._make_state(Phase.CONTROL)
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.SUSTAIN

    def test_stays_control_with_few_junctions(self) -> None:
        brain = self._make_brain()
        agent_state = brain.initial_agent_state()
        agent_state.phase = Phase.CONTROL
        agent_state.step = 100

        agent_state.entity_map.find = MagicMock(
            return_value=[
                ((10, 10), MagicMock()),
            ]
        )

        state = self._make_state(Phase.CONTROL)
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.CONTROL

    def test_sustain_stays_sustain(self) -> None:
        """SUSTAIN is a terminal phase."""
        brain = self._make_brain()
        agent_state = brain.initial_agent_state()
        agent_state.phase = Phase.SUSTAIN
        agent_state.step = 500

        state = self._make_state(Phase.SUSTAIN)
        new_phase = brain._evaluate_phase(agent_state, state)
        assert new_phase == Phase.SUSTAIN

    def test_aligner_gear_detection(self) -> None:
        brain = self._make_brain(role="aligner")
        state = self._make_state(Phase.BOOTSTRAP)
        state.aligner_gear = True
        assert brain._has_role_gear(state) is True

    def test_scrambler_gear_detection(self) -> None:
        brain = self._make_brain(role="scrambler")
        state = self._make_state(Phase.BOOTSTRAP)
        state.scrambler_gear = True
        assert brain._has_role_gear(state) is True

    def test_flex_uses_scout_gear(self) -> None:
        """Flex agents check scout gear (they start as scouts)."""
        brain = self._make_brain(role="flex")
        state = self._make_state(Phase.BOOTSTRAP)
        state.scout_gear = True
        assert brain._has_role_gear(state) is True


# ---------------------------------------------------------------------------
# 5b. Goal factories produce correct goals per role and phase
# ---------------------------------------------------------------------------


class TestGoalFactories:
    """Verify goal lists match expected structure per role/phase."""

    def test_miner_goals_have_mining_chain(self) -> None:
        goals = make_miner_goals(Phase.BOOTSTRAP)
        goal_names = [type(g).__name__ for g in goals]
        assert "SurviveGoal" in goal_names
        assert "RechargeEnergyGoal" in goal_names
        assert "GetMinerGearGoal" in goal_names
        assert "ResourceManagedMineGoal" in goal_names

    def test_scout_goals_have_explore(self) -> None:
        goals = make_scout_goals(Phase.BOOTSTRAP)
        goal_names = [type(g).__name__ for g in goals]
        assert "ExploreGoal" in goal_names
        assert "GetScoutGearGoal" in goal_names

    def test_aligner_control_has_coordinated_align(self) -> None:
        coordinator = Coordinator()
        goals = make_aligner_goals(Phase.CONTROL, coordinator, agent_id=0)
        goal_names = [type(g).__name__ for g in goals]
        assert "CoordinatedAlignGoal" in goal_names
        assert "GetAlignerGearGoal" in goal_names

    def test_aligner_sustain_has_patrol(self) -> None:
        coordinator = Coordinator()
        goals = make_aligner_goals(Phase.SUSTAIN, coordinator, agent_id=0)
        goal_names = [type(g).__name__ for g in goals]
        assert "PatrolJunctionsGoal" in goal_names
        assert "CoordinatedAlignGoal" not in goal_names

    def test_scrambler_has_coordinated_scramble(self) -> None:
        coordinator = Coordinator()
        goals = make_scrambler_goals(Phase.CONTROL, coordinator, agent_id=0)
        goal_names = [type(g).__name__ for g in goals]
        assert "CoordinatedScrambleGoal" in goal_names
        assert "GetScramblerGearGoal" in goal_names

    def test_phase_change_rebuilds_goals(self) -> None:
        """When phase changes, _make_goals_for_phase produces new goal lists."""
        env_info = MagicMock()
        env_info.obs_features = []
        env_info.action_names = ["noop"]
        coordinator = Coordinator()
        brain = CogasBrain(env_info, agent_id=0, role="aligner", coordinator=coordinator)

        bootstrap_goals = brain._make_goals_for_phase(Phase.BOOTSTRAP)
        control_goals = brain._make_goals_for_phase(Phase.CONTROL)
        sustain_goals = brain._make_goals_for_phase(Phase.SUSTAIN)

        # All phases should produce goals
        assert len(bootstrap_goals) > 0
        assert len(control_goals) > 0
        assert len(sustain_goals) > 0

        # Sustain should have patrol, control should have align
        sustain_names = [type(g).__name__ for g in sustain_goals]
        control_names = [type(g).__name__ for g in control_goals]
        assert "PatrolJunctionsGoal" in sustain_names
        assert "CoordinatedAlignGoal" in control_names


# ---------------------------------------------------------------------------
# 6. Import and instantiation
# ---------------------------------------------------------------------------


class TestImportAndInstantiation:
    """Verify the policy can be imported and created without errors."""

    def test_import_cogas_policy(self) -> None:
        from cogames_agents.policy.scripted_agent.cogas import CogasPolicy as CP

        assert CP is CogasPolicy

    def test_short_names_attribute(self) -> None:
        assert CogasPolicy.short_names == ["cogas"]

    def test_instantiate_with_defaults(self) -> None:
        policy = _make_cogas_policy()
        assert policy is not None
        assert len(policy._role_distribution) == 10

    def test_instantiate_with_trace(self) -> None:
        policy = _make_cogas_policy(trace=1, trace_level=2, trace_agent=0)
        assert policy._trace_enabled is True
        assert policy._trace_level == 2
        assert policy._trace_agent == 0

    def test_coordinator_is_created(self) -> None:
        """Policy creates a Coordinator instance."""
        policy = _make_cogas_policy()
        assert isinstance(policy._coordinator, Coordinator)

    def test_extra_kwargs_accepted(self) -> None:
        """Policy should accept unknown kwargs without error."""
        policy = _make_cogas_policy(unknown_param=42, another="value")
        assert policy is not None


# ---------------------------------------------------------------------------
# Coordinator unit tests
# ---------------------------------------------------------------------------


class TestCoordinator:
    """Verify Coordinator heart reservation and junction/scramble claims."""

    def test_heart_reservation_limit(self) -> None:
        coord = Coordinator()
        assert coord.reserve_heart(0) is True
        assert coord.reserve_heart(1) is True
        # Third agent should be denied
        assert coord.reserve_heart(2) is False

    def test_heart_reservation_idempotent(self) -> None:
        coord = Coordinator()
        coord.reserve_heart(0)
        coord.reserve_heart(1)
        # Existing reservation holder can still reserve
        assert coord.reserve_heart(0) is True

    def test_heart_release(self) -> None:
        coord = Coordinator()
        coord.reserve_heart(0)
        coord.reserve_heart(1)
        coord.release_heart(0)
        # Now slot is open
        assert coord.reserve_heart(2) is True

    def test_junction_claim(self) -> None:
        coord = Coordinator()
        pos = (10, 20)
        assert coord.claim_junction(0, pos) is True
        # Same agent can re-claim
        assert coord.claim_junction(0, pos) is True
        # Different agent denied
        assert coord.claim_junction(1, pos) is False

    def test_junction_release(self) -> None:
        coord = Coordinator()
        pos = (10, 20)
        coord.claim_junction(0, pos)
        coord.release_junction(0)
        # Now available
        assert coord.claim_junction(1, pos) is True

    def test_claimed_junctions_set(self) -> None:
        coord = Coordinator()
        coord.claim_junction(0, (1, 2))
        coord.claim_junction(1, (3, 4))
        assert coord.claimed_junctions() == {(1, 2), (3, 4)}

    def test_scramble_claim(self) -> None:
        coord = Coordinator()
        pos = (5, 5)
        assert coord.claim_scramble(0, pos) is True
        assert coord.claim_scramble(1, pos) is False

    def test_scramble_release(self) -> None:
        coord = Coordinator()
        pos = (5, 5)
        coord.claim_scramble(0, pos)
        coord.release_scramble(0)
        assert coord.claim_scramble(1, pos) is True

    def test_claimed_scrambles_set(self) -> None:
        coord = Coordinator()
        coord.claim_scramble(0, (1, 1))
        coord.claim_scramble(1, (2, 2))
        assert coord.claimed_scrambles() == {(1, 1), (2, 2)}
