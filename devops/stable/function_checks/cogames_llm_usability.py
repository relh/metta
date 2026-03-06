from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from anthropic import AnthropicBedrock

from devops.runners.metta_constants import OBSERVATORY_AUTH_SERVER_URL, PROD_STATS_SERVER_URI
from devops.stable.function_checks._helpers.llm_eval_harness import LLM_EVAL_TRANSCRIPT_DIR, Transcript, run_agent
from devops.stable.function_checks._helpers.llm_eval_judge import Judgment, judge_transcript
from devops.stable.function_checks._helpers.llm_eval_scenarios import SCENARIOS, LLMEvalScenario
from devops.stable.stable_check_context import StableCheckContext
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_function_check_registry import stable_function_check

logger = logging.getLogger(__name__)

MIN_SCORE = 3
_LLM_EVAL_VENV_DIR = Path("devops/stable/state/llm_eval_venv")
_LLM_EVAL_VENV_BIN_DIR = _LLM_EVAL_VENV_DIR / "bin"


def _get_anthropic_client() -> AnthropicBedrock:
    aws_region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    return AnthropicBedrock(aws_region=aws_region)


def _save_transcript(scenario_name: str, transcript: Transcript, judgment: Judgment) -> None:
    LLM_EVAL_TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = LLM_EVAL_TRANSCRIPT_DIR / f"{scenario_name}.md"
    parts = [
        f"# {scenario_name}",
        "",
        f"**Passed**: {judgment.passed}  ",
        f"**Scores**: discovery={judgment.discovery} interpretation={judgment.interpretation} "
        f"completeness={judgment.completeness} efficiency={judgment.efficiency}  ",
        f"**Tokens**: {transcript.total_input_tokens} in / {transcript.total_output_tokens} out  ",
        f"**Completed**: {transcript.completed} | **Failed**: {transcript.failed} | **Gave up**: {transcript.gave_up}",
    ]
    if judgment.cli_confusion_notes.strip():
        parts.extend(["", f"**CLI confusion**: {judgment.cli_confusion_notes}"])
    parts.extend(["", "## Transcript", "", "```", transcript.format_for_judge(), "```", ""])
    path.write_text("\n".join(parts))
    logger.info("Saved transcript to %s", path)


def _run_scenario(
    *,
    scenario: LLMEvalScenario,
    bin_dir: Path,
    server_url: str = PROD_STATS_SERVER_URI,
    login_server: str = OBSERVATORY_AUTH_SERVER_URL,
) -> tuple[Transcript, Judgment]:
    client = _get_anthropic_client()
    transcript = run_agent(
        client=client,
        task=scenario.task,
        bin_dir=bin_dir,
        server_url=server_url,
        login_server=login_server,
        max_turns=scenario.max_agent_turns,
    )
    judgment = judge_transcript(client=client, transcript=transcript, scenario_name=scenario.name)
    _save_transcript(scenario.name, transcript, judgment)
    return transcript, judgment


def _assert_judgment(scenario_name: str, judgment: Judgment) -> None:
    logger.info(
        "LLM eval result for %s: passed=%s, scores=[d=%d i=%d c=%d e=%d]",
        scenario_name,
        judgment.passed,
        judgment.discovery,
        judgment.interpretation,
        judgment.completeness,
        judgment.efficiency,
    )
    if judgment.cli_confusion_notes.strip():
        logger.warning("CLI confusion for %s: %s", scenario_name, judgment.cli_confusion_notes)
    assert judgment.passed and judgment.meets_threshold(min_score=MIN_SCORE), (
        f"LLM eval failed for {scenario_name}: passed={judgment.passed}, "
        f"scores=[d={judgment.discovery} i={judgment.interpretation} c={judgment.completeness} e={judgment.efficiency}]"
    )


@stable_function_check(
    timeout_s=600,
    check_group=StableCheckGroup.CLI_HEALTH,
)
def setup_llm_eval_venv(_ctx: StableCheckContext) -> None:
    """Create a fresh isolated venv with the cogames CLI installed for LLM eval checks."""
    if _LLM_EVAL_VENV_DIR.exists():
        shutil.rmtree(_LLM_EVAL_VENV_DIR)
    _LLM_EVAL_VENV_DIR.mkdir(parents=True, exist_ok=True)
    venv_python = _LLM_EVAL_VENV_BIN_DIR / "python"
    subprocess.run(["python3", "-m", "venv", str(_LLM_EVAL_VENV_DIR)], check=True)
    subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(venv_python), "-m", "pip", "install", "cogames"], check=True)


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.CLI_HEALTH,
    depends_on=setup_llm_eval_venv,
)
def llm_eval_spectator_leaderboard(_ctx: StableCheckContext) -> None:
    _, judgment = _run_scenario(scenario=SCENARIOS["spectator_leaderboard"], bin_dir=_LLM_EVAL_VENV_BIN_DIR)
    _assert_judgment("spectator_leaderboard", judgment)


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.CLI_HEALTH,
    depends_on=setup_llm_eval_venv,
)
def llm_eval_tournament_progress(_ctx: StableCheckContext) -> None:
    """LLM eval: agent uses cogames CLI to check if the current season is stuck, what stage it's in, and match count."""
    _, judgment = _run_scenario(scenario=SCENARIOS["tournament_progress"], bin_dir=_LLM_EVAL_VENV_BIN_DIR)
    _assert_judgment("tournament_progress", judgment)


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.CLI_HEALTH,
    depends_on=setup_llm_eval_venv,
)
def llm_eval_important_tournaments(_ctx: StableCheckContext) -> None:
    """LLM eval: agent uses cogames CLI to identify active seasons, the default season, and each tournament's type."""
    _, judgment = _run_scenario(scenario=SCENARIOS["important_tournaments"], bin_dir=_LLM_EVAL_VENV_BIN_DIR)
    _assert_judgment("important_tournaments", judgment)


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.CLI_HEALTH,
    depends_on=setup_llm_eval_venv,
)
def llm_eval_debug_submission_error(_ctx: StableCheckContext) -> None:
    """LLM eval: agent uses cogames CLI to find a failed policy submission and retrieve its error logs."""
    _, judgment = _run_scenario(scenario=SCENARIOS["debug_submission_error"], bin_dir=_LLM_EVAL_VENV_BIN_DIR)
    _assert_judgment("debug_submission_error", judgment)


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.CLI_HEALTH,
    depends_on=setup_llm_eval_venv,
)
def llm_eval_debug_submission_performance(_ctx: StableCheckContext) -> None:
    """LLM eval: agent uses cogames CLI to inspect match results and episode details for a poorly performing policy."""
    _, judgment = _run_scenario(scenario=SCENARIOS["debug_submission_performance"], bin_dir=_LLM_EVAL_VENV_BIN_DIR)
    _assert_judgment("debug_submission_performance", judgment)


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.CLI_HEALTH,
    depends_on=setup_llm_eval_venv,
)
def llm_eval_tournament_game_rules(_ctx: StableCheckContext) -> None:
    """LLM eval: agent uses cogames CLI to explain game rule and objective differences across tournament missions."""
    _, judgment = _run_scenario(scenario=SCENARIOS["tournament_game_rules"], bin_dir=_LLM_EVAL_VENV_BIN_DIR)
    _assert_judgment("tournament_game_rules", judgment)
