from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from devops.stable.function_checks._helpers import llm_eval_harness as harness


def _text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_use_id: str, command: str) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=tool_use_id, name="bash", input={"command": command})


def _make_response(
    blocks: list[SimpleNamespace],
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 20,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def _make_client(responses: list[SimpleNamespace]) -> MagicMock:
    client = MagicMock()
    client.messages.create = MagicMock(side_effect=responses)
    return client


def test_agent_completes_in_one_turn() -> None:
    text = "AlphaBot leads with 1500 points.\nTASK_COMPLETE: Leaderboard shows current rankings"
    response = _make_response([_text_block(text)])
    client = _make_client([response])

    transcript = harness.run_agent(
        client=client,
        task="show me the current leaderboard",
        bin_dir=Path("/fake/bin"),
        server_url="http://localhost:8080",
    )

    assert transcript.completed is True
    assert transcript.failed is False
    assert transcript.gave_up is False
    assert transcript.commands_run == []
    assert len(transcript.turns) == 1
    assert transcript.total_input_tokens == 10
    assert transcript.total_output_tokens == 20
    assert "Leaderboard shows current rankings" in transcript.summary


@patch.object(harness, "_execute_command")
def test_agent_runs_command_then_completes(mock_exec: MagicMock) -> None:
    mock_exec.return_value = ("1. AlphaBot  1500\n2. BetaBot  1200\n", "", 0)

    tool_response = _make_response(
        [_tool_use_block("tool_1", "cogames leaderboard --server http://localhost")],
        stop_reason="tool_use",
    )
    complete_response = _make_response(
        [_text_block("Found the rankings.\nTASK_COMPLETE: Leaderboard retrieved successfully")],
    )
    client = _make_client([tool_response, complete_response])

    transcript = harness.run_agent(
        client=client,
        task="show me the current leaderboard",
        bin_dir=Path("/fake/bin"),
        server_url="http://localhost:8080",
    )

    assert transcript.completed is True
    assert transcript.failed is False
    assert transcript.commands_run == ["cogames leaderboard --server http://localhost"]
    assert len(transcript.turns) == 2
    assert transcript.total_input_tokens == 20
    assert transcript.total_output_tokens == 40
    mock_exec.assert_called_once()


@patch.object(harness, "_execute_command")
def test_agent_gives_up_at_max_turns(mock_exec: MagicMock) -> None:
    mock_exec.return_value = ("output\n", "", 0)

    tool_response = _make_response(
        [_tool_use_block("tool_1", "cogames leaderboard --server http://localhost")],
        stop_reason="tool_use",
    )
    client = _make_client([tool_response, tool_response, tool_response])

    transcript = harness.run_agent(
        client=client,
        task="show me the current leaderboard",
        bin_dir=Path("/fake/bin"),
        server_url="http://localhost:8080",
        max_turns=3,
    )

    assert transcript.completed is False
    assert transcript.failed is False
    assert transcript.gave_up is True
    assert len(transcript.commands_run) == 3


def test_agent_detects_task_failed() -> None:
    text = "Cannot connect to tournament server.\nTASK_FAILED: tournament server unreachable"
    response = _make_response([_text_block(text)])
    client = _make_client([response])

    transcript = harness.run_agent(
        client=client,
        task="show me the current leaderboard",
        bin_dir=Path("/fake/bin"),
        server_url="http://localhost:8080",
    )

    assert transcript.completed is False
    assert transcript.failed is True
    assert transcript.gave_up is False
    assert "tournament server unreachable" in transcript.summary


def test_agent_gives_up_on_end_turn_without_tool_use() -> None:
    response = _make_response([_text_block("I'm not sure what to do next.")])
    client = _make_client([response])

    transcript = harness.run_agent(
        client=client,
        task="show me the current leaderboard",
        bin_dir=Path("/fake/bin"),
        server_url="http://localhost:8080",
    )

    assert transcript.completed is False
    assert transcript.failed is False
    assert transcript.gave_up is True


def test_transcript_format_for_judge() -> None:
    response = _make_response([_text_block("Found 3 active tournaments.\nTASK_COMPLETE: listed active tournaments")])
    client = _make_client([response])

    transcript = harness.run_agent(
        client=client,
        task="show me the current leaderboard",
        bin_dir=Path("/fake/bin"),
        server_url="http://localhost:8080",
    )

    formatted = transcript.format_for_judge()
    assert "show me the current leaderboard" in formatted
    assert "TASK_COMPLETE" in formatted


def test_token_counting_across_multiple_turns() -> None:
    with patch.object(harness, "_execute_command", return_value=("ok\n", "", 0)):
        tool_response = _make_response(
            [_tool_use_block("t1", "cmd1")],
            stop_reason="tool_use",
            input_tokens=100,
            output_tokens=50,
        )
        complete_response = _make_response(
            [_text_block("TASK_COMPLETE: done")],
            input_tokens=200,
            output_tokens=30,
        )
        client = _make_client([tool_response, complete_response])

        transcript = harness.run_agent(
            client=client,
            task="test",
            bin_dir=Path("/fake/bin"),
            server_url="http://localhost:8080",
        )

        assert transcript.total_input_tokens == 300
        assert transcript.total_output_tokens == 80


def test_execute_command_preserves_env_vars() -> None:
    """Regression: _execute_command was replacing the entire env with only PATH,
    stripping HOME, USER, TMPDIR, etc. that CLI tools depend on."""
    stdout, _, exit_code = harness._execute_command("echo $HOME", bin_dir=Path("/fake/bin"), timeout_s=5)
    assert exit_code == 0
    assert stdout.strip() == os.environ["HOME"]
