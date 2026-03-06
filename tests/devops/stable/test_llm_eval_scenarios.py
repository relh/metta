from __future__ import annotations

from devops.stable.function_checks._helpers.llm_eval_scenarios import SCENARIOS, LLMEvalScenario

READ_ONLY_NAMES = {"spectator_leaderboard", "tournament_progress", "important_tournaments", "tournament_game_rules"}
AUTH_REQUIRED_NAMES = {"debug_submission_error", "debug_submission_performance"}
ALL_NAMES = READ_ONLY_NAMES | AUTH_REQUIRED_NAMES


def test_scenarios_are_defined() -> None:
    assert len(SCENARIOS) >= len(ALL_NAMES)


def test_scenario_fields_are_populated() -> None:
    for scenario in SCENARIOS.values():
        assert isinstance(scenario, LLMEvalScenario)
        assert scenario.name
        assert scenario.task
        assert scenario.max_agent_turns > 0
        assert scenario.timeout_s > 0


def test_all_scenarios_exist() -> None:
    assert ALL_NAMES <= set(SCENARIOS.keys())


def test_read_only_scenarios_dont_require_auth() -> None:
    for name in READ_ONLY_NAMES:
        assert SCENARIOS[name].requires_auth is False


def test_auth_scenarios_require_auth() -> None:
    for name in AUTH_REQUIRED_NAMES:
        assert SCENARIOS[name].requires_auth is True
