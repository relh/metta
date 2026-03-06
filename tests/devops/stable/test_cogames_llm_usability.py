from __future__ import annotations

import pytest
from anthropic import AnthropicBedrock

from devops.stable.function_checks import cogames_llm_usability as mod
from devops.stable.function_checks._helpers.llm_eval_harness import AgentTurn, Transcript
from devops.stable.function_checks._helpers.llm_eval_judge import Judgment
from devops.stable.stable_check_context import StableCheckContext


def _passing_transcript(task: str = "test") -> Transcript:
    t = Transcript(task=task)
    t.completed = True
    t.turns = [AgentTurn(assistant_text="TASK_COMPLETE: Done.")]
    return t


def _passing_judgment() -> Judgment:
    return Judgment(
        discovery=4,
        interpretation=4,
        completeness=4,
        efficiency=4,
        cli_confusion_notes="None observed.",
        passed=True,
    )


def _failing_judgment() -> Judgment:
    return Judgment(
        discovery=2,
        interpretation=2,
        completeness=1,
        efficiency=2,
        cli_confusion_notes="Could not find leaderboard.",
        passed=False,
    )


def test_check_functions_are_registered() -> None:
    assert hasattr(mod, "llm_eval_spectator_leaderboard")
    assert hasattr(mod, "llm_eval_tournament_progress")
    assert hasattr(mod, "llm_eval_important_tournaments")
    assert hasattr(mod, "llm_eval_debug_submission_error")
    assert hasattr(mod, "llm_eval_debug_submission_performance")
    assert hasattr(mod, "llm_eval_tournament_game_rules")


def test_spectator_leaderboard_passes_on_good_judgment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod,
        "_run_scenario",
        lambda *, scenario, **_kw: (_passing_transcript(scenario.task), _passing_judgment()),
    )
    mod.llm_eval_spectator_leaderboard(StableCheckContext(job_name="test-job", inputs={}))


def test_spectator_leaderboard_fails_on_bad_judgment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mod,
        "_run_scenario",
        lambda *, scenario, **_kw: (_passing_transcript(scenario.task), _failing_judgment()),
    )
    with pytest.raises(AssertionError, match="LLM eval failed"):
        mod.llm_eval_spectator_leaderboard(StableCheckContext(job_name="test-job", inputs={}))


def test_get_anthropic_client_returns_bedrock() -> None:
    client = mod._get_anthropic_client()
    assert isinstance(client, AnthropicBedrock)
