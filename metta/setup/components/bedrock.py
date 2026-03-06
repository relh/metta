import os
from pathlib import Path

from metta.common.util.constants import METTA_AWS_REGION
from metta.setup.components.base import SetupModule
from metta.setup.registry import register_module
from metta.setup.utils import info, success

BEDROCK_ENV_VARS: dict[str, str] = {
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "AWS_REGION": METTA_AWS_REGION,
    "ANTHROPIC_MODEL": "us.anthropic.claude-opus-4-6-v1",
    "ANTHROPIC_SMALL_FAST_MODEL": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}


def _find_shell_rc() -> Path | None:
    shell = os.environ.get("SHELL", "")
    if shell.endswith("zsh"):
        return Path(os.environ.get("ZDOTDIR", Path.home())) / ".zshrc"
    if shell.endswith("bash"):
        return Path.home() / ".bashrc"
    return None


def _has_active_export(content: str, var_name: str) -> bool:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if f"export {var_name}=" in stripped:
            return True
    return False


@register_module
class BedrockSetup(SetupModule):
    install_once = True

    def dependencies(self) -> list[str]:
        return ["aws"]

    @property
    def description(self) -> str:
        return "AWS Bedrock LLM access"

    def check_installed(self) -> bool:
        rc_file = _find_shell_rc()
        if rc_file is None:
            return False
        content = rc_file.read_text()
        return all(_has_active_export(content, k) for k in BEDROCK_ENV_VARS)

    def install(self, non_interactive: bool = False, force: bool = False) -> None:
        if self.check_installed() and not force:
            success("Bedrock env vars already configured.")
            return

        rc_file = _find_shell_rc()
        if rc_file is None:
            info("No .zshrc or .bashrc found. Add these env vars manually:")
            for k, v in BEDROCK_ENV_VARS.items():
                info(f"  export {k}={v}")
            return

        content = rc_file.read_text()
        lines_to_add = [f"export {k}={v}" for k, v in BEDROCK_ENV_VARS.items() if not _has_active_export(content, k)]
        if not lines_to_add:
            success("Bedrock env vars already configured.")
            return

        with open(rc_file, "a") as f:
            f.write("\n# AWS Bedrock (Claude Code)\n")
            for line in lines_to_add:
                f.write(f"{line}\n")

        success(f"Added {len(lines_to_add)} Bedrock env var(s) to {rc_file}")
        info("Run `source " + str(rc_file) + "` or open a new shell to activate.")

    def check_connected_as(self) -> str | None:
        try:
            import boto3  # noqa: PLC0415

            client = boto3.client("bedrock", region_name=METTA_AWS_REGION)
            client.list_foundation_models(byOutputModality="TEXT")
            return METTA_AWS_REGION
        except Exception:
            return None

    @property
    def can_remediate_connected_status_with_install(self) -> bool:
        return True
