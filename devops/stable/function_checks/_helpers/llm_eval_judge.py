from __future__ import annotations

import json
import logging
import re

from anthropic import AnthropicBedrock
from pydantic import BaseModel

from devops.stable.function_checks._helpers.llm_eval_harness import Transcript

logger = logging.getLogger(__name__)

JUDGE_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"

JUDGE_PROMPT_TEMPLATE = """\
You are evaluating an AI agent's performance on a CLI task.

Scenario: {scenario_name}

Transcript:
{transcript}

Rate the agent on each dimension from 1 (worst) to 5 (best):

- discovery: Did the agent explore the environment and find relevant commands/files?
- interpretation: Did the agent correctly interpret command outputs and errors?
- completeness: Did the agent fully accomplish the stated task?
- efficiency: Did the agent avoid unnecessary steps and wasted effort?

Also note any points where the agent appeared confused about CLI usage (cli_confusion_notes).
Set "passed" to true if the agent reasonably accomplished the task, false otherwise.

Respond with ONLY a JSON object (no markdown, no explanation):
{{"discovery": <int>, "interpretation": <int>, "completeness": <int>,
"efficiency": <int>, "cli_confusion_notes": "<string>", "passed": <bool>}}
"""


class Judgment(BaseModel):
    discovery: int
    interpretation: int
    completeness: int
    efficiency: int
    cli_confusion_notes: str
    passed: bool

    def meets_threshold(self, min_score: int = 3) -> bool:
        return all(s >= min_score for s in [self.discovery, self.interpretation, self.completeness, self.efficiency])


def judge_transcript(*, client: AnthropicBedrock, transcript: Transcript, scenario_name: str) -> Judgment:
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        scenario_name=scenario_name,
        transcript=transcript.format_for_judge(),
    )
    response = client.messages.create(
        model=JUDGE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = response.content[0].text
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
    raw_text = re.sub(r"\s*```$", "", raw_text.strip())
    judgment = Judgment(**json.loads(raw_text))

    logger.info(
        "Judge scores for %s: discovery=%d interpretation=%d completeness=%d efficiency=%d passed=%s",
        scenario_name,
        judgment.discovery,
        judgment.interpretation,
        judgment.completeness,
        judgment.efficiency,
        judgment.passed,
    )
    if judgment.cli_confusion_notes.strip():
        logger.warning("CLI confusion notes for %s: %s", scenario_name, judgment.cli_confusion_notes)

    return judgment
