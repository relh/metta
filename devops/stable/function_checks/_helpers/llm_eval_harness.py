from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import AnthropicBedrock

AGENT_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
LLM_EVAL_TRANSCRIPT_DIR = Path("devops/stable/state/logs/llm_eval_transcripts")

SYSTEM_PROMPT_TEMPLATE = """\
You are testing the cogames CLI. You have shell access via the bash tool.

The cogames binary is at: {bin_path}
The tournament server is at: {server_url}
{login_server_line}

Instructions:
- Use --help to discover available commands
- Pass --server {server_url} for any tournament-related commands
{login_server_instructions}
- Explore, run commands, and verify behavior

When you have completed the task, write: TASK_COMPLETE: <one-line summary>
If you are stuck and cannot proceed, write: TASK_FAILED: <explanation>
"""

BASH_TOOL = {
    "name": "bash",
    "description": "Run a shell command and return stdout/stderr.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            }
        },
        "required": ["command"],
    },
}

_RESTRICTED_PATH_DIRS = ["/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
_MAX_STDOUT = 10000
_MAX_STDERR = 5000


@dataclass
class AgentTurn:
    assistant_text: str = ""
    command: str | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None


@dataclass
class Transcript:
    task: str
    turns: list[AgentTurn] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    completed: bool = False
    failed: bool = False
    gave_up: bool = False
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    @property
    def summary(self) -> str:
        for turn in reversed(self.turns):
            for marker in ("TASK_COMPLETE:", "TASK_FAILED:"):
                idx = turn.assistant_text.find(marker)
                if idx != -1:
                    return turn.assistant_text[idx + len(marker) :].strip()
        return ""

    def format_for_judge(self) -> str:
        parts = [f"TASK: {self.task}", ""]
        for i, turn in enumerate(self.turns, 1):
            parts.append(f"--- Turn {i} ---")
            if turn.assistant_text:
                parts.append(f"ASSISTANT: {turn.assistant_text}")
            if turn.command:
                parts.append(f"COMMAND: {turn.command}")
                parts.append(f"STDOUT: {turn.stdout}")
                if turn.stderr:
                    parts.append(f"STDERR: {turn.stderr}")
                parts.append(f"EXIT_CODE: {turn.exit_code}")
            parts.append("")
        return "\n".join(parts)


def _execute_command(command: str, bin_dir: Path, timeout_s: int) -> tuple[str, str, int]:
    path = str(bin_dir) + ":" + ":".join(_RESTRICTED_PATH_DIRS)
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=dict(os.environ, PATH=path),
    )
    stdout = result.stdout[:_MAX_STDOUT]
    stderr = result.stderr[:_MAX_STDERR]
    return stdout, stderr, result.returncode


def _build_system_prompt(bin_dir: Path, server_url: str, login_server: str | None) -> str:
    if login_server:
        login_server_line = f"The login/auth server is at: {login_server}"
        login_server_instructions = f"- Pass --login-server {login_server} for auth-related commands"
    else:
        login_server_line = ""
        login_server_instructions = ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        bin_path=str(bin_dir / "cogames"),
        server_url=server_url,
        login_server_line=login_server_line,
        login_server_instructions=login_server_instructions,
    )


def run_agent(
    *,
    client: AnthropicBedrock,
    task: str,
    bin_dir: Path,
    server_url: str,
    login_server: str | None = None,
    max_turns: int = 20,
    command_timeout_s: int = 30,
    model: str = AGENT_MODEL,
) -> Transcript:
    transcript = Transcript(task=task)
    system_prompt = _build_system_prompt(bin_dir, server_url, login_server)
    messages: list[dict] = [{"role": "user", "content": task}]

    for _ in range(max_turns):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system_prompt,
            tools=[BASH_TOOL],
            messages=messages,
        )

        transcript.total_input_tokens += response.usage.input_tokens
        transcript.total_output_tokens += response.usage.output_tokens

        assistant_text = ""
        tool_use_blocks = []

        for block in response.content:
            if block.type == "text":
                assistant_text += block.text
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        if "TASK_COMPLETE" in assistant_text:
            transcript.completed = True
            transcript.turns.append(AgentTurn(assistant_text=assistant_text))
            break

        if "TASK_FAILED" in assistant_text:
            transcript.failed = True
            transcript.turns.append(AgentTurn(assistant_text=assistant_text))
            break

        if not tool_use_blocks:
            transcript.gave_up = True
            transcript.turns.append(AgentTurn(assistant_text=assistant_text))
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tool_block in tool_use_blocks:
            command = tool_block.input.get("command")
            if command is None:
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tool_block.id, "content": "error: missing 'command'"}
                )
                transcript.turns.append(AgentTurn(assistant_text=assistant_text))
                assistant_text = ""
                continue
            stdout, stderr, exit_code = _execute_command(command, bin_dir, command_timeout_s)
            transcript.commands_run.append(command)
            transcript.turns.append(
                AgentTurn(
                    assistant_text=assistant_text,
                    command=command,
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=exit_code,
                )
            )
            assistant_text = ""
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": f"stdout:\n{stdout}\nstderr:\n{stderr}\nexit_code: {exit_code}",
                }
            )
        messages.append({"role": "user", "content": tool_results})
    else:
        transcript.gave_up = True

    return transcript
