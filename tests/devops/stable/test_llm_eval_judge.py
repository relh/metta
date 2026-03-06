from __future__ import annotations

import json
from unittest.mock import MagicMock

from devops.stable.function_checks._helpers.llm_eval_harness import AgentTurn, Transcript
from devops.stable.function_checks._helpers.llm_eval_judge import Judgment, judge_transcript


def _make_judge_response(judgment_dict: dict) -> MagicMock:
    text_block = MagicMock()
    text_block.text = json.dumps(judgment_dict)
    response = MagicMock()
    response.content = [text_block]
    return response


def _make_transcript(task: str, completed: bool) -> Transcript:
    return Transcript(
        task=task,
        turns=[
            AgentTurn(
                assistant_text="Let me check the leaderboard.",
                command="cogames leaderboard --server http://localhost",
                stdout="1. AlphaBot  1500\n2. BetaBot  1200",
                exit_code=0,
            ),
            AgentTurn(assistant_text="TASK_COMPLETE: Found the leaderboard.", command=None),
        ],
        completed=completed,
    )


def test_judge_returns_structured_judgment() -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_judge_response(
        {
            "discovery": 5,
            "interpretation": 4,
            "completeness": 5,
            "efficiency": 4,
            "cli_confusion_notes": "",
            "passed": True,
        }
    )
    transcript = _make_transcript("show me the current leaderboard rankings", completed=True)
    result = judge_transcript(client=client, transcript=transcript, scenario_name="spectator_leaderboard")

    assert isinstance(result, Judgment)
    assert result.discovery == 5
    assert result.interpretation == 4
    assert result.completeness == 5
    assert result.efficiency == 4
    assert result.cli_confusion_notes == ""
    assert result.passed is True
    assert result.meets_threshold(min_score=4)


def test_judge_handles_low_scores() -> None:
    client = MagicMock()
    client.messages.create.return_value = _make_judge_response(
        {
            "discovery": 2,
            "interpretation": 1,
            "completeness": 2,
            "efficiency": 1,
            "cli_confusion_notes": "Agent tried `cogames submit` without a policy path.",
            "passed": False,
        }
    )
    transcript = _make_transcript("check tournament progress", completed=False)
    result = judge_transcript(client=client, transcript=transcript, scenario_name="tournament_progress")

    assert result.discovery == 2
    assert result.interpretation == 1
    assert result.passed is False
    assert not result.meets_threshold(min_score=3)


def test_judge_meets_threshold_check() -> None:
    at_boundary = Judgment(
        discovery=3,
        interpretation=3,
        completeness=3,
        efficiency=3,
        cli_confusion_notes="",
        passed=True,
    )
    assert at_boundary.meets_threshold(min_score=3)
    assert not at_boundary.meets_threshold(min_score=4)

    one_below = Judgment(
        discovery=3,
        interpretation=3,
        completeness=2,
        efficiency=3,
        cli_confusion_notes="",
        passed=True,
    )
    assert not one_below.meets_threshold(min_score=3)
